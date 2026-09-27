from __future__ import annotations

import argparse
import atexit
import json
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

# Imports below use the repository's source layout when this module is run directly.
# ruff: noqa: E402, I001
_REPO_ROOT = Path(__file__).resolve().parents[4]
for _package_dir in (
    _REPO_ROOT / "packages" / "ai_provider" / "src",
    _REPO_ROOT / "packages" / "ai_orchestrator" / "src",
    _REPO_ROOT / "packages" / "ai_agent" / "src",
):
    if _package_dir.exists() and str(_package_dir) not in sys.path:
        sys.path.insert(0, str(_package_dir))

from ai_agent import (
    AgentLoop,
    ApprovalPolicyPreset,
    PermissionManager,
    PermissionPolicy,
    ToolCategory,
    ToolContext,
    default_coding_tools,
)
from ai_orchestrator import (
    AccessMethod,
    CostPolicyTier,
    DelegationKind,
    LatencyTarget,
    OrchestrationResult,
    QualityThreshold,
    TaskType,
    assess_delegation,
    load_model_catalog,
    plan_delegated_subtask,
    prepare_execution,
)
from ai_orchestrator import PrivacyClass as OrchestratorPrivacyClass
from ai_provider import (
    AIMessage,
    AIRequest,
    BackendConfig,
    ChatClient,
    MessageRole,
    PrivacyClass,
    ProviderKind,
    ProviderError,
    create_chat_client,
    ensure_ollama_server,
    get_local_provider_capability_snapshot,
    get_ollama_resource_profile,
    is_ollama_server_available,
)
from ai_provider import PrivacyClass as ProviderPrivacyClass

from ai_provider.coding_assist import coding_task_profile, run_coding_prompt
from ai_provider.codex_mcp import setup_project_codex_mcp
from ai_provider.external_agents import (
    ExternalAgentConfig as ExternalAgentConfig,  # noqa: F401 - compatibility export
    ExternalAgentEventSummary,
    build_external_agent_command as _build_external_agent_command,
    build_codex_plugin_command,
    codex_plugin_status_by_name,
    codex_capability_status as _codex_capability_status,  # noqa: F401 - compatibility export
    external_agent_config_from_orchestration as _external_agent_config_from_orchestration,
    external_agent_command,
    external_agent_status as _external_agent_status,
    is_external_agent_access_method as _is_external_agent_access_method,
    parse_external_agent_jsonl as parse_external_agent_jsonl,  # noqa: F401 - compatibility export
    parse_codex_plugin_list,
    run_codex_plugin_operation,
    run_diagnostic_command,
    run_external_agent as _run_external_agent,
)
from ai_provider.repo_context import (
    DEFAULT_CONTEXT_BUDGET_CHARS,
    DEFAULT_CONTEXT_FILE_BUDGET_CHARS,
    RepoContextFile as RepoContextFile,  # noqa: F401 - compatibility export
    build_default_system_prompt,
    build_repo_prompt,
    find_repo_root,
    load_prompt_context,
)
from ai_provider.repo_actions import (
    AssistantAction as AssistantAction,  # noqa: F401 - compatibility export
    AssistantActionResult as AssistantActionResult,  # noqa: F401 - compatibility export
    execute_actions,
    extract_actions,
    format_action_results as _format_action_results,
)
from ai_provider.scrutiny import (
    RESPONSE_SCRUTINY_SYSTEM_PROMPT as _RESPONSE_SCRUTINY_SYSTEM_PROMPT,
    ResponseScrutinyReport as ResponseScrutinyReport,  # noqa: F401 - compatibility export
    build_response_scrutiny_prompt,
    parse_response_scrutiny_report,
)
from ai_provider.transcripts import (
    RunMetrics,
    TeeOutput as _TeeOutput,
    print_external_agent_input as _print_external_agent_input,
    print_model_input as _print_model_input,
    print_run_metrics as _print_run_metrics,
    print_transcript_header as _print_transcript_header,
    start_run_metrics as _start_run_metrics,
    write_transcript_only as _write_transcript_only,
)


DEFAULT_DELEGATION_CONTEXT_BUDGET_CHARS = 6_000
CLI_MODES = ("ask", "review", "implement", "plan", "diagnose")
APPROVAL_POLICY_PRESETS = tuple(item.value for item in ApprovalPolicyPreset)


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
        "external_agents": _external_agent_status(),
    }


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
        "--codex-mcp-setup",
        action="store_true",
        help=(
            "Create or update project-scoped .codex/config.toml so Codex can use "
            "this repository's read/search MCP tools."
        ),
    )
    parser.add_argument(
        "--codex-mcp-register-global",
        action="store_true",
        help=(
            "With --codex-mcp-setup, also run `codex mcp add` to persistently "
            "register the server in the user-level Codex MCP configuration."
        ),
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
    parser.add_argument(
        "--approval-policy",
        choices=APPROVAL_POLICY_PRESETS,
        default=ApprovalPolicyPreset.INTERACTIVE.value,
        help=(
            "Model-neutral action approval preset. read_only denies writes/shell, "
            "interactive asks for writes/shell, workspace_write allows file writes "
            "but denies legacy shell actions, and trusted_local allows local writes/shell."
        ),
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
        "--log-full-prompt",
        action="store_true",
        help=(
            "Include exact system and user prompts in --log-file transcripts. "
            "This can contain repository context and sensitive text."
        ),
    )
    parser.add_argument(
        "--skip-prompt-review",
        action="store_true",
        help="Bypass deterministic prompt review.",
    )
    parser.add_argument(
        "--codex-persist-session",
        action="store_true",
        help=(
            "For Codex CLI routes, omit --ephemeral so Codex can save a resumable session. "
            "This is opt-in because it writes Codex session state outside this repo."
        ),
    )
    parser.add_argument(
        "--codex-resume",
        help=(
            "For Codex CLI routes, resume a previous Codex exec session by id/name, "
            "or pass 'last' for the most recent session."
        ),
    )
    parser.add_argument(
        "--codex-output-last-message",
        type=Path,
        help=(
            "For Codex CLI routes, also ask Codex to write the final assistant message "
            "to this local file via --output-last-message."
        ),
    )
    parser.add_argument(
        "--codex-output-schema",
        type=Path,
        help=(
            "For Codex CLI routes, pass a JSON Schema file to Codex via --output-schema "
            "to constrain the final assistant message."
        ),
    )
    parser.add_argument(
        "--codex-search",
        action="store_true",
        help=(
            "For Codex CLI routes, enable Codex web search for this run. "
            "This is opt-in because it allows external web/search activity."
        ),
    )
    parser.add_argument(
        "--codex-image",
        action="append",
        default=[],
        type=Path,
        metavar="PATH",
        help=(
            "For Codex CLI routes, attach one local image to the initial prompt via "
            "--image. May be repeated."
        ),
    )
    parser.add_argument(
        "--codex-plugin-install",
        action="append",
        default=[],
        metavar="PLUGIN@MARKETPLACE",
        help=(
            "Install one exact Codex plugin selector through `codex plugin add`. "
            "May be repeated. Requires --execute and does not authorize external services."
        ),
    )
    parser.add_argument(
        "--codex-plugin-remove",
        action="append",
        default=[],
        metavar="PLUGIN@MARKETPLACE",
        help=(
            "Remove one exact Codex plugin selector through `codex plugin remove`. "
            "May be repeated. Requires --execute."
        ),
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

    repo_root = (args.repo_root or find_repo_root(Path.cwd())).resolve()
    if args.codex_plugin_install or args.codex_plugin_remove:
        return _run_codex_plugin_management(args=args, repo_root=repo_root, parser=parser)
    if args.codex_mcp_setup:
        try:
            result = setup_project_codex_mcp(
                repo_root,
                register_global=args.codex_mcp_register_global,
            )
        except (FileNotFoundError, RuntimeError, subprocess.TimeoutExpired) as exc:
            print("=== Codex MCP setup ===")
            print(f"repo_root: {repo_root}")
            print("codex_mcp_status: failed")
            print(f"failure_reason: {exc}")
            return 1
        print("=== Codex MCP setup ===")
        print(f"repo_root: {repo_root}")
        print(f"codex_mcp_config: {result.config_path}")
        print(f"codex_mcp_server: {result.server_name}")
        print(f"codex_mcp_command: {result.command}")
        print("codex_mcp_args_json: " + json.dumps(list(result.args)))
        print("codex_mcp_enabled_tools_json: " + json.dumps(list(result.enabled_tools)))
        print(f"codex_mcp_config_created: {result.created}")
        print("codex_mcp_scope: project")
        print(f"codex_mcp_global_registered: {result.global_registered}")
        if result.global_add_stdout:
            print(f"codex_mcp_add_stdout: {result.global_add_stdout}")
        if result.global_add_stderr:
            print(f"codex_mcp_add_stderr: {result.global_add_stderr}")
        return 0
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
    if args.log_full_prompt and args.log_file is None:
        parser.error("--log-full-prompt requires --log-file")
    if args.codex_persist_session and args.codex_resume:
        parser.error("--codex-persist-session cannot be combined with --codex-resume")

    transcript = None
    close_transcript_func: Callable[[], None] | None = None
    if args.log_file is not None:
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        transcript = args.log_file.open("w", encoding="utf-8")
        terminal = sys.stdout
        sys.stdout = _TeeOutput(terminal, transcript)

        def close_transcript() -> None:
            if transcript.closed:
                return
            sys.stdout = terminal
            transcript.close()

        atexit.register(close_transcript)
        close_transcript_func = close_transcript
        print(f"transcript_log_file: {args.log_file}")
        _print_transcript_header(args, argv)

    metrics = _start_run_metrics()
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
    primary_system_prompt = build_default_system_prompt(args.system)
    ollama_resource_profile = (
        get_ollama_resource_profile(args.ollama_profile)
        if args.ollama_profile is not None
        else None
    )
    external_orchestration = prepare_execution(
        prompt,
        profile,
        catalog,
        review_prompt=not args.skip_prompt_review,
        prompt_for_review=args.prompt,
        timeout_seconds=args.timeout_seconds,
    )
    if (
        (args.codex_persist_session or args.codex_resume)
        and external_orchestration.is_ready
        and external_orchestration.execution_plan is not None
        and external_orchestration.execution_plan.target.access_method is not AccessMethod.CODEX_CLI
    ):
        parser.error("--codex-persist-session and --codex-resume require a Codex CLI route")
    if (
        args.codex_output_last_message is not None
        and external_orchestration.is_ready
        and external_orchestration.execution_plan is not None
        and external_orchestration.execution_plan.target.access_method is not AccessMethod.CODEX_CLI
    ):
        parser.error("--codex-output-last-message requires a Codex CLI route")
    if (
        args.codex_output_schema is not None
        and external_orchestration.is_ready
        and external_orchestration.execution_plan is not None
        and external_orchestration.execution_plan.target.access_method is not AccessMethod.CODEX_CLI
    ):
        parser.error("--codex-output-schema requires a Codex CLI route")
    if (
        args.codex_search
        and external_orchestration.is_ready
        and external_orchestration.execution_plan is not None
        and external_orchestration.execution_plan.target.access_method is not AccessMethod.CODEX_CLI
    ):
        parser.error("--codex-search requires a Codex CLI route")
    if (
        args.codex_image
        and external_orchestration.is_ready
        and external_orchestration.execution_plan is not None
        and external_orchestration.execution_plan.target.access_method is not AccessMethod.CODEX_CLI
    ):
        parser.error("--codex-image requires a Codex CLI route")
    if (
        external_orchestration.is_ready
        and external_orchestration.execution_plan is not None
        and _is_external_agent_access_method(
            external_orchestration.execution_plan.target.access_method
        )
    ):
        return _run_external_agent_cli_mode(
            prompt=prompt,
            args=args,
            repo_root=repo_root,
            context_files=context_files,
            context_budget_chars=context_budget_chars,
            orchestration=external_orchestration,
            delegation_status=delegation_status,
            metrics=metrics,
            close_transcript=close_transcript_func,
        )

    if args.log_full_prompt:
        _print_model_input("Primary", system_prompt=primary_system_prompt, prompt=prompt)
    primary_elapsed_seconds = None
    try:
        primary_started = time.perf_counter()
        result = run_coding_prompt(
            prompt,
            profile,
            catalog,
            review_prompt=not args.skip_prompt_review,
            prompt_for_review=args.prompt,
            timeout_seconds=args.timeout_seconds,
            execute=args.execute and not args.native_tools and args.mode != "plan",
            system_prompt=primary_system_prompt,
            start_ollama=args.start_ollama,
            ollama_command=args.ollama_command,
            ollama_startup_timeout_seconds=args.ollama_startup_timeout_seconds,
            ollama_log_path=args.ollama_log_file if args.start_ollama else None,
            ollama_resource_profile=ollama_resource_profile,
        )
        primary_elapsed_seconds = time.perf_counter() - primary_started
    except ProviderError as exc:
        print("=== Repo Coding Assistant ===")
        print(f"mode: {args.mode}")
        print(f"repo_root: {repo_root}")
        print("status: failed")
        print(f"failure_reason: {exc}")
        print("execution_status: failed")
        _print_run_metrics(
            metrics,
            primary_elapsed_seconds=primary_elapsed_seconds,
            primary_response=None,
            scrutiny_elapsed_seconds=None,
            scrutiny_response=None,
        )
        if close_transcript_func is not None:
            close_transcript_func()
        return 1

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
    scrutiny_result = None
    scrutiny_elapsed_seconds = None
    if args.scrutinize_response and assistant_response_text is not None:
        print("\n=== Response scrutiny ===")
        scrutiny_failed = False
        try:
            scrutiny_started = time.perf_counter()
            scrutiny_prompt = build_response_scrutiny_prompt(prompt, assistant_response_text)
            if args.log_full_prompt:
                _print_model_input(
                    "Scrutiny",
                    system_prompt=_RESPONSE_SCRUTINY_SYSTEM_PROMPT,
                    prompt=scrutiny_prompt,
                )
            scrutiny_result = run_coding_prompt(
                scrutiny_prompt,
                profile,
                catalog,
                review_prompt=False,
                timeout_seconds=args.timeout_seconds,
                execute=True,
                system_prompt=_RESPONSE_SCRUTINY_SYSTEM_PROMPT,
                start_ollama=False,
            )
            scrutiny_elapsed_seconds = time.perf_counter() - scrutiny_started
        except ProviderError as exc:
            print("scrutiny_status: failed")
            print(f"scrutiny_failure_reason: {exc}")
            scrutiny_failed = True
        else:
            if scrutiny_result.response is not None:
                scrutiny_text = scrutiny_result.response.message.content
                print(scrutiny_text)
                try:
                    scrutiny_report = parse_response_scrutiny_report(scrutiny_text)
                except ValueError as exc:
                    print("scrutiny_status: invalid")
                    print(f"scrutiny_failure_reason: {exc}")
                    scrutiny_failed = True
                else:
                    print(f"scrutiny_verdict: {scrutiny_report.verdict}")
                    print(f"scrutiny_score: {scrutiny_report.score}")
                    print("scrutiny_status: completed")
                    if scrutiny_report.verdict != "pass" and execution_status == "completed":
                        execution_status = "completed_with_scrutiny_findings"
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
    _print_run_metrics(
        metrics,
        primary_elapsed_seconds=primary_elapsed_seconds,
        primary_response=result.response,
        scrutiny_elapsed_seconds=scrutiny_elapsed_seconds,
        scrutiny_response=scrutiny_result.response if scrutiny_result is not None else None,
    )
    if close_transcript_func is not None:
        close_transcript_func()
    return 0


def _run_codex_plugin_management(
    *,
    args: argparse.Namespace,
    repo_root: Path,
    parser: argparse.ArgumentParser,
) -> int:
    """Run explicit Codex plugin install/remove operations."""

    if not args.execute:
        parser.error("--codex-plugin-install/--codex-plugin-remove require --execute")
    if args.prompt:
        parser.error("plugin management cannot be combined with a prompt request")
    command = external_agent_command(AccessMethod.CODEX_CLI)
    if command is None:
        print("=== Codex plugin management ===")
        print(f"repo_root: {repo_root}")
        print("codex_plugin_status: failed")
        print("failure_reason: Could not find Codex CLI. Set CODEX_COMMAND or install Codex CLI.")
        return 1

    operations: list[tuple[str, str]] = [
        *[("add", selector) for selector in args.codex_plugin_install],
        *[("remove", selector) for selector in args.codex_plugin_remove],
    ]
    try:
        planned_commands = [
            build_codex_plugin_command(command, action, selector) for action, selector in operations
        ]
    except ValueError as exc:
        parser.error(str(exc))

    print("=== Codex plugin management ===")
    print(f"repo_root: {repo_root}")
    print(f"codex_command: {command}")
    print("codex_plugin_auth_boundary: install/remove only; no OAuth or service authorization")
    before = run_diagnostic_command(command, "plugin", "list", timeout_seconds=10.0)
    print("codex_plugin_before_ok: " + str(before["ok"]))
    if before["stdout"]:
        print("codex_plugin_before_stdout:")
        print(before["stdout"])
    if before["stderr"]:
        print("codex_plugin_before_stderr:")
        print(before["stderr"])

    all_ok = True
    for planned_command, (action, selector) in zip(planned_commands, operations, strict=True):
        print(f"codex_plugin_operation: {action} {selector}")
        print("codex_plugin_command_line_json: " + json.dumps(list(planned_command)))
        try:
            result = run_codex_plugin_operation(
                command,
                action=action,
                selector=selector,
                timeout_seconds=args.timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            print("codex_plugin_result_ok: False")
            print(f"codex_plugin_result_error: {exc}")
            all_ok = False
            continue
        print(f"codex_plugin_result_ok: {result.ok}")
        print(f"codex_plugin_result_returncode: {result.returncode}")
        if result.stdout:
            print("codex_plugin_result_stdout:")
            print(result.stdout)
        if result.stderr:
            print("codex_plugin_result_stderr:")
            print(result.stderr)
        all_ok = all_ok and result.ok

    after = run_diagnostic_command(command, "plugin", "list", timeout_seconds=10.0)
    print("codex_plugin_after_ok: " + str(after["ok"]))
    if after["stdout"]:
        print("codex_plugin_after_stdout:")
        print(after["stdout"])
    if after["stderr"]:
        print("codex_plugin_after_stderr:")
        print(after["stderr"])
    if after["ok"]:
        expected_selectors = tuple(selector for _, selector in operations)
        expected_status = codex_plugin_status_by_name(
            parse_codex_plugin_list(after["stdout"]),
            expected_selectors,
        )
        print("codex_plugin_expected_status_json: " + json.dumps(expected_status, sort_keys=True))
        for action, selector in operations:
            status = expected_status[selector]["status"] or ""
            if action == "add" and not status.startswith("installed"):
                all_ok = False
            if action == "remove" and status.startswith("installed"):
                all_ok = False
    print(
        "codex_plugin_next_step: start a new Codex CLI session before using installed skills/tools"
    )
    print(f"execution_status: {'completed' if all_ok else 'failed'}")
    return 0 if all_ok else 1


def _run_external_agent_cli_mode(
    *,
    prompt: str,
    args: argparse.Namespace,
    repo_root: Path,
    context_files: Sequence[RepoContextFile],
    context_budget_chars: int | None,
    orchestration: OrchestrationResult,
    delegation_status: str,
    metrics: RunMetrics,
    close_transcript: Callable[[], None] | None,
) -> int:
    """Run or plan a coding request through an external coding-agent CLI route."""

    assert orchestration.execution_plan is not None
    target = orchestration.execution_plan.target
    print("=== Repo Coding Assistant ===")
    print(f"mode: {args.mode}")
    print(f"repo_root: {repo_root}")
    print(
        f"context_chars: {sum(len(item.content) for item in context_files)}"
        + (f"/{args.context_budget_chars}" if context_budget_chars is not None else "/unlimited")
    )
    for context_file in context_files:
        print(f"context: {context_file.display_path}")
    print(f"status: {orchestration.status.value}")
    print(f"delegation: {delegation_status}")
    print(f"route_id: {target.route_id}")
    print(f"product: {target.product}")
    print(f"provider: {target.provider}")
    print(f"model: {target.model}")
    print(f"access_method: {target.access_method.value}")
    print(f"cost_policy_tier: {target.cost_policy_tier.value}")
    if args.log_full_prompt:
        _print_external_agent_input("Primary", prompt=prompt)

    primary_elapsed_seconds = None
    external_result = None
    execution_status = "planned"
    exit_code = 0
    try:
        config = _external_agent_config_from_orchestration(
            orchestration,
            repo_root=repo_root,
            timeout_seconds=args.timeout_seconds,
            sandbox=_codex_sandbox_for_approval_policy(args.approval_policy),
            codex_persist_session=args.codex_persist_session,
            codex_resume=args.codex_resume,
            output_last_message_path=args.codex_output_last_message,
            output_schema_path=args.codex_output_schema,
            web_search=args.codex_search,
            image_paths=tuple(args.codex_image),
        )
        print(f"external_agent_command: {config.command}")
        print(f"approval_policy: {args.approval_policy}")
        print(f"external_agent_sandbox: {config.sandbox}")
        print(f"external_agent_ephemeral: {config.ephemeral}")
        if config.resume is not None:
            print(f"external_agent_resume: {config.resume}")
        if config.output_last_message_path is not None:
            print(f"external_agent_output_last_message: {config.output_last_message_path}")
        if config.output_schema_path is not None:
            print(f"external_agent_output_schema: {config.output_schema_path}")
        print(f"external_agent_web_search: {config.web_search}")
        if config.image_paths:
            print(
                "external_agent_images_json: "
                + json.dumps([str(path) for path in config.image_paths])
            )
        print("\n=== Assistant response ===")
        if args.execute and args.mode != "plan":
            primary_started = time.perf_counter()
            external_result = _run_external_agent(prompt, config)
            primary_elapsed_seconds = time.perf_counter() - primary_started
            print(f"external_agent_returncode: {external_result.returncode}")
            if external_result.events is not None:
                _print_external_agent_event_summary(external_result.events)
                _write_external_agent_raw_jsonl(external_result.stdout)
                if external_result.events.final_answer:
                    print(external_result.events.final_answer)
                elif external_result.last_message:
                    print(external_result.last_message, end="")
                    if not external_result.last_message.endswith("\n"):
                        print()
                else:
                    print("external_agent_final_answer: unavailable")
            elif external_result.stdout:
                print(external_result.stdout, end="")
                if not external_result.stdout.endswith("\n"):
                    print()
            if external_result.stderr:
                print("\n=== External agent stderr ===")
                stderr_text = _format_external_agent_stderr(external_result.stderr)
                print(stderr_text, end="")
                if not stderr_text.endswith("\n"):
                    print()
            parsed_failure = (
                external_result.events.failure_reason
                if external_result.events is not None
                else None
            )
            execution_status = (
                "completed"
                if external_result.returncode == 0 and parsed_failure is None
                else "failed"
            )
            exit_code = 0 if execution_status == "completed" else external_result.returncode or 1
        else:
            command = _build_external_agent_command(config)
            print("execution: skipped")
            print("external_agent_command_line_json: " + json.dumps(list(command)))
    except (FileNotFoundError, NotImplementedError, subprocess.TimeoutExpired) as exc:
        print("\n=== Assistant response ===")
        print(f"failure_reason: {exc}")
        execution_status = "failed"
        exit_code = 1

    print(f"execution_status: {execution_status}")
    _print_run_metrics(
        metrics,
        primary_elapsed_seconds=primary_elapsed_seconds,
        primary_response=None,
        scrutiny_elapsed_seconds=None,
        scrutiny_response=None,
    )
    if close_transcript is not None:
        close_transcript()
    return exit_code


def _print_external_agent_event_summary(events: ExternalAgentEventSummary) -> None:
    """Print structured external-agent execution metadata."""

    print("external_agent_jsonl_events: parsed")
    print(f"external_agent_command_event_count: {len(events.command_events)}")
    print(f"external_agent_tool_event_count: {len(events.tool_events)}")
    print(f"external_agent_web_search_event_count: {len(events.web_search_events)}")
    print(f"external_agent_file_change_event_count: {len(events.file_change_events)}")
    if events.usage is not None:
        print("external_agent_usage_json: " + json.dumps(events.usage, sort_keys=True))
    if events.failure_reason is not None:
        print(f"external_agent_failure_reason: {events.failure_reason}")
    if events.parse_errors:
        print("external_agent_jsonl_parse_errors_json: " + json.dumps(list(events.parse_errors)))


def _write_external_agent_raw_jsonl(raw_jsonl: str) -> None:
    """Preserve raw external-agent JSONL in transcript logs without console noise."""

    if not raw_jsonl:
        return
    _write_transcript_only("\n=== External agent raw JSONL ===\n")
    _write_transcript_only(raw_jsonl)
    if not raw_jsonl.endswith("\n"):
        _write_transcript_only("\n")


def _format_external_agent_stderr(stderr: str, *, limit: int = 2000) -> str:
    """Bound noisy external-agent stderr while preserving the actionable prefix."""

    if len(stderr) <= limit:
        return stderr
    omitted = len(stderr) - limit
    return (
        stderr[:limit].rstrip()
        + f"\n[external agent stderr truncated: {omitted} characters omitted]\n"
    )


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

    approval_policy = ApprovalPolicyPreset(
        getattr(args, "approval_policy", ApprovalPolicyPreset.INTERACTIVE.value)
    )
    permission_policy = PermissionPolicy.from_approval_preset(approval_policy)
    approval_callback = (
        approve
        if any(
            permission_policy.action_for_category(category).value == "ask_user"
            for category in ToolCategory
        )
        else None
    )
    client = create_chat_client(config)
    agent = AgentLoop(
        client,
        default_coding_tools(),
        ToolContext(workspace_root=repo_root),
        permissions=PermissionManager(
            policy=permission_policy,
            approval_callback=approval_callback,
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
            authorize_action=_legacy_action_authorizer(
                getattr(args, "approval_policy", ApprovalPolicyPreset.INTERACTIVE.value)
            ),
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


def _codex_sandbox_for_approval_policy(approval_policy: str) -> str:
    """Map model-neutral approval presets to supported Codex CLI sandbox modes."""

    if ApprovalPolicyPreset(approval_policy) is ApprovalPolicyPreset.READ_ONLY:
        return "read-only"
    return "workspace-write"


def _legacy_action_authorizer(approval_policy: str) -> Callable[[AssistantAction], bool]:
    """Return an authorizer for legacy fenced-JSON local actions."""

    preset = ApprovalPolicyPreset(approval_policy)

    def authorize(action: AssistantAction) -> bool:
        if action.action_type in {"read_file", "list_dir"}:
            return True
        if action.action_type == "write_file":
            if preset is ApprovalPolicyPreset.READ_ONLY:
                return False
            if preset is ApprovalPolicyPreset.INTERACTIVE:
                return _confirm_legacy_action(action, "write")
            return True
        if action.action_type == "run_command":
            if preset in {
                ApprovalPolicyPreset.READ_ONLY,
                ApprovalPolicyPreset.WORKSPACE_WRITE,
            }:
                return False
            if preset is ApprovalPolicyPreset.INTERACTIVE:
                return _confirm_legacy_action(action, "shell")
            return True
        return preset is ApprovalPolicyPreset.TRUSTED_LOCAL

    return authorize


def _confirm_legacy_action(action: AssistantAction, category: str) -> bool:
    """Ask the user before running an interactive legacy local action."""

    answer = input(f"Allow {category} action '{action.action_type}'? [y/N]: ")
    return answer.strip().lower() in {"y", "yes"}


if __name__ == "__main__":
    sys.exit(main())
