"""Provider-neutral multi-turn tool execution loop."""

from __future__ import annotations

import json
import math
import time
from collections import Counter
from collections.abc import Callable
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
)
from ai_provider.closeout import safe_diagnostic_label

from ai_agent.completion import CompletionRequirement, missing_requirements
from ai_agent.contracts import ToolCall, ToolResult
from ai_agent.model_output_recovery import ModelOutputRecovery
from ai_agent.permissions import PermissionManager
from ai_agent.tools.base import ToolContext, ToolRegistry

if TYPE_CHECKING:
    from ai_agent.fanout import FanoutPolicy


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
        max_iterations: int = 10,
        deadline: float | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        diagnostic: Callable[[str], None] | None = None,
        completion_requirements: tuple[CompletionRequirement, ...] = (),
        fanout_policy: FanoutPolicy | str = "allowed",
        on_event: Callable[[ToolExecutionEvent], None] | None = None,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
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

    def run(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        privacy_class: PrivacyClass = PrivacyClass.LOCAL_ONLY,
    ) -> AgentResult:
        """Execute a prompt and any requested tools until a final answer is returned."""
        from ai_provider.credential_guard import (
            contains_credentials,
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
        if system_prompt:
            messages.append(AIMessage(MessageRole.SYSTEM, system_prompt))
        messages.append(AIMessage(MessageRole.USER, prompt))
        tool_results: list[ToolResult] = []
        recovery = ModelOutputRecovery(self.context.workspace_root)
        model_output_errors = 0
        completion_failures = 0
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
            try:
                request = AIRequest(
                    messages=tuple(messages),
                    model=model,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    privacy_class=privacy_class,
                    tools=tuple(
                        _tool_definition(tool) for tool in self.registry.list_definitions()
                    ),
                )
                enforce_credential_policy(request, extra=self.context.credential_secrets)
                response = self.client.complete(request)
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
                return AgentResult(
                    response=response,
                    tool_results=tuple(tool_results),
                    iterations=iteration,
                    messages=tuple(messages),
                    model_output_errors=model_output_errors,
                    completion_failures=completion_failures,
                )

            seen_in_batch: set[tuple[str, str, str]] = set()
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
                    continue
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
                else:
                    pending_key = call.id if call.id else f"anonymous:{iteration}:{position}"
                    self._check_deadline(messages)
                    self._pending[pending_key] = agent_call
                    self._emit_event(ToolExecutionEvent("tool_started", call.name, call.id or None))
                    try:
                        result = tool.run(agent_call, self.context)
                    except ProviderError as exc:
                        # Protocol failure: the effect is uncertain, so the call
                        # stays pending for reconciliation instead of becoming
                        # model feedback.
                        if not exc.partial_messages:
                            exc.partial_messages = tuple(messages)
                        raise
                    except Exception as exc:  # noqa: BLE001 - recovery-as-result
                        # A tool bug escaping BaseTool.run still returns as a
                        # result so the model can adapt; it never crashes the run.
                        output = f"Error executing tool {call.name}: {exc}"
                        if contains_credentials(output, extra=self.context.credential_secrets):
                            output = (
                                "Credential-bearing tool output withheld. Effects may already "
                                "have occurred; inspect locally before continuing."
                            )
                        result = ToolResult(
                            name=call.name,
                            output=output,
                            call_id=call.id,
                            is_error=True,
                        )
                        self._pending.pop(pending_key, None)
                        self._emit_event(
                            ToolExecutionEvent(
                                "tool_completed", call.name, call.id or None, is_error=True
                            )
                        )
                    else:
                        self._pending.pop(pending_key, None)
                        self._emit_event(
                            ToolExecutionEvent(
                                "tool_completed",
                                call.name,
                                call.id or None,
                                is_error=result.is_error,
                            )
                        )
                if replay_key is not None:
                    seen_in_batch.add(replay_key)
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
            "earlier tool effects remain and must be inspected before continuing.",
            category=ProviderErrorCategory.NON_RETRYABLE,
            provider=self.client.backend.provider,
            raw_error=AgentIterationLimitExceeded(),
        )
        error.partial_messages = tuple(messages)
        raise error


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
