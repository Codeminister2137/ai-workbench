from __future__ import annotations

import argparse
import atexit
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from io import TextIOBase
from pathlib import Path
from typing import Any

# Imports below use the repository's source layout when this example is run directly.
# ruff: noqa: E402
_REPO_ROOT = Path(__file__).resolve().parents[3]
for _package_dir in (
    _REPO_ROOT / "packages" / "ai_provider" / "src",
    _REPO_ROOT / "packages" / "ai_orchestrator" / "src",
    _REPO_ROOT / "packages" / "ai_agent" / "src",
):
    if _package_dir.exists() and str(_package_dir) not in sys.path:
        sys.path.insert(0, str(_package_dir))

from ai_agent import (
    AgentLoop,
    PermissionManager,
    PermissionPolicy,
    ToolContext,
    default_coding_tools,
)
from ai_orchestrator import (
    AccessMethod,
    CostPolicyTier,
    DelegationKind,
    LatencyTarget,
    QualityThreshold,
    TaskType,
    assess_delegation,
    load_model_catalog,
    plan_delegated_subtask,
)
from ai_orchestrator import PrivacyClass as OrchestratorPrivacyClass
from ai_provider import (
    AIMessage,
    AIRequest,
    BackendConfig,
    ChatClient,
    MessageRole,
    PrivacyClass,
    ProviderError,
    ProviderKind,
    create_chat_client,
    ensure_ollama_server,
    get_local_provider_capability_snapshot,
    get_ollama_resource_profile,
    is_ollama_server_available,
)
from ai_provider import PrivacyClass as ProviderPrivacyClass
from coding_assist import coding_task_profile, run_coding_prompt


@dataclass(frozen=True, slots=True)
class RepoContextFile:
    """One file approved for inclusion in a repo-aware prompt."""

    path: Path
    display_path: str
    content: str
    inside_repo: bool


@dataclass(frozen=True, slots=True)
class AssistantAction:
    """One proposed local action emitted by the assistant model."""

    action_type: str
    args: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AssistantActionResult:
    """Result of one local assistant action."""

    action_type: str
    ok: bool
    summary: str
    output: str = ""


_ACTION_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
DEFAULT_CONTEXT_BUDGET_CHARS = 5_000
DEFAULT_CONTEXT_FILE_BUDGET_CHARS = 2_500
DEFAULT_DELEGATION_CONTEXT_BUDGET_CHARS = 6_000
CLI_MODES = ("ask", "review", "implement", "plan", "diagnose")
_TOOL_SYSTEM_PROMPT = """
You are a repo-aware coding assistant. Use the provided repository context,
preserve the permission boundary, and do not claim to have edited or executed
files unless an action result proves it.

When you need local tools, emit exactly one JSON object in a fenced json block:

```json
{"actions":[{"type":"read_file","path":"relative/path.py"}]}
```

Supported action types:
- read_file: {"type":"read_file","path":"relative/path"}
- list_dir: {"type":"list_dir","path":"relative/path"}
- write_file: {"type":"write_file","path":"relative/path","content":"full file content"}
- run_command: {"type":"run_command","command":"command string","cwd":"optional/relative/path"}

Prefer the smallest useful action set. Do not invent persistent state, background
jobs, external actions, or hidden side effects.
""".strip()
_RESPONSE_SCRUTINY_SYSTEM_PROMPT = """
You scrutinize a repo-aware coding assistant response for usefulness and accuracy.
Compare the candidate response with the original request and the supplied repository
context. Do not invent facts or claim that a recommendation is required when the
context does not support it.

Return a concise report with exactly these headings:
VERDICT: pass | needs_revision | fail
SCORE: 0-10
STRENGTHS:
ISSUES:
RECOMMENDED_NEXT_ACTION:
REVISED_RESPONSE:

Judge whether the answer is grounded in the repository, distinguishes completed
work from remaining work, identifies the smallest useful next action, avoids
generic filler, and states uncertainty or decision boundaries. If the candidate
is already good, say so rather than proposing unnecessary changes.
""".strip()


class _TeeOutput(TextIOBase):
    """Write CLI output to the terminal and an optional transcript file."""

    def __init__(self, terminal: Any, transcript: Any) -> None:
        self._terminal = terminal
        self._transcript = transcript

    def write(self, text: str) -> int:
        self._terminal.write(text)
        self._transcript.write(text)
        return len(text)

    def flush(self) -> None:
        self._terminal.flush()
        self._transcript.flush()


def _capability_report(snapshot: Any) -> dict[str, Any]:
    """Convert the local capability snapshot into stable JSON-friendly data."""

    return {
        "system": {
            "os": snapshot.system.os_name,
            "os_version": snapshot.system.os_version,
            "machine": snapshot.system.machine,
            "processor": snapshot.system.processor,
            "logical_cpu_count": snapshot.system.logical_cpu_count,
            "memory_total_bytes": snapshot.system.memory.total_bytes,
            "memory_available_bytes": snapshot.system.memory.available_bytes,
            "gpus": [
                {
                    "name": gpu.name,
                    "memory_bytes": gpu.memory_bytes,
                    "memory_source": gpu.memory_source,
                }
                for gpu in snapshot.system.gpus
            ],
        },
        "ollama": {
            "available": snapshot.ollama_available,
            "version": snapshot.ollama_version,
            "models_path": str(snapshot.models_path),
            "installed_models": [model.model for model in snapshot.installed_ollama_models],
            "running_models": [model.model for model in snapshot.running_ollama_models],
        },
    }


def build_response_scrutiny_prompt(original_prompt: str, response: str) -> str:
    """Build a bounded second-pass prompt for evaluating one assistant response."""

    return (
        "Original repository-analysis request:\n"
        f"{original_prompt}\n\n"
        "Candidate assistant response:\n"
        f"{response}\n\n"
        "Scrutinize the candidate response using the required report format."
    )


def find_repo_root(start: Path) -> Path:
    """Find the nearest Git repository root at or above start."""

    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return current


def build_default_system_prompt(extra_system_prompt: str | None = None) -> str:
    """Return the repo-aware system prompt with optional caller instructions."""

    if not extra_system_prompt:
        return _TOOL_SYSTEM_PROMPT
    return f"{_TOOL_SYSTEM_PROMPT}\n\nAdditional instruction:\n{extra_system_prompt.strip()}"


def load_prompt_context(
    repo_root: Path,
    selected_paths: Sequence[Path],
    *,
    input_func: Callable[[str], str] = input,
    allow_outside_files: bool = False,
    context_budget_chars: int | None = DEFAULT_CONTEXT_BUDGET_CHARS,
    context_file_budget_chars: int = DEFAULT_CONTEXT_FILE_BUDGET_CHARS,
) -> tuple[RepoContextFile, ...]:
    """Load approved context files within deterministic size budgets."""

    if context_budget_chars is not None and context_budget_chars <= 0:
        raise ValueError("context_budget_chars must be greater than zero or None.")
    if context_file_budget_chars <= 0:
        raise ValueError("context_file_budget_chars must be greater than zero.")

    context_paths = [
        repo_root / "AGENTS.md",
        repo_root / "CURRENT_CONTEXT.md",
        *selected_paths,
    ]
    loaded: list[RepoContextFile] = []
    seen: set[Path] = set()
    for path in context_paths:
        resolved = _resolve_context_path(repo_root, path)
        if resolved in seen or not resolved.exists() or not resolved.is_file():
            continue
        seen.add(resolved)
        inside_repo = _is_relative_to(resolved, repo_root)
        if not inside_repo and not allow_outside_files:
            if not _confirm_outside_read(resolved, input_func=input_func):
                continue
        remaining_budget = (
            None
            if context_budget_chars is None
            else max(context_budget_chars - sum(len(item.content) for item in loaded), 0)
        )
        if remaining_budget == 0:
            continue
        content_limit = context_file_budget_chars
        if remaining_budget is not None:
            content_limit = min(content_limit, remaining_budget)
        loaded.append(
            RepoContextFile(
                path=resolved,
                display_path=_display_path(repo_root, resolved),
                content=_limit_context_content(
                    resolved.read_text(encoding="utf-8", errors="replace"),
                    content_limit,
                ),
                inside_repo=inside_repo,
            )
        )
    return tuple(loaded)


def _limit_context_content(content: str, max_chars: int) -> str:
    """Keep the beginning and end of a file while marking omitted content."""

    if len(content) <= max_chars:
        return content
    marker = f"\n[context truncated; {len(content) - max_chars} chars]\n"
    available = max_chars - len(marker)
    if available <= 0:
        return marker[:max_chars]
    head_chars = (available + 1) // 2
    tail_chars = available // 2
    tail = content[-tail_chars:].lstrip() if tail_chars else ""
    return content[:head_chars].rstrip() + marker + tail


def build_repo_prompt(user_prompt: str, context_files: Sequence[RepoContextFile]) -> str:
    """Combine the user's request and approved repository context into one prompt."""

    sections = [
        "# User request",
        user_prompt.strip(),
        "",
        "# Repository context",
    ]
    if not context_files:
        sections.append("No repository context files were loaded.")
    for context_file in context_files:
        boundary = "inside-repo" if context_file.inside_repo else "outside-repo-approved"
        sections.extend(
            [
                "",
                f"## {context_file.display_path} ({boundary})",
                "```text",
                context_file.content.rstrip(),
                "```",
            ]
        )
    return "\n".join(sections).strip()


def build_delegation_context(
    context_files: Sequence[RepoContextFile],
    *,
    max_chars: int = DEFAULT_DELEGATION_CONTEXT_BUDGET_CHARS,
) -> tuple[str, tuple[str, ...]]:
    """Build bounded, line-numbered context for safe local extraction."""

    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero.")
    sections: list[str] = []
    sources: list[str] = []
    remaining = max_chars
    for context_file in context_files:
        if remaining <= 0:
            break
        source = context_file.display_path
        header = f"=== SOURCE: {source} ===\n"
        if len(header) >= remaining:
            sections.append(header[:remaining])
            break
        lines = context_file.content.splitlines()
        rendered = [header]
        used = len(header)
        for line_number, line in enumerate(lines, start=1):
            line_text = f"{line_number}: {line}\n"
            marker = f"[source truncated after line {line_number - 1}]"
            if used + len(line_text) + len(marker) > remaining:
                rendered.append(marker)
                used = remaining
                break
            rendered.append(line_text)
            used += len(line_text)
        sections.append("".join(rendered).rstrip())
        sources.append(source)
        remaining -= used
    return "\n\n".join(sections), tuple(sources)


def _has_source_citation(summary: str, sources: Sequence[str]) -> bool:
    """Return whether a local summary cites one of the supplied sources."""

    normalized = summary.replace("\\", "/").lower()
    return any(
        f"[source:{source.replace(chr(92), '/').lower()}:" in normalized for source in sources
    )


def run_local_context_delegation(
    context_files: Sequence[RepoContextFile],
    primary_profile: Any,
    catalog: tuple[Any, ...],
    *,
    client_factory: Callable[[BackendConfig], ChatClient] = create_chat_client,
    max_chars: int = DEFAULT_DELEGATION_CONTEXT_BUDGET_CHARS,
) -> tuple[str | None, str]:
    """Extract source-grounded context locally for injection into a primary prompt."""

    decision = assess_delegation(
        task_type=primary_profile.task_type,
        delegation_kind=DelegationKind.CONTEXT_EXTRACTION,
    )
    if not decision.allowed:
        return None, f"rejected: {decision.reason}"
    delegation_context, sources = build_delegation_context(
        context_files,
        max_chars=max_chars,
    )
    if not sources:
        return None, "skipped: no repository context was loaded"
    plan = plan_delegated_subtask(
        parent_profile=primary_profile,
        catalog=catalog,
        task_type=TaskType.SUMMARIZATION,
        subtask_id="repo_context_extraction",
        description="Extract source-grounded repository constraints for the primary model",
        cost_policy_tier=CostPolicyTier.LOCAL_ONLY,
    )
    config = BackendConfig(
        provider=ProviderKind(plan.execution_plan.target.provider),
        model=plan.execution_plan.target.model,
        base_url=plan.execution_plan.target.base_url,
        timeout_seconds=plan.execution_plan.target.timeout_seconds or 60.0,
    )
    request = AIRequest(
        messages=(
            AIMessage(
                role=MessageRole.USER,
                content=(
                    "Extract only concrete facts needed for the user's coding request from "
                    "the supplied sources. Cite every claim with [source:path:line]. Do not "
                    "make architectural or implementation decisions.\n\n"
                    f"{delegation_context}"
                ),
            ),
        ),
        model=config.model,
        privacy_class=ProviderPrivacyClass(plan.profile.privacy_class.value),
    )
    response = client_factory(config).complete(request)
    summary = response.message.content.strip()
    if not _has_source_citation(summary, sources):
        return None, "rejected: local summary contained no verifiable source citation"
    return summary, f"accepted: {plan.execution_plan.target.route_id}"


def extract_actions(response_text: str) -> tuple[AssistantAction, ...]:
    """Extract assistant action requests from a fenced JSON block or raw JSON."""

    payloads = [match.group(1) for match in _ACTION_BLOCK_PATTERN.finditer(response_text)]
    stripped = response_text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        payloads.append(stripped)

    for payload in payloads:
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        raw_actions = parsed.get("actions")
        if not isinstance(raw_actions, list):
            continue
        actions: list[AssistantAction] = []
        for raw_action in raw_actions:
            if not isinstance(raw_action, dict):
                continue
            action_type = raw_action.get("type")
            if not isinstance(action_type, str):
                continue
            args = {key: value for key, value in raw_action.items() if key != "type"}
            actions.append(AssistantAction(action_type=action_type, args=args))
        return tuple(actions)
    return ()


def execute_actions(
    actions: Sequence[AssistantAction],
    repo_root: Path,
    *,
    input_func: Callable[[str], str] = input,
    allow_outside_files: bool = False,
    command_timeout_seconds: float = 60.0,
) -> tuple[AssistantActionResult, ...]:
    """Execute approved local actions proposed by the assistant."""

    return tuple(
        _execute_action(
            action,
            repo_root,
            input_func=input_func,
            allow_outside_files=allow_outside_files,
            command_timeout_seconds=command_timeout_seconds,
        )
        for action in actions
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a minimal repo-aware coding assistant request."
    )
    parser.add_argument("prompt", nargs="?", help="Coding prompt to prepare or execute.")
    parser.add_argument(
        "--mode",
        choices=CLI_MODES,
        default="ask",
        help=(
            "Execution mode: ask/review answer without actions, implement permits "
            "approved actions, plan never contacts a provider, diagnose prints capabilities."
        ),
    )
    parser.add_argument(
        "--local-capabilities",
        action="store_true",
        help="Print a local machine/provider capability report and exit.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="Repository root. Defaults to the nearest parent containing .git.",
    )
    parser.add_argument(
        "--file",
        action="append",
        type=Path,
        default=[],
        help="Repo file to include in the prompt. May be passed more than once.",
    )
    parser.add_argument(
        "--context-budget-chars",
        type=int,
        default=DEFAULT_CONTEXT_BUDGET_CHARS,
        help=(
            "Maximum characters reserved for all repository context. Use 0 to disable the budget."
        ),
    )
    parser.add_argument(
        "--context-file-budget-chars",
        type=int,
        default=DEFAULT_CONTEXT_FILE_BUDGET_CHARS,
        help="Maximum characters included from any one context file.",
    )
    parser.add_argument(
        "--delegate-context",
        action="store_true",
        help=(
            "Extract bounded, source-cited repository context with a local model "
            "before the primary request."
        ),
    )
    parser.add_argument(
        "--delegation-context-budget-chars",
        type=int,
        default=DEFAULT_DELEGATION_CONTEXT_BUDGET_CHARS,
        help="Maximum characters sent to the local context-extraction model.",
    )
    parser.add_argument(
        "--allow-outside-files",
        action="store_true",
        help=(
            "Explicitly allow selected files and action paths outside the repository "
            "without prompting."
        ),
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("packages/ai_orchestrator/examples/model_catalog.toml"),
        help="Path to a TOML model catalog.",
    )
    parser.add_argument(
        "--privacy",
        choices=[item.value for item in OrchestratorPrivacyClass],
        default=OrchestratorPrivacyClass.LOCAL_ONLY.value,
        help="Privacy class for the request.",
    )
    parser.add_argument(
        "--quality",
        choices=[item.value for item in QualityThreshold],
        default=QualityThreshold.STANDARD.value,
        help="Minimum quality threshold.",
    )
    parser.add_argument(
        "--provider",
        choices=["ollama", "openai", "requesty", "google"],
        help="Hard provider override.",
    )
    parser.add_argument("--route-id", help="Hard access-route override.")
    parser.add_argument(
        "--access-method",
        choices=[item.value for item in AccessMethod],
        help="Hard access-method override, such as local_runtime/provider_api.",
    )
    parser.add_argument("--model", help="Hard model override.")
    parser.add_argument(
        "--cost-policy",
        choices=[item.value for item in CostPolicyTier],
        default=CostPolicyTier.ALLOWANCES_ALLOWED.value,
        help="Maximum billing boundary this task may cross.",
    )
    parser.add_argument(
        "--system",
        help="Additional provider-neutral system instruction appended to the tool prompt.",
    )
    parser.add_argument("--max-latency-seconds", type=float, help="Hard latency constraint.")
    parser.add_argument("--timeout-seconds", type=float, default=60.0, help="Provider timeout.")
    parser.add_argument(
        "--start-ollama",
        action="store_true",
        help="Start `ollama serve` before executing a local Ollama request.",
    )
    parser.add_argument(
        "--ollama-command",
        default="ollama",
        help="Ollama executable used with --start-ollama.",
    )
    parser.add_argument(
        "--ollama-startup-timeout-seconds",
        type=float,
        default=10.0,
        help="Seconds to wait for Ollama to become reachable after starting it.",
    )
    parser.add_argument(
        "--ollama-log-file",
        type=Path,
        default=Path("logs/ollama-serve.log"),
        help=(
            "File for Ollama serve output when --start-ollama is used. "
            "Use an empty value only by calling the Python CLI directly."
        ),
    )
    parser.add_argument(
        "--ollama-profile",
        choices=["gaming", "balanced", "full"],
        help=(
            "Resource profile used when this command starts Ollama. "
            "Restart Ollama for a changed profile to take effect."
        ),
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Also save the complete CLI transcript to this local file.",
    )
    parser.add_argument(
        "--skip-prompt-review",
        action="store_true",
        help="Bypass deterministic prompt review.",
    )
    parser.add_argument(
        "--scrutinize-response",
        action="store_true",
        help=(
            "Run one additional response-quality pass after a completed ask/review "
            "response and include its report in the transcript."
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the provider request. Without this, only print the prepared plan.",
    )
    parser.add_argument(
        "--apply-actions",
        action="store_true",
        help="Execute assistant-proposed local actions after a provider response.",
    )
    parser.add_argument(
        "--native-tools",
        action="store_true",
        help=(
            "Use provider-native tool calling with the ai-agent loop. "
            "Requires --execute; writes and commands ask for approval."
        ),
    )
    parser.add_argument(
        "--max-action-rounds",
        type=int,
        default=3,
        help="Maximum provider/action follow-up rounds when --apply-actions is set.",
    )
    parser.add_argument(
        "--command-timeout-seconds",
        type=float,
        default=60.0,
        help="Timeout for assistant-proposed local commands.",
    )
    args = parser.parse_args(argv)

    if args.mode == "diagnose" or args.local_capabilities:
        snapshot = get_local_provider_capability_snapshot()
        print(json.dumps(_capability_report(snapshot), indent=2, default=str))
        return 0
    if not args.prompt:
        parser.error("prompt is required unless --local-capabilities is used")
    if args.mode == "plan":
        args.execute = False
    if args.mode in {"ask", "review"} and (args.apply_actions or args.native_tools):
        parser.error(f"--mode {args.mode} does not permit file or command actions")
    if args.scrutinize_response and not args.execute:
        parser.error("--scrutinize-response requires --execute")
    if args.scrutinize_response and args.mode not in {"ask", "review"}:
        parser.error("--scrutinize-response is available only in ask or review mode")
    if args.mode == "implement" and not args.execute:
        parser.error("--mode implement requires --execute")
    if args.mode == "implement" and not (args.apply_actions or args.native_tools):
        parser.error("--mode implement requires --apply-actions or --native-tools")

    transcript = None
    if args.log_file is not None:
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        transcript = args.log_file.open("w", encoding="utf-8")
        terminal = sys.stdout
        sys.stdout = _TeeOutput(terminal, transcript)

        def close_transcript() -> None:
            sys.stdout = terminal
            transcript.close()

        atexit.register(close_transcript)
        print(f"transcript_log_file: {args.log_file}")

    repo_root = (args.repo_root or find_repo_root(Path.cwd())).resolve()
    context_budget_chars = None if args.context_budget_chars == 0 else args.context_budget_chars
    context_files = load_prompt_context(
        repo_root,
        args.file,
        allow_outside_files=args.allow_outside_files,
        context_budget_chars=context_budget_chars,
        context_file_budget_chars=args.context_file_budget_chars,
    )
    prompt = build_repo_prompt(args.prompt, context_files)
    catalog = load_model_catalog(args.catalog)
    profile = coding_task_profile(
        privacy_class=OrchestratorPrivacyClass(args.privacy),
        quality_threshold=QualityThreshold(args.quality),
        latency_target=LatencyTarget.INTERACTIVE,
        max_expected_latency_seconds=args.max_latency_seconds,
        cost_policy_tier=CostPolicyTier(args.cost_policy),
        route_id_override=args.route_id,
        access_method_override=(
            AccessMethod(args.access_method) if args.access_method is not None else None
        ),
        provider_override=args.provider,
        model_override=args.model,
    )
    delegated_summary = None
    delegation_status = "disabled"
    if args.delegate_context and args.execute:
        delegated_summary, delegation_status = run_local_context_delegation(
            context_files,
            profile,
            catalog,
            max_chars=args.delegation_context_budget_chars,
        )
        if delegated_summary is not None:
            prompt = f"{prompt}\n\n## Verified local context extraction\n{delegated_summary}"
    elif args.delegate_context:
        delegation_status = "planned: requires --execute"
    ollama_resource_profile = (
        get_ollama_resource_profile(args.ollama_profile)
        if args.ollama_profile is not None
        else None
    )
    result = run_coding_prompt(
        prompt,
        profile,
        catalog,
        review_prompt=not args.skip_prompt_review,
        prompt_for_review=args.prompt,
        timeout_seconds=args.timeout_seconds,
        execute=args.execute and not args.native_tools and args.mode != "plan",
        system_prompt=build_default_system_prompt(args.system),
        start_ollama=args.start_ollama,
        ollama_command=args.ollama_command,
        ollama_startup_timeout_seconds=args.ollama_startup_timeout_seconds,
        ollama_log_path=args.ollama_log_file if args.start_ollama else None,
        ollama_resource_profile=ollama_resource_profile,
    )

    print("=== Repo Coding Assistant ===")
    print(f"mode: {args.mode}")
    print(f"repo_root: {repo_root}")
    print(
        f"context_chars: {sum(len(item.content) for item in context_files)}"
        + (f"/{args.context_budget_chars}" if context_budget_chars is not None else "/unlimited")
    )
    for context_file in context_files:
        print(f"context: {context_file.display_path}")
    print(f"status: {result.orchestration.status.value}")
    print(f"delegation: {delegation_status}")
    execution_status = "planned"
    if result.orchestration.prompt_judge and result.orchestration.prompt_judge.should_refine:
        for issue in result.orchestration.prompt_judge.issues:
            print(f"prompt_review: {issue.severity.value} {issue.code}: {issue.message}")
    if result.config is not None:
        assert result.orchestration.execution_plan is not None
        print(f"route_id: {result.orchestration.execution_plan.target.route_id}")
        print(f"product: {result.orchestration.execution_plan.target.product}")
        print(f"provider: {result.config.provider.value}")
        print(f"model: {result.config.model}")
        print(
            f"cost_policy_tier: {result.orchestration.execution_plan.target.cost_policy_tier.value}"
        )
        if args.start_ollama and result.config.provider is ProviderKind.OLLAMA:
            print(f"ollama_log_file: {args.ollama_log_file}")
            if args.ollama_profile is not None:
                print(f"ollama_profile: {args.ollama_profile}")
            print(
                "ollama_api: "
                + (
                    "reachable"
                    if is_ollama_server_available(result.config.base_url)
                    else "unreachable"
                )
            )
    print("\n=== Assistant response ===")
    assistant_response_text = None
    if args.native_tools and args.execute and result.config is not None:
        native_result = _run_native_agent(
            prompt,
            result.config,
            profile,
            args,
            repo_root,
        )
        assistant_response_text = native_result.response.message.content
        print(assistant_response_text)
        execution_status = (
            "completed_with_tool_errors"
            if any(item.is_error for item in native_result.tool_results)
            else "completed"
        )
    elif result.response is not None:
        assistant_response_text = result.response.message.content
        print(assistant_response_text)
        if args.apply_actions:
            actions_ok = _run_action_loop(
                result.response.message.content,
                prompt,
                profile,
                catalog,
                args,
                repo_root,
            )
            execution_status = "completed" if actions_ok else "completed_with_action_errors"
        else:
            execution_status = "completed"
    elif result.orchestration.failure_reason:
        print(f"failure_reason: {result.orchestration.failure_reason}")
    elif result.orchestration.prompt_judge and result.orchestration.prompt_judge.should_refine:
        for issue in result.orchestration.prompt_judge.issues:
            print(f"prompt_issue: {issue.severity.value} {issue.code}: {issue.message}")
        if result.orchestration.prompt_judge.refined_prompt:
            print(f"suggested_prompt: {result.orchestration.prompt_judge.refined_prompt}")
    if result.orchestration.failure_reason:
        execution_status = "failed"
    if args.scrutinize_response and assistant_response_text is not None:
        print("\n=== Response scrutiny ===")
        scrutiny_failed = False
        try:
            scrutiny_result = run_coding_prompt(
                build_response_scrutiny_prompt(prompt, assistant_response_text),
                profile,
                catalog,
                review_prompt=False,
                timeout_seconds=args.timeout_seconds,
                execute=True,
                system_prompt=_RESPONSE_SCRUTINY_SYSTEM_PROMPT,
                start_ollama=False,
            )
        except ProviderError as exc:
            print("scrutiny_status: failed")
            print(f"scrutiny_failure_reason: {exc}")
            scrutiny_failed = True
        else:
            if scrutiny_result.response is not None:
                print(scrutiny_result.response.message.content)
                print("scrutiny_status: completed")
            else:
                print("scrutiny_status: failed")
                scrutiny_failed = True
                if scrutiny_result.orchestration.failure_reason:
                    print(
                        f"scrutiny_failure_reason: {scrutiny_result.orchestration.failure_reason}"
                    )
        if scrutiny_failed and execution_status == "completed":
            execution_status = "completed_with_scrutiny_errors"
    print(f"execution_status: {execution_status}")
    return 0


def _run_native_agent(
    prompt: str,
    config: BackendConfig,
    profile: Any,
    args: argparse.Namespace,
    repo_root: Path,
) -> Any:
    """Run the provider-native agent loop inside the repository boundary."""
    if args.start_ollama and config.provider is ProviderKind.OLLAMA:
        ensure_ollama_server(
            config.base_url,
            command=args.ollama_command,
            startup_timeout_seconds=args.ollama_startup_timeout_seconds,
            log_path=args.ollama_log_file if args.start_ollama else None,
            resource_profile=(
                get_ollama_resource_profile(args.ollama_profile)
                if args.ollama_profile is not None
                else None
            ),
        )

    def approve(call: Any, category: Any) -> bool:
        answer = input(f"Allow {category.value} tool '{call.name}'? [y/N]: ")
        return answer.strip().lower() in {"y", "yes"}

    client = create_chat_client(config)
    agent = AgentLoop(
        client,
        default_coding_tools(),
        ToolContext(workspace_root=repo_root),
        permissions=PermissionManager(
            policy=PermissionPolicy.interactive(),
            approval_callback=approve,
        ),
        max_iterations=args.max_action_rounds,
    )
    return agent.run(
        prompt,
        system_prompt=build_default_system_prompt(args.system),
        model=config.model,
        privacy_class=PrivacyClass(profile.privacy_class.value),
    )


def _run_action_loop(
    response_text: str,
    original_prompt: str,
    profile: Any,
    catalog: Any,
    args: argparse.Namespace,
    repo_root: Path,
) -> bool:
    round_index = 0
    current_response = response_text
    all_actions_ok = True
    while round_index < args.max_action_rounds:
        actions = extract_actions(current_response)
        if not actions:
            return all_actions_ok
        round_index += 1
        results = execute_actions(
            actions,
            repo_root,
            allow_outside_files=args.allow_outside_files,
            command_timeout_seconds=args.command_timeout_seconds,
        )
        all_actions_ok = all_actions_ok and all(result.ok for result in results)
        print(_format_action_results(results))
        follow_up_prompt = (
            f"{original_prompt}\n\n# Local action results round {round_index}\n"
            f"{_format_action_results(results)}\n\n"
            "Continue from these results. If more local actions are required, emit "
            "another actions JSON block. Otherwise provide the final answer."
        )
        result = run_coding_prompt(
            follow_up_prompt,
            profile,
            catalog,
            review_prompt=not args.skip_prompt_review,
            prompt_for_review=original_prompt,
            timeout_seconds=args.timeout_seconds,
            execute=True,
            system_prompt=build_default_system_prompt(args.system),
            start_ollama=args.start_ollama,
            ollama_command=args.ollama_command,
            ollama_startup_timeout_seconds=args.ollama_startup_timeout_seconds,
            ollama_log_path=args.ollama_log_file if args.start_ollama else None,
        )
        if result.response is None:
            if result.orchestration.failure_reason:
                print(f"failure_reason: {result.orchestration.failure_reason}")
            return False
        current_response = result.response.message.content
        print(current_response)
    return all_actions_ok


def _resolve_context_path(repo_root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _display_path(repo_root: Path, path: Path) -> str:
    if _is_relative_to(path, repo_root):
        return str(path.relative_to(repo_root))
    return str(path)


def _confirm_outside_read(path: Path, *, input_func: Callable[[str], str]) -> bool:
    try:
        answer = input_func(f"Read file outside repository? {path} [y/N]: ")
    except EOFError:
        return False
    return answer.strip().lower() in {"y", "yes"}


def _execute_action(
    action: AssistantAction,
    repo_root: Path,
    *,
    input_func: Callable[[str], str],
    allow_outside_files: bool,
    command_timeout_seconds: float,
) -> AssistantActionResult:
    if action.action_type == "read_file":
        return _read_file_action(action, repo_root, input_func, allow_outside_files)
    if action.action_type == "list_dir":
        return _list_dir_action(action, repo_root, input_func, allow_outside_files)
    if action.action_type == "write_file":
        return _write_file_action(action, repo_root, input_func, allow_outside_files)
    if action.action_type == "run_command":
        return _run_command_action(
            action,
            repo_root,
            input_func,
            allow_outside_files,
            command_timeout_seconds,
        )
    return AssistantActionResult(
        action_type=action.action_type,
        ok=False,
        summary=f"Unsupported action type: {action.action_type}",
    )


def _read_file_action(
    action: AssistantAction,
    repo_root: Path,
    input_func: Callable[[str], str],
    allow_outside_files: bool,
) -> AssistantActionResult:
    path = _action_path(action, repo_root)
    if path is None:
        return AssistantActionResult(action.action_type, False, "read_file requires path.")
    if not _path_allowed(path, repo_root, input_func, allow_outside_files):
        return AssistantActionResult(action.action_type, False, f"Skipped outside path: {path}")
    if not path.is_file():
        return AssistantActionResult(action.action_type, False, f"File not found: {path}")
    content = path.read_text(encoding="utf-8", errors="replace")
    return AssistantActionResult(
        action.action_type,
        True,
        f"Read {_display_path(repo_root, path)}",
        content,
    )


def _list_dir_action(
    action: AssistantAction,
    repo_root: Path,
    input_func: Callable[[str], str],
    allow_outside_files: bool,
) -> AssistantActionResult:
    path = _action_path(action, repo_root) or repo_root
    if not _path_allowed(path, repo_root, input_func, allow_outside_files):
        return AssistantActionResult(action.action_type, False, f"Skipped outside path: {path}")
    if not path.is_dir():
        return AssistantActionResult(action.action_type, False, f"Directory not found: {path}")
    names = sorted(child.name for child in path.iterdir())
    return AssistantActionResult(
        action.action_type,
        True,
        f"Listed {_display_path(repo_root, path)}",
        "\n".join(names),
    )


def _write_file_action(
    action: AssistantAction,
    repo_root: Path,
    input_func: Callable[[str], str],
    allow_outside_files: bool,
) -> AssistantActionResult:
    path = _action_path(action, repo_root)
    content = action.args.get("content")
    if path is None or not isinstance(content, str):
        return AssistantActionResult(
            action.action_type,
            False,
            "write_file requires path and string content.",
        )
    if not _path_allowed(path, repo_root, input_func, allow_outside_files):
        return AssistantActionResult(action.action_type, False, f"Skipped outside path: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return AssistantActionResult(
        action.action_type,
        True,
        f"Wrote {_display_path(repo_root, path)}",
    )


def _run_command_action(
    action: AssistantAction,
    repo_root: Path,
    input_func: Callable[[str], str],
    allow_outside_files: bool,
    command_timeout_seconds: float,
) -> AssistantActionResult:
    command = action.args.get("command")
    if not isinstance(command, str) or not command.strip():
        return AssistantActionResult(action.action_type, False, "run_command requires command.")
    cwd_value = action.args.get("cwd")
    cwd = (
        _resolve_context_path(repo_root, Path(cwd_value))
        if isinstance(cwd_value, str)
        else repo_root
    )
    if not _path_allowed(cwd, repo_root, input_func, allow_outside_files):
        return AssistantActionResult(action.action_type, False, f"Skipped outside cwd: {cwd}")
    try:
        completed = subprocess.run(
            _shell_command(command),
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=command_timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return AssistantActionResult(
            action.action_type,
            False,
            f"Command timed out after {command_timeout_seconds:g}s: {command}",
        )
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    return AssistantActionResult(
        action.action_type,
        completed.returncode == 0,
        f"Command exited {completed.returncode}: {command}",
        output,
    )


def _action_path(action: AssistantAction, repo_root: Path) -> Path | None:
    path_value = action.args.get("path")
    if not isinstance(path_value, str) or not path_value.strip():
        return None
    return _resolve_context_path(repo_root, Path(path_value))


def _path_allowed(
    path: Path,
    repo_root: Path,
    input_func: Callable[[str], str],
    allow_outside_files: bool,
) -> bool:
    if _is_relative_to(path.resolve(), repo_root):
        return True
    if allow_outside_files:
        return True
    return _confirm_outside_read(path.resolve(), input_func=input_func)


def _shell_command(command: str) -> list[str]:
    if os.name == "nt":
        return ["powershell", "-NoProfile", "-Command", command]
    return ["/bin/sh", "-c", command]


def _format_action_results(results: Sequence[AssistantActionResult]) -> str:
    sections: list[str] = ["# Action results"]
    for index, result in enumerate(results, start=1):
        status = "ok" if result.ok else "failed"
        sections.extend(
            [
                "",
                f"## {index}. {result.action_type} ({status})",
                result.summary,
            ]
        )
        if result.output:
            sections.extend(["```text", result.output.rstrip(), "```"])
    return "\n".join(sections)


if __name__ == "__main__":
    sys.exit(main())
