"""Provider-neutral multi-turn tool execution loop."""

from __future__ import annotations

import json
import math
import time
from collections import Counter
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Literal

from ai_provider import (
    AIMessage,
    AIRequest,
    AIResponse,
    AIToolCall,
    AIToolDefinition,
    AIToolParameter,
    ChatClient,
    FinishReason,
    MessageRole,
    PrivacyClass,
    ProviderError,
    ProviderErrorCategory,
    ToolCallFormatError,
    UsageMetadata,
    UsageSource,
)
from ai_provider.closeout import safe_diagnostic_label

from ai_agent.chat_context import messages_total_chars
from ai_agent.completion import CompletionRequirement, missing_requirements
from ai_agent.contracts import PermissionAction, ToolCall, ToolResult
from ai_agent.groundedness import check_groundedness
from ai_agent.model_output_recovery import ModelOutputRecovery
from ai_agent.permissions import PermissionManager
from ai_agent.tools.base import ToolContext, ToolRegistry

if TYPE_CHECKING:
    from ai_agent.fanout import FanoutPolicy
    from ai_agent.tools.base import BaseTool


class AgentIterationLimitExceeded(RuntimeError):
    """Known host-loop stop, distinct from a provider or tool failure."""


@dataclass(frozen=True, slots=True)
class ToolExecutionEvent:
    """One tool_started/tool_completed observation from an agent run.

    Events bracket real tool dispatches only. Unknown tools, permission
    refusals and duplicate call-ids produce error results without events,
    since nothing was dispatched and nothing was pending.
    """

    type: Literal["tool_started", "tool_completed"]
    name: str
    call_id: str | None
    is_error: bool = False


@dataclass(frozen=True, slots=True)
class AgentResult:
    """Final response and tool execution history from an agent run."""

    response: AIResponse
    tool_results: tuple[ToolResult, ...] = ()
    iterations: int = 1
    # Transient only, like ProviderError.partial_messages; never log/persist raw continuation.
    messages: tuple[AIMessage, ...] = field(default=(), repr=False, compare=False)
    model_output_errors: int = 0
    completion_failures: int = 0
    compactions: int = 0
    # Accumulated model-call usage for this run() invocation: iterations
    # plus compaction summarizer calls. Descendant delegated loops are not
    # included (the delegation runner protocol carries no usage channel).
    usage: UsageMetadata = field(default_factory=UsageMetadata)


def _combine_usage(first: UsageMetadata, second: UsageMetadata) -> UsageMetadata:
    """Sum two usage records; the source is the weakest link.

    Token/cost fields sum treating None as zero. The combined source is
    honest about gaps: any UNAVAILABLE call poisons the run label, mixed
    reported/estimated degrades to ESTIMATED.
    """
    rank = {
        UsageSource.PROVIDER_REPORTED: 2,
        UsageSource.ESTIMATED: 1,
        UsageSource.UNAVAILABLE: 0,
    }
    source = first.source if rank[first.source] <= rank[second.source] else second.source

    def sum_int(*values: int | None) -> int | None:
        known = [value for value in values if value is not None]
        return sum(known) if known else None

    def sum_float(*values: float | None) -> float | None:
        known = [value for value in values if value is not None]
        return sum(known) if known else None

    combined_in = sum_int(first.input_tokens, second.input_tokens)
    combined_out = sum_int(first.output_tokens, second.output_tokens)
    combined_total = sum_int(first.total_tokens, second.total_tokens)
    if combined_total is None:
        combined_total = sum_int(combined_in, combined_out)
    return UsageMetadata(
        source=source,
        input_tokens=combined_in,
        output_tokens=combined_out,
        total_tokens=combined_total,
        reported_cost_usd=sum_float(first.reported_cost_usd, second.reported_cost_usd),
    )


class AgentLoop:
    """Run authorized tools, optionally requiring declared evidence before completion.

    An identical call repeated inside one response is executed once and never
    auto-replayed; each new turn's calls are fresh model instructions and run
    even if identical to an earlier turn. Dispatched tools are tracked in
    :attr:`pending` and bracketed by tool_started/tool_completed events, and
    tool failures return as results so the model can adapt. Protocol failures
    (provider, deadline, delegation) still raise.
    """

    def __init__(
        self,
        client: ChatClient,
        registry: ToolRegistry,
        context: ToolContext,
        *,
        permissions: PermissionManager | None = None,
        max_iterations: int = 50,
        deadline: float | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        diagnostic: Callable[[str], None] | None = None,
        completion_requirements: tuple[CompletionRequirement, ...] = (),
        fanout_policy: FanoutPolicy | str = "allowed",
        on_event: Callable[[ToolExecutionEvent], None] | None = None,
        request_metadata: Mapping[str, object] | None = None,
        loop_context_budget_chars: int | None = None,
        compaction_tail_messages: int = 8,
        max_compactions: int = 3,
        require_grounded_reports: bool = False,
        delegation_max_workers: int = 4,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
        if loop_context_budget_chars is not None and loop_context_budget_chars < 1:
            raise ValueError("loop_context_budget_chars must be positive or None")
        if compaction_tail_messages < 1:
            raise ValueError("compaction_tail_messages must be at least 1")
        if max_compactions < 0:
            raise ValueError("max_compactions must be non-negative")
        if delegation_max_workers < 1:
            raise ValueError("delegation_max_workers must be at least 1")
        if deadline is not None and not math.isfinite(deadline):
            raise ValueError("deadline must be finite")
        self.client = client
        self.registry = registry
        self.context = context
        self._host_delegation = context.delegation
        self.permissions = permissions or PermissionManager()
        self.max_iterations = max_iterations
        self.deadline = deadline
        self.temperature = temperature
        self.top_p = top_p
        self.diagnostic = diagnostic
        self.on_event = on_event
        self.request_metadata = dict(request_metadata or {})
        self.loop_context_budget_chars = loop_context_budget_chars
        self.compaction_tail_messages = compaction_tail_messages
        self.max_compactions = max_compactions
        self.require_grounded_reports = require_grounded_reports
        self.delegation_max_workers = delegation_max_workers
        self._tool_schema_chars: int | None = None
        self._pending: dict[str, ToolCall] = {}
        if (
            not isinstance(completion_requirements, tuple)
            or len(completion_requirements) > 16
            or any(not isinstance(item, CompletionRequirement) for item in completion_requirements)
        ):
            raise ValueError("Expected at most16 declared completion requirements")
        identifiers = [item.requirement_id for item in completion_requirements]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Completion requirement identifiers must be unique")
        self.completion_requirements = completion_requirements
        from ai_agent.fanout import FanoutPolicy as _FanoutPolicy

        self.fanout_policy = _FanoutPolicy.coerce(fanout_policy)

    def _check_deadline(self, messages: list[AIMessage]) -> None:
        if self.deadline is not None and time.perf_counter() >= self.deadline:
            error = ProviderError(
                "Agent deadline expired; earlier effects remain and must be inspected.",
                category=ProviderErrorCategory.TIMEOUT,
                provider=self.client.backend.provider,
            )
            error.partial_messages = tuple(messages)
            raise error

    @property
    def pending(self) -> tuple[ToolCall, ...]:
        """Dispatched tool calls awaiting completion.

        Non-empty only while a tool executes. A protocol failure escaping a
        tool keeps its call here: the effect is uncertain and must be
        reconciled before continuing.
        """
        return tuple(self._pending.values())

    def _emit_event(self, event: ToolExecutionEvent) -> None:
        if self.on_event is not None:
            self.on_event(event)

    def _measured_context_chars(self, messages: list[AIMessage]) -> int:
        """Transcript chars plus the tool schemas sent with every request."""
        if self._tool_schema_chars is None:
            total = 0
            for definition in self.registry.list_definitions():
                try:
                    rendered = json.dumps(
                        _tool_definition(definition).to_json_schema(),
                        ensure_ascii=False,
                    )
                except (TypeError, ValueError):
                    rendered = definition.name
                total += len(rendered)
            self._tool_schema_chars = total
        return messages_total_chars(messages) + self._tool_schema_chars

    def _visible_tool_definitions(self) -> list[AIToolDefinition]:
        """Export registry tools minus policy-denied ones.

        A denied tool is hidden from the model's context (deny wins); the
        permission check at dispatch still enforces the policy.
        """
        visible: list[AIToolDefinition] = []
        for tool in self.registry.list_definitions():
            action = self.permissions.policy.action_for_tool(tool.name, tool.category)
            if action is PermissionAction.DENY:
                continue
            visible.append(_tool_definition(tool))
        return visible

    def _run_authorized_call(self, tool: BaseTool, agent_call: ToolCall) -> ToolResult:
        """Execute one authorized call; converts bugs to results, reraises protocol."""
        from ai_provider.credential_guard import contains_credentials

        try:
            return tool.run(agent_call, self.context)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 - recovery-as-result
            output = f"Error executing tool {agent_call.name}: {exc}"
            if contains_credentials(output, extra=self.context.credential_secrets):
                output = (
                    "Credential-bearing tool output withheld. Effects may already "
                    "have occurred; inspect locally before continuing."
                )
            return ToolResult(
                name=agent_call.name,
                output=output,
                call_id=agent_call.call_id,
                is_error=True,
            )

    def _dispatch_sequential(self, tool, agent_call, pending_key, call, messages) -> ToolResult:
        """Run one call inline with pending/event bookkeeping on this thread."""
        self._check_deadline(messages)
        self._pending[pending_key] = agent_call
        self._emit_event(ToolExecutionEvent("tool_started", call.name, call.id or None))
        try:
            result = self._run_authorized_call(tool, agent_call)
        except ProviderError as exc:
            if not exc.partial_messages:
                exc.partial_messages = tuple(messages)
            raise
        self._pending.pop(pending_key, None)
        self._emit_event(
            ToolExecutionEvent(
                "tool_completed",
                call.name,
                call.id or None,
                is_error=result.is_error,
            )
        )
        return result

    def _fanout_delegates(self, delegates, messages):
        """Run sibling delegate_task calls concurrently; ordered results.

        ``delegates`` is ``[(position, call, tool, agent_call, pending_key,
        replay_key), ...]``. Started events fire on this thread before the
        spawn, completed events after the join, both in position order. The
        first ProviderError aborts the batch (fail-loud, like sequential).
        Returns ``{position: (call, result, replay_key)}``.
        """
        self._check_deadline(messages)
        workers = min(self.delegation_max_workers, len(delegates))
        if self.diagnostic:
            self.diagnostic(f"delegation_fanout: n={len(delegates)} workers={workers}")
        for _position, call, _tool, agent_call, pending_key, _replay in delegates:
            self._pending[pending_key] = agent_call
            self._emit_event(ToolExecutionEvent("tool_started", call.name, call.id or None))
        import concurrent.futures as _futures

        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="delegate") as pool:
            future_map = {
                pool.submit(self._run_authorized_call, tool, agent_call): (
                    position,
                    call,
                    pending_key,
                    replay,
                )
                for position, call, tool, agent_call, pending_key, replay in delegates
            }
            done: dict = {}
            failure = None
            for future in _futures.as_completed(future_map):
                position, call, pending_key, replay = future_map[future]
                try:
                    done[position] = (call, future.result(), replay, pending_key)
                except ProviderError as exc:
                    if failure is None:
                        failure = (position, exc)
                except Exception as exc:  # noqa: BLE001 - defensive; helper converts
                    done[position] = (
                        call,
                        ToolResult(
                            name=call.name,
                            output=f"Error executing tool {call.name}: {exc}",
                            call_id=call.id,
                            is_error=True,
                        ),
                        replay,
                        pending_key,
                    )
            outcomes: dict = {}
            for position in sorted(done):
                call, result, replay, pending_key = done[position]
                self._pending.pop(pending_key, None)
                self._emit_event(
                    ToolExecutionEvent(
                        "tool_completed",
                        call.name,
                        call.id or None,
                        is_error=result.is_error,
                    )
                )
                outcomes[position] = (call, result, replay)
            if failure is not None:
                _position, exc = failure
                if not exc.partial_messages:
                    exc.partial_messages = tuple(messages)
                raise exc
            return outcomes

    def _maybe_compact(
        self,
        messages: list[AIMessage],
        compactions: int,
        model: str | None,
        privacy_class: PrivacyClass,
    ) -> tuple[int, UsageMetadata | None]:
        """Summarize older turns when the loop context budget is exceeded.

        Original system messages (required instructions) are immune and always
        kept verbatim. Older non-system turns plus any prior compaction summary
        are folded into a fresh rolling summary; the newest tail stays verbatim.
        Returns the updated compaction count plus the summarizer call usage
        (None when nothing was compacted).
        """
        budget = self.loop_context_budget_chars
        if budget is None or self._measured_context_chars(messages) <= budget:
            return compactions, None
        if compactions >= self.max_compactions:
            raise ProviderError(
                f"loop context still exceeds its budget after {compactions} "
                "compactions; one large output likely refills the window. "
                "Inspect earlier effects and continue only unfinished work.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider=self.client.backend.provider,
            )
        systems = [item for item in messages if item.role is MessageRole.SYSTEM]
        immune = [item for item in systems if not _is_compaction_summary(item)]
        prior_summaries = [item for item in systems if _is_compaction_summary(item)]
        conversation = [item for item in messages if item.role is not MessageRole.SYSTEM]
        if not conversation and not prior_summaries:
            raise ProviderError(
                "loop instructions alone exceed the loop context budget; "
                "raise the budget instead of compacting them away.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider=self.client.backend.provider,
            )
        tail = conversation[-self.compaction_tail_messages :]
        while tail and self._measured_context_chars([*immune, *tail]) > budget:
            tail = tail[1:]
        if conversation and not tail:
            raise ProviderError(
                "loop instructions plus the latest message exceed the loop "
                "context budget; nothing older remains to summarize.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider=self.client.backend.provider,
            )
        older = conversation[: len(conversation) - len(tail)] if tail else list(conversation)
        foldable: list[AIMessage] = [*prior_summaries, *older]
        if not foldable:
            raise ProviderError(
                "loop context exceeds its budget but every turn is inside the "
                "protected tail; raise the budget or narrow the task.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider=self.client.backend.provider,
            )
        self._check_deadline(messages)
        from ai_provider.credential_guard import enforce_credential_policy

        summary_request = AIRequest(
            messages=(
                AIMessage(
                    MessageRole.SYSTEM,
                    "Summarize an in-progress coding-agent transcript so the run "
                    "can continue. A prior summary may be included; fold it in "
                    "and supersede it. Preserve the original objective, owner "
                    "decisions, files created/modified with their states, "
                    "commands run with outcomes, validation results, open "
                    "questions, and remaining work. Do not invent facts. "
                    "Return only the summary.",
                ),
                AIMessage(MessageRole.USER, _render_compaction_source(foldable, budget)),
            ),
            model=model,
            privacy_class=privacy_class,
            metadata={**self.request_metadata, "task_type": "loop_compaction"},
        )
        enforce_credential_policy(summary_request, extra=self.context.credential_secrets)
        summary_response = self.client.complete(summary_request)
        summary_text = summary_response.message.content.strip()
        if not summary_text:
            raise ProviderError(
                "loop compaction summarizer returned an empty summary",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider=self.client.backend.provider,
            )
        messages[:] = [
            *immune,
            AIMessage(
                MessageRole.SYSTEM,
                "Compacted summary of earlier turns. Use this as compressed "
                "context; the following messages are the recent raw tail.\n\n"
                f"{summary_text}",
            ),
            *tail,
        ]
        if self.diagnostic:
            self.diagnostic(
                f"loop_compaction: n={compactions + 1} summarized={len(foldable)} tail={len(tail)}"
            )
        return compactions + 1, summary_response.usage

    def resume(
        self,
        messages: tuple[AIMessage, ...],
        *,
        model: str | None = None,
        privacy_class: PrivacyClass = PrivacyClass.LOCAL_ONLY,
        prior_iterations: int = 0,
        prior_tool_results: tuple[ToolResult, ...] = (),
    ) -> AgentResult:
        """Continue an exhausted run from saved messages under a fresh allowance.

        ``messages`` is normally ``ProviderError.partial_messages`` from a run
        that raised with ``AgentIterationLimitExceeded``, and
        ``prior_tool_results`` the matching ``ProviderError.tool_results``.
        The loop budget restarts at zero local iterations; priors seed the
        cumulative counts reported on the result.
        """
        return self.run(
            "",
            model=model,
            privacy_class=privacy_class,
            resume_messages=messages,
            prior_iterations=prior_iterations,
            prior_tool_results=prior_tool_results,
        )

    def run(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        privacy_class: PrivacyClass = PrivacyClass.LOCAL_ONLY,
        resume_messages: tuple[AIMessage, ...] | None = None,
        prior_iterations: int = 0,
        prior_tool_results: tuple[ToolResult, ...] = (),
    ) -> AgentResult:
        """Execute a prompt and any requested tools until a final answer is returned.

        ``resume_messages`` continues an exhausted run from saved messages
        (e.g. ``ProviderError.partial_messages``); ``prompt``/``system_prompt``
        are ignored then and ``prior_iterations`` seeds cumulative reporting.
        ``prior_tool_results`` restores earlier evidence for groundedness
        checks and cumulative reporting. Prefer :meth:`resume` for that path.
        """
        if prior_iterations < 0:
            raise ValueError("prior_iterations must be non-negative")
        if resume_messages is not None:
            if not resume_messages or any(
                not isinstance(item, AIMessage) for item in resume_messages
            ):
                raise ValueError("resume_messages must be a non-empty AIMessage tuple")
        from ai_provider.credential_guard import (
            credential_values,
            enforce_credential_policy,
        )

        self._pending.clear()

        self.context = replace(
            self.context,
            credential_secrets=credential_values(
                (
                    *self.context.credential_secrets,
                    getattr(getattr(self.client, "config", None), "api_key", None),
                )
            ),
        )
        if self._host_delegation is None and any(
            item.name == "delegate_task" for item in self.registry.list_definitions()
        ):
            from ai_agent.delegation_scope import DelegationBudget, DelegationScope

            self.context = replace(
                self.context,
                delegation=DelegationScope(
                    self.registry,
                    self.permissions,
                    self.context.workspace_root.resolve(),
                    DelegationBudget(self.max_iterations, self.deadline),
                    fanout=self.fanout_policy,
                    instructions=system_prompt or "",
                    objective=prompt,
                    backends=frozenset(
                        {
                            (
                                self.client.backend.provider,
                                self.client.backend.model,
                                self.client.backend.base_url,
                            )
                        }
                    ),
                    approved_client=self.client,
                    request_timeout_seconds=getattr(
                        getattr(self.client, "config", None), "timeout_seconds", None
                    ),
                ),
            )
        messages: list[AIMessage] = []
        if resume_messages is not None:
            messages.extend(resume_messages)
        else:
            if system_prompt:
                messages.append(AIMessage(MessageRole.SYSTEM, system_prompt))
            messages.append(AIMessage(MessageRole.USER, prompt))
        tool_results: list[ToolResult] = list(prior_tool_results)
        recovery = ModelOutputRecovery(self.context.workspace_root)
        model_output_errors = 0
        completion_failures = 0
        compactions = 0
        # Nullable until the first model call: an empty UNAVAILABLE seed
        # would poison the weakest-link source of every run.
        usage: UsageMetadata | None = None
        incomplete_states: Counter[tuple[tuple[str, ...], tuple[tuple[str, str], ...]]] = Counter()

        for iteration in range(1, self.max_iterations + 1):
            self._check_deadline(messages)
            if self.context.delegation is not None:
                if not self.context.delegation.active():
                    raise ProviderError(
                        "Parent delegation authority expired.",
                        category=ProviderErrorCategory.NON_RETRYABLE,
                    )
                self.context.delegation.budget.consume()
            compactions, compact_usage = self._maybe_compact(
                messages, compactions, model, privacy_class
            )
            if compact_usage is not None:
                usage = compact_usage if usage is None else _combine_usage(usage, compact_usage)
            try:
                request = AIRequest(
                    messages=tuple(messages),
                    model=model,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    privacy_class=privacy_class,
                    tools=tuple(self._visible_tool_definitions()),
                    metadata=dict(self.request_metadata),
                )
                enforce_credential_policy(request, extra=self.context.credential_secrets)
                response = self.client.complete(request)
                usage = response.usage if usage is None else _combine_usage(usage, response.usage)
            except ToolCallFormatError as exc:
                model_output_errors += 1
                self._check_deadline(messages)
                allowed = iteration < self.max_iterations and recovery.allow_feedback()
                if self.diagnostic:
                    cause = exc.__cause__ or exc.raw_error
                    cause_kind = safe_diagnostic_label(type(cause).__name__) if cause else "unknown"
                    self.diagnostic(
                        "model_output_error: "
                        f"provider={safe_diagnostic_label(exc.provider) or 'unknown'} "
                        f"category={exc.category.value} "
                        f"cause_kind={cause_kind}"
                    )
                    self.diagnostic(
                        f"model_output_recovery: errors={model_output_errors} "
                        f"action={'feedback' if allowed else 'stop'}"
                    )
                if not allowed:
                    error = ProviderError(
                        "Malformed tool arguments repeated without observed file progress, "
                        "or the turn allowance ended. Earlier effects remain; inspect them "
                        "and continue only unfinished work in an explicitly resumed turn.",
                        category=ProviderErrorCategory.NON_RETRYABLE,
                        provider=exc.provider,
                    )
                    error.partial_messages = tuple(messages)
                    raise error from exc
                messages.append(
                    AIMessage(
                        MessageRole.USER,
                        "Host execution feedback: the last response's tool arguments could not "
                        "be decoded. No tool from that response executed. Earlier tool effects "
                        "remain recorded above; do not replay them. Correct the arguments using "
                        "the declared schemas and inspect existing effects when needed. "
                        "The original permissions, task and remaining allowance still apply.",
                    )
                )
                continue
            except ProviderError as exc:
                exc.partial_messages = tuple(messages)
                raise
            messages.append(response.message)
            self._check_deadline(messages)
            tool_calls = response.tool_calls or response.message.tool_calls
            if not tool_calls:
                if (
                    self.completion_requirements
                    and response.finish_reason not in {FinishReason.LENGTH, FinishReason.ERROR}
                    and response.message.content.strip()
                ):
                    try:
                        missing = missing_requirements(
                            self.completion_requirements, tuple(tool_results)
                        )
                    except Exception:
                        error = ProviderError(
                            "Completion evidence checker failed; inspect earlier effects "
                            "and the declared requirements before continuing.",
                            category=ProviderErrorCategory.NON_RETRYABLE,
                            provider=self.client.backend.provider,
                        )
                        error.partial_messages = tuple(messages)
                        raise error from None
                    self._check_deadline(messages)
                    if missing:
                        completion_failures += 1
                        key = (missing, recovery.observed_state())
                        self._check_deadline(messages)
                        incomplete_states[key] += 1
                        allowed = iteration < self.max_iterations and incomplete_states[key] < 2
                        if self.diagnostic:
                            self.diagnostic("completion_check: missing=" + ",".join(missing))
                            self.diagnostic(
                                f"completion_recovery: errors={completion_failures} "
                                f"action={'feedback' if allowed else 'stop'}"
                            )
                        if not allowed:
                            error = ProviderError(
                                "Required completion evidence is still missing: "
                                + ",".join(missing)
                                + ". The same blocker recurred without observed progress, "
                                "or the original turn allowance ended. Inspect earlier "
                                "effects and continue only unfinished work in a new turn.",
                                category=ProviderErrorCategory.NON_RETRYABLE,
                                provider=self.client.backend.provider,
                            )
                            error.partial_messages = tuple(messages)
                            raise error
                        messages.append(
                            AIMessage(
                                MessageRole.USER,
                                "Host completion feedback: the preceding model report is "
                                "a candidate, not accepted task completion. Missing required "
                                "successful observations: "
                                + ",".join(missing)
                                + ". Perform only the unfinished authorized work and then "
                                "author a corrected factual final report. Earlier tool "
                                "effects and observations remain above; do not replay them. "
                                "The original task, permissions and remaining allowance "
                                "still apply; this feedback grants no new actions or time.",
                            )
                        )
                        continue
                if (
                    self.require_grounded_reports
                    and response.finish_reason not in {FinishReason.LENGTH, FinishReason.ERROR}
                    and response.message.content.strip()
                ):
                    verdict = check_groundedness(response.message.content, tuple(tool_results))
                    if verdict.unsupported:
                        completion_failures += 1
                        classes = sorted({claim.claim_class for claim in verdict.unsupported})
                        key = (("groundedness", *classes), recovery.observed_state())
                        self._check_deadline(messages)
                        incomplete_states[key] += 1
                        allowed = iteration < self.max_iterations and incomplete_states[key] < 2
                        if self.diagnostic:
                            self.diagnostic("groundedness_check: unsupported=" + ",".join(classes))
                            self.diagnostic(
                                f"groundedness_recovery: errors={completion_failures} "
                                f"action={'feedback' if allowed else 'stop'}"
                            )
                        if not allowed:
                            error = ProviderError(
                                "Report claims verification without observed tool "
                                "evidence: "
                                + ",".join(classes)
                                + ". The same blocker recurred without observed "
                                "progress, or the original turn allowance ended. "
                                "Inspect earlier effects and continue only "
                                "unfinished work in a new turn.",
                                category=ProviderErrorCategory.NON_RETRYABLE,
                                provider=self.client.backend.provider,
                            )
                            error.partial_messages = tuple(messages)
                            raise error
                        messages.append(
                            AIMessage(
                                MessageRole.USER,
                                "Host groundedness feedback: the preceding report "
                                "claims completed verification ("
                                + ",".join(classes)
                                + ") but no supporting tool evidence was observed "
                                "in this run. Perform the checks with authorized "
                                "tools and then author a corrected factual final "
                                "report, or downgrade the report to an explicitly "
                                "unverified summary with no verification claims. "
                                "Earlier tool effects remain above; do not replay "
                                "them. The original task, permissions and "
                                "remaining allowance still apply.",
                            )
                        )
                        continue
                return AgentResult(
                    response=response,
                    tool_results=tuple(tool_results),
                    iterations=prior_iterations + iteration,
                    messages=tuple(messages),
                    model_output_errors=model_output_errors,
                    completion_failures=completion_failures,
                    compactions=compactions,
                    usage=usage if usage is not None else UsageMetadata(),
                )

            seen_in_batch: set[tuple[str, str, str]] = set()
            planned: list[tuple[int, str, tuple, AIToolCall]] = []
            for position, call in enumerate(tool_calls):
                self._check_deadline(messages)
                if self.context.delegation is not None:
                    self.context.delegation.budget.consume_tool()
                replay_key = _replay_key(call)
                if replay_key is not None and replay_key in seen_in_batch:
                    # Never auto-replay: an identical call already completed in
                    # this response keeps its recorded outcome. No dispatch,
                    # no pending, no events.
                    result = ToolResult(
                        name=call.name,
                        output=(
                            f"Error: tool call {call.id!r} already completed in this "
                            "response; not replayed. Earlier effects and observations "
                            "remain above; continue with unfinished work only."
                        ),
                        call_id=call.id,
                        is_error=True,
                    )
                    planned.append((position, "result", (result, replay_key), call))
                    continue
                # Record the key at plan time: later duplicates in the same
                # batch must see it during planning, before anything executes.
                if replay_key is not None:
                    seen_in_batch.add(replay_key)
                agent_call = ToolCall(name=call.name, arguments=call.arguments, call_id=call.id)
                tool = self.registry.get(call.name)
                if tool is None:
                    registered_names = sorted(t.name for t in self.registry.list_definitions())
                    names_str = ", ".join(repr(name) for name in registered_names)
                    registry_detail = (
                        f"Registered tool names: {names_str}."
                        if registered_names
                        else "No tools are registered in this run."
                    )
                    result = ToolResult(
                        name=call.name,
                        output=(
                            f"Error: unknown tool {call.name!r}. {registry_detail} "
                            "No operation was attempted."
                        ),
                        call_id=call.id,
                        is_error=True,
                    )
                    planned.append((position, "result", (result, replay_key), call))
                    continue
                elif not self.permissions.check_and_authorize(tool, agent_call):
                    try:
                        tool.validate_arguments(agent_call.arguments)
                    except (ValueError, OverflowError):
                        # Schema metadata is safe feedback; argument values and exception
                        # text may contain private data and must not be echoed here.
                        schema = ", ".join(
                            f"{parameter.name}: {parameter.type_name}"
                            + (" (required)" if parameter.required else "")
                            for parameter in tool.definition.parameters
                        )
                        refusal = (
                            f"Error: invalid arguments for tool {call.name!r}. "
                            f"Expected schema: {schema}. No operation attempted."
                        )
                    else:
                        refusal = (
                            f"Error: tool call {call.name!r} was not authorized. "
                            "No operation attempted."
                        )
                    result = ToolResult(
                        name=call.name,
                        output=refusal,
                        call_id=call.id,
                        is_error=True,
                    )
                    planned.append((position, "result", (result, replay_key), call))
                    continue
                pending_key = call.id if call.id else f"anonymous:{iteration}:{position}"
                planned.append(
                    (
                        position,
                        "dispatch",
                        (tool, agent_call, pending_key, replay_key),
                        call,
                    )
                )
            delegate_entries = []
            for position, kind, payload, call in planned:
                if kind == "dispatch" and call.name == "delegate_task":
                    tool, agent_call, pending_key, replay = payload
                    delegate_entries.append((position, call, tool, agent_call, pending_key, replay))
            parallel = (
                len(delegate_entries) >= 2
                and self.delegation_max_workers > 1
                and self.permissions.approval_callback is None
            )
            fanout_results: dict[int, tuple] = {}
            fanout_done = False
            for position, kind, payload, call in planned:
                if kind == "result":
                    result, replay_key = payload
                else:
                    tool, agent_call, pending_key, replay_key = payload
                    if parallel and call.name == "delegate_task":
                        if not fanout_done:
                            fanout_results = self._fanout_delegates(delegate_entries, messages)
                            fanout_done = True
                        _call, result, replay_key = fanout_results[position]
                    else:
                        result = self._dispatch_sequential(
                            tool, agent_call, pending_key, call, messages
                        )
                # seen_in_batch was populated at plan time (above); every
                # duplicate in this batch was already refused there.
                tool_results.append(result)
                recovery.observe(result)
                messages.append(
                    AIMessage(
                        role=MessageRole.TOOL,
                        content=result.output,
                        tool_call_id=call.id,
                        name=call.name,
                    )
                )
                self._check_deadline(messages)

        error = ProviderError(
            f"Agent loop exceeded max_iterations={self.max_iterations}; "
            "earlier tool effects remain and must be inspected before continuing. "
            "Resume under a fresh allowance with AgentLoop.resume(partial_messages).",
            category=ProviderErrorCategory.NON_RETRYABLE,
            provider=self.client.backend.provider,
            raw_error=AgentIterationLimitExceeded(),
        )
        error.partial_messages = tuple(messages)
        # Dynamic: ProviderError lives below ai_agent and cannot import ToolResult.
        error.tool_results = tuple(tool_results)
        raise error


COMPACTION_SUMMARY_PREFIX = "Compacted summary of earlier turns."


def _is_compaction_summary(message: AIMessage) -> bool:
    return message.content.startswith(COMPACTION_SUMMARY_PREFIX)


def _render_compaction_source(messages: list[AIMessage], cap_chars: int) -> str:
    """Render older turns for the summarizer, newest first under a char cap."""
    parts: list[str] = []
    used = 0
    omitted = 0
    for message in reversed(messages):
        rendered = (
            f"[{message.role.value}]"
            + (f" tool={message.name}" if message.name else "")
            + f":\n{message.content}"
        )
        if used + len(rendered) > cap_chars and parts:
            omitted += 1
            continue
        parts.append(rendered)
        used += len(rendered)
    parts.reverse()
    header = (
        f"# Earlier transcript ({len(messages)} turns"
        + (f", {omitted} oldest omitted over the cap" if omitted else "")
        + ")\n"
    )
    return header + "\n\n".join(parts)


def _replay_key(call: AIToolCall) -> tuple[str, str, str] | None:
    """Identify one issued call for within-response never-replay tracking.

    The key covers the call-id and the full operation: an identical repeat
    inside one response is a replay and is refused, while a repeated id
    carrying a different operation is a fresh call. Calls without an id are
    never deduplicated.
    """
    if not call.id:
        return None
    try:
        fingerprint = json.dumps(call.arguments, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return None
    return (call.id, call.name, fingerprint)


def _tool_definition(definition: Any) -> AIToolDefinition:
    return AIToolDefinition(
        name=definition.name,
        description=definition.description,
        parameters=tuple(
            AIToolParameter(
                name=parameter.name,
                type_name=parameter.type_name,
                description=parameter.description,
                required=parameter.required,
                default=parameter.default,
                enum_values=parameter.enum_values,
                item_type_name=getattr(parameter, "item_type_name", None),
            )
            for parameter in definition.parameters
        ),
    )
