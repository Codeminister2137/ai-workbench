"""Agent-owned repository assistant composition and command execution."""

from __future__ import annotations

import argparse
import atexit
import copy
import json
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from io import TextIOWrapper
from pathlib import Path
from typing import Any

from ai_orchestrator import (
    AccessMethod,
    CostPolicyTier,
    LatencyTarget,
    OrchestrationResult,
    QualityThreshold,
    TaskCapability,
    TaskType,
    derive_subtask_profile,
    load_model_catalog,
    prepare_execution,
)
from ai_orchestrator import PrivacyClass as OrchestratorPrivacyClass
from ai_provider import (
    AIMessage,
    AIRequest,
    BackendConfig,
    MessageRole,
    PrivacyClass,
    ProviderError,
    ProviderErrorCategory,
    ProviderKind,
    create_chat_client,
    ensure_ollama_server,
    get_local_provider_capability_snapshot,
    get_ollama_resource_profile,
    is_ollama_server_available,
)
from ai_provider import (
    OllamaResourceProfile as OllamaResourceProfile,
)
from ai_provider import PrivacyClass as ProviderPrivacyClass  # noqa: F401 - compatibility export
from ai_provider.chat_transcripts import (
    DEFAULT_CHAT_TRANSCRIPT_DB,
    ChatSessionRecord,
    SQLiteChatTranscriptStore,
)
from ai_provider.closeout import FINAL_RESPONSE_INSTRUCTION, format_cli_closeout
from ai_provider.codex_mcp import setup_project_codex_mcp
from ai_provider.coding_assist import (
    backend_config_from_execution_target,
    coding_task_profile,
    run_coding_prompt,
)
from ai_provider.execution_fallback import FallbackSession, external_usage_limit
from ai_provider.external_agents import (
    ExternalAgentConfig as ExternalAgentConfig,  # noqa: F401 - compatibility export
)
from ai_provider.external_agents import (
    ExternalAgentResult,
    build_codex_plugin_command,
    codex_plugin_status_by_name,
    external_agent_command,
    parse_codex_plugin_list,
    run_codex_plugin_operation,
    run_diagnostic_command,
)
from ai_provider.external_agents import (
    build_external_agent_command as _build_external_agent_command,
)
from ai_provider.external_agents import (
    codex_capability_status as _codex_capability_status,  # noqa: F401 - compatibility export
)
from ai_provider.external_agents import (
    external_agent_status as _external_agent_status,
)
from ai_provider.external_agents import (
    is_external_agent_access_method as _is_external_agent_access_method,
)
from ai_provider.external_agents import (
    parse_external_agent_jsonl as parse_external_agent_jsonl,  # noqa: F401 - compatibility export
)
from ai_provider.external_agents import (
    run_external_agent as _run_external_agent,
)
from ai_provider.native_admission import (
    NATIVE_TOOL_EVIDENCE,
    installed_native_identity,
    native_coding_catalog,
    native_tool_incompatibility,
    prepare_native_coding_client,
)
from ai_provider.orchestrated_runs import (
    DEFAULT_ORCHESTRATED_RUN_DB as DEFAULT_ORCHESTRATED_RUN_DB,
)
from ai_provider.orchestrated_runs import (
    OrchestratedStageRecord,
)
from ai_provider.repo_actions import (
    AssistantAction as AssistantAction,  # noqa: F401 - compatibility export
)
from ai_provider.repo_actions import (
    AssistantActionResult as AssistantActionResult,  # noqa: F401 - compatibility export
)
from ai_provider.repo_actions import (
    execute_actions,
    extract_actions,
)
from ai_provider.repo_actions import (
    format_action_results as _format_action_results,
)
from ai_provider.repo_context import (
    DEFAULT_CONTEXT_BUDGET_CHARS as DEFAULT_CONTEXT_BUDGET_CHARS,
)
from ai_provider.repo_context import (
    DEFAULT_CONTEXT_FILE_BUDGET_CHARS as DEFAULT_CONTEXT_FILE_BUDGET_CHARS,
)
from ai_provider.repo_context import (
    RepoContextFile as RepoContextFile,  # noqa: F401 - compatibility export
)
from ai_provider.repo_context import (
    build_default_system_prompt,
    build_native_tool_system_prompt,
    build_repo_prompt,
    find_repo_root,
    load_prompt_context,
)
from ai_provider.scrutiny import (
    RESPONSE_SCRUTINY_SYSTEM_PROMPT as _RESPONSE_SCRUTINY_SYSTEM_PROMPT,
)
from ai_provider.scrutiny import (
    ResponseScrutinyReport as ResponseScrutinyReport,  # noqa: F401 - compatibility export
)
from ai_provider.scrutiny import (
    build_response_scrutiny_prompt,
    parse_response_scrutiny_report,
)
from ai_provider.transcripts import (
    RunMetrics,
)
from ai_provider.transcripts import (
    TeeOutput as _TeeOutput,
)
from ai_provider.transcripts import (
    print_external_agent_input as _print_external_agent_input,
)
from ai_provider.transcripts import (
    print_model_input as _print_model_input,
)
from ai_provider.transcripts import (
    print_run_metrics as _print_run_metrics,
)
from ai_provider.transcripts import (
    print_transcript_header as _print_transcript_header,
)
from ai_provider.transcripts import (
    start_run_metrics as _start_run_metrics,
)
from ai_provider.transcripts import (
    write_transcript_only as _write_transcript_only,
)

from ai_agent import (
    AgentLoop,
    ApprovalPolicyPreset,
    PermissionManager,
    PermissionPolicy,
    ToolCategory,
    ToolContext,
    ToolResult,
    codex_authorization_registry,
    coding_tools_with_delegation,
    default_coding_tools,
)
from ai_agent.chat_context import (
    ChatContextAssembly as ChatContextAssembly,  # noqa: F401 - compatibility export
)
from ai_agent.chat_context import (
    assemble_chat_context as _assemble_chat_context,  # noqa: F401 - compatibility export
)
from ai_agent.chat_context import (
    build_chat_summary_prompt as _build_chat_summary_prompt,  # noqa: F401 - compatibility export
)
from ai_agent.chat_context import (
    messages_total_chars as _messages_total_chars,  # noqa: F401 - compatibility export
)
from ai_agent.chat_context import (
    update_chat_rolling_summary as _update_chat_rolling_summary,  # noqa: F401 - compatibility export
)
from ai_agent.delegation_context import (
    assemble_delegation_context,
)
from ai_agent.external_execution import ExternalExecutionSettings
from ai_agent.external_reporting import (
    activity_preview as _activity_preview,
)
from ai_agent.external_reporting import (
    dedupe_preserving_order as _dedupe_preserving_order,  # noqa: F401 - compatibility export
)
from ai_agent.external_reporting import (
    delegation_status_after_external_agent_events as _delegation_status_after_external_agent_events,  # noqa: F401 - compatibility export
)
from ai_agent.external_reporting import (
    event_has_failed_status as _event_has_failed_status,  # noqa: F401 - compatibility export
)
from ai_agent.external_reporting import (
    event_mentions_codex_collab_delegation as _event_mentions_codex_collab_delegation,  # noqa: F401 - compatibility export
)
from ai_agent.external_reporting import (
    event_mentions_tool as _event_mentions_tool,  # noqa: F401 - compatibility export
)
from ai_agent.external_reporting import (
    external_agent_exception_hint as _external_agent_exception_hint,  # noqa: F401 - compatibility export
)
from ai_agent.external_reporting import (
    external_agent_failure_hint as _external_agent_failure_hint,  # noqa: F401 - compatibility export
)
from ai_agent.external_reporting import (
    extract_pytest_failure_names as _extract_pytest_failure_names,  # noqa: F401 - compatibility export
)
from ai_agent.external_reporting import (
    filter_external_agent_stderr as _filter_external_agent_stderr,  # noqa: F401 - compatibility export
)
from ai_agent.external_reporting import (
    first_actionable_stderr_line as _first_actionable_stderr_line,  # noqa: F401 - compatibility export
)
from ai_agent.external_reporting import (
    format_external_agent_stderr as _format_external_agent_stderr,  # noqa: F401 - compatibility export
)
from ai_agent.external_reporting import (
    print_external_agent_event_summary as _print_external_agent_event_summary,  # noqa: F401 - compatibility export
)
from ai_agent.external_reporting import (
    timeout_output_to_text as _timeout_output_to_text,  # noqa: F401 - compatibility export
)
from ai_agent.external_reporting import (
    write_external_agent_stderr as _write_external_agent_stderr,  # noqa: F401 - compatibility export
)
from ai_agent.repair_workflow import (
    build_orchestrated_repair_prompt as _build_orchestrated_repair_prompt,  # noqa: F401 - compatibility export
)
from ai_agent.repair_workflow import (
    format_validation_failures_for_prompt as _format_validation_failures_for_prompt,  # noqa: F401 - compatibility export
)
from ai_agent.repair_workflow import (
    run_orchestrated_repair_loop as _run_orchestrated_repair_loop,  # noqa: F401 - compatibility export
)
from ai_agent.repair_workflow import (
    validation_failure_fingerprint as _validation_failure_fingerprint,  # noqa: F401 - compatibility export
)
from ai_agent.repair_workflow import (
    validation_stage_needs_repair as _validation_stage_needs_repair,  # noqa: F401 - compatibility export
)
from ai_agent.repo_assistant_args import (
    APPROVAL_POLICY_PRESETS as APPROVAL_POLICY_PRESETS,
)
from ai_agent.repo_assistant_args import (
    CHAT_CONTEXT_MODES as CHAT_CONTEXT_MODES,
)
from ai_agent.repo_assistant_args import (
    CLI_MODES as CLI_MODES,
)
from ai_agent.repo_assistant_args import (
    DEFAULT_CHAT_HISTORY_BUDGET_CHARS as DEFAULT_CHAT_HISTORY_BUDGET_CHARS,
)
from ai_agent.repo_assistant_args import (
    DEFAULT_CHAT_RECENT_MESSAGE_COUNT as DEFAULT_CHAT_RECENT_MESSAGE_COUNT,
)
from ai_agent.repo_assistant_args import (
    DEFAULT_DELEGATION_CONTEXT_BUDGET_CHARS as DEFAULT_DELEGATION_CONTEXT_BUDGET_CHARS,
)
from ai_agent.repo_assistant_args import (
    DEFAULT_VALIDATION_COMMAND as DEFAULT_VALIDATION_COMMAND,
)
from ai_agent.repo_assistant_args import (
    build_argument_parser,
)
from ai_agent.run_tracking import (
    ORCHESTRATED_STAGE_PLAN as _ORCHESTRATED_STAGE_PLAN,  # noqa: F401 - compatibility export
)
from ai_agent.run_tracking import (
    OrchestratedRunTracker as OrchestratedRunTracker,  # noqa: F401 - compatibility export
)
from ai_agent.run_tracking import (
    execution_status_with_validation_stage as _execution_status_with_validation_stage,  # noqa: F401 - compatibility export
)
from ai_agent.run_tracking import (
    execution_status_without_validation_error as _execution_status_without_validation_error,  # noqa: F401 - compatibility export
)
from ai_agent.run_tracking import (
    fallback_details as _fallback_details,  # noqa: F401 - compatibility export
)
from ai_agent.run_tracking import (
    git_status_short as _git_status_short,  # noqa: F401 - compatibility export
)
from ai_agent.run_tracking import (
    persist_orchestrated_run_plan as _persist_orchestrated_run_plan,  # noqa: F401 - compatibility export
)
from ai_agent.run_tracking import (
    print_orchestrated_stage_plan as _print_orchestrated_stage_plan,  # noqa: F401 - compatibility export
)
from ai_agent.run_tracking import (
    remaining_orchestrated_budget_seconds as _remaining_orchestrated_budget_seconds,  # noqa: F401 - compatibility export
)
from ai_agent.run_tracking import (
    validation_status_from_stage as _validation_status_from_stage,  # noqa: F401 - compatibility export
)
from ai_agent.scrutiny_workflow import run_orchestrated_scrutiny
from ai_agent.support_passes import (
    AuxiliaryPanelResult as AuxiliaryPanelResult,
)
from ai_agent.support_passes import (
    run_auxiliary_panel as run_auxiliary_panel,
)
from ai_agent.support_passes import (
    run_local_context_delegation as run_local_context_delegation,
)
from ai_agent.validation import (
    ValidationCommandResult as ValidationCommandResult,  # noqa: F401 - compatibility export
)
from ai_agent.validation import (
    activity_preview_lines as _activity_preview_lines,  # noqa: F401 - compatibility export
)
from ai_agent.validation import (
    default_validation_python as _default_validation_python,  # noqa: F401 - compatibility export
)
from ai_agent.validation import (
    run_validation_commands as _run_validation_commands,  # noqa: F401 - compatibility export
)
from ai_agent.validation import (
    split_validation_command as _split_validation_command,  # noqa: F401 - compatibility export
)
from ai_agent.validation import (
    validation_commands_from_args as _validation_commands_from_args,  # noqa: F401 - compatibility export
)
from ai_agent.validation import (
    validation_results_json as _validation_results_json,  # noqa: F401 - compatibility export
)
from ai_agent.validation import (
    validation_status as _validation_status,  # noqa: F401 - compatibility export
)

_TIMEOUT_OPTION_NAMES = ("--timeout-seconds",)


def _capability_report(snapshot: Any) -> dict[str, Any]:
    """Convert the local capability snapshot into stable JSON-friendly data."""

    external_agents = _external_agent_status()
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
        "external_agents": external_agents,
        "authorization": codex_authorization_registry(external_agents["codex"]).to_dict(),
    }


def build_delegation_context(
    context_files: Sequence[RepoContextFile],
    *,
    max_chars: int = DEFAULT_DELEGATION_CONTEXT_BUDGET_CHARS,
) -> tuple[str, tuple[str, ...]]:
    """Return bounded rendered context and sources with visible lines."""
    context = assemble_delegation_context(context_files, max_chars=max_chars)
    return context.text, context.sources


def _configure_away_mode(
    args: argparse.Namespace,
    argv: Sequence[str] | None,
    parser: argparse.ArgumentParser,
) -> None:
    """Apply deterministic unattended-run budget defaults."""

    if args.away_minutes is None:
        return
    if args.away_minutes <= 0:
        parser.error("--away-minutes must be greater than zero")
    timeout_selected = "timeout_seconds" in (
        getattr(args, "_provided_user_defaults", frozenset())
        | getattr(args, "_configured_user_defaults", frozenset())
    )
    if not timeout_selected and not _argv_has_option(argv, _TIMEOUT_OPTION_NAMES):
        args.timeout_seconds = args.away_minutes * 60


def _argv_has_option(argv: Sequence[str] | None, option_names: Sequence[str]) -> bool:
    """Return whether the raw argv included any of the supplied option names."""

    effective_argv = tuple(argv) if argv is not None else tuple(sys.argv[1:])
    option_prefixes = tuple(f"{name}=" for name in option_names)
    return any(item in option_names or item.startswith(option_prefixes) for item in effective_argv)


def _system_prompt_with_away_budget(system_prompt: str, *, away_minutes: float) -> str:
    """Append foreground budget guidance for unattended CLI runs."""

    return (
        f"{system_prompt.rstrip()}\n\n"
        "Unattended run budget:\n"
        f"- The user may be away for up to {away_minutes:g} minute(s).\n"
        "- Work within the explicit CLI mode, approval policy, privacy class, and "
        "cost policy already supplied.\n"
        "- Use available approved tools and bounded delegate_task calls when they "
        "materially help, but keep subtasks focused and reviewable.\n"
        "- Do not wait for interactive clarification during the run. If a material "
        "product, architecture, privacy, dependency, or data decision blocks safe "
        "progress, stop at that decision boundary and explain the options.\n"
        "- Before finishing, summarize completed work, validation attempted, remaining "
        "risks, and the next action for the returning user."
    )


def _prompt_with_away_budget(prompt: str, *, away_minutes: float) -> str:
    """Add visible unattended-run guidance to the executable prompt."""

    return (
        f"{prompt.rstrip()}\n\n"
        "## Unattended run budget\n"
        f"The user may be away for up to {away_minutes:g} minute(s). Use the available "
        "approved tools and bounded delegation where useful, stay within the explicit "
        "CLI approval/privacy/cost boundaries, and stop at any material decision boundary "
        "that requires user input."
    )


def _execution_status_with_auxiliary_result(
    execution_status: str,
    auxiliary_status: str | None,
) -> str:
    """Preserve successful implementation status while surfacing auxiliary failures."""

    if execution_status == "completed" and auxiliary_status not in (None, "completed"):
        return "completed_with_auxiliary_errors"
    return execution_status


def _print_cli_closeout(
    *,
    args: argparse.Namespace,
    response_text: str | None,
    status: str,
    execution_status: str,
    validation_stage: OrchestratedStageRecord | None = None,
    failure_reason: str | None = None,
) -> None:
    """Print the same evidence-bounded summary for every CLI execution route."""

    fallback_attempts = _fallback_details(args).get("fallback_attempts", [])
    if not isinstance(fallback_attempts, list):
        fallback_attempts = []
    print(
        format_cli_closeout(
            response_text=response_text,
            status=status,
            execution_status=execution_status,
            validation_details=validation_stage.details if validation_stage is not None else None,
            fallback_attempts=fallback_attempts,
            failure_reason=failure_reason,
        ),
        end="",
    )


def _system_prompt_with_final_response_contract(system_prompt: str) -> str:
    return f"{system_prompt.rstrip()}\n\n{FINAL_RESPONSE_INSTRUCTION}"


def _run_orchestrated_scrutiny(
    *,
    args: argparse.Namespace,
    tracker: OrchestratedRunTracker,
    repo_root: Path,
    profile: Any,
    catalog: tuple[Any, ...],
    validation_stage: OrchestratedStageRecord | None,
    assistant_response_text: str | None,
    execution_status: str,
    deadline: float | None,
) -> str:
    """Compose reusable scrutiny with the CLI's existing provider hooks."""
    return run_orchestrated_scrutiny(
        args=args,
        tracker=tracker,
        repo_root=repo_root,
        profile=profile,
        catalog=catalog,
        validation_stage=validation_stage,
        assistant_response_text=assistant_response_text,
        execution_status=execution_status,
        deadline=deadline,
        coding_runner=run_coding_prompt,
        client_factory=create_chat_client,
    )


def _resolve_chat_db_path(args: argparse.Namespace, repo_root: Path) -> Path:
    path = Path(args.chat_db)
    if path.is_absolute():
        return path
    return repo_root / path


def _resolve_chat_session(
    *,
    store: SQLiteChatTranscriptStore,
    args: argparse.Namespace,
    repo_root: Path,
) -> tuple[ChatSessionRecord, bool]:
    if args.chat_session is None or args.chat_session == "new":
        return (
            store.create_session(
                repo_root=repo_root,
                title=args.chat_title or args.prompt or "Untitled chat",
                privacy_class=args.privacy,
            ),
            True,
        )
    if args.chat_session == "last":
        session = store.latest_session(repo_root=repo_root)
        if session is None:
            raise KeyError("no previous chat session exists for this repository")
        return session, False
    session = store.get_session(args.chat_session)
    if session is None:
        raise KeyError(f"chat session does not exist: {args.chat_session}")
    return session, False


def _print_chat_sessions(sessions: Sequence[ChatSessionRecord]) -> None:
    print("=== Repo Assistant Chat Sessions ===")
    if not sessions:
        print("chat_sessions: none")
        return
    for session in sessions:
        print(
            "chat_session: "
            f"{session.session_id} "
            f"updated_at={session.updated_at_utc} "
            f"privacy={session.privacy_class} "
            f"title={session.title}"
        )


def _run_chat_mode(
    *,
    args: argparse.Namespace,
    repo_root: Path,
    prompt: str,
    primary_system_prompt: str,
    profile: Any,
    orchestration: OrchestrationResult,
    metrics: RunMetrics,
    close_transcript: Callable[[], None] | None,
) -> int:
    """Run one persisted provider-neutral chat turn."""

    store = SQLiteChatTranscriptStore(_resolve_chat_db_path(args, repo_root))
    if args.chat_list:
        _print_chat_sessions(store.list_sessions(limit=args.chat_list_limit))
        if close_transcript is not None:
            close_transcript()
        return 0
    if not args.execute:
        parser_status = "planned"
        print("=== Repo Assistant Chat ===")
        print(f"mode: {args.mode}")
        print(f"repo_root: {repo_root}")
        print(f"chat_db: {store.path}")
        print("chat_execution: not_started")
        print("chat_skip_reason: chat mode requires --execute to call a provider")
        print(f"execution_status: {parser_status}")
        _print_run_metrics(
            metrics,
            primary_elapsed_seconds=None,
            primary_response=None,
            scrutiny_elapsed_seconds=None,
            scrutiny_response=None,
        )
        if close_transcript is not None:
            close_transcript()
        return 0
    if not orchestration.is_ready or orchestration.execution_plan is None:
        print("=== Repo Assistant Chat ===")
        print(f"mode: {args.mode}")
        print(f"repo_root: {repo_root}")
        print(f"chat_db: {store.path}")
        print("status: failed")
        print(f"failure_reason: {orchestration.failure_reason}")
        print("execution_status: failed")
        if close_transcript is not None:
            close_transcript()
        return 1
    if _is_external_agent_access_method(orchestration.execution_plan.target.access_method):
        print("=== Repo Assistant Chat ===")
        print(f"mode: {args.mode}")
        print(f"repo_root: {repo_root}")
        print("status: failed")
        print("failure_reason: chat mode currently supports provider API/local runtime routes only")
        print("execution_status: failed")
        if close_transcript is not None:
            close_transcript()
        return 1

    try:
        session, created = _resolve_chat_session(store=store, args=args, repo_root=repo_root)
    except KeyError as exc:
        print("=== Repo Assistant Chat ===")
        print(f"mode: {args.mode}")
        print(f"repo_root: {repo_root}")
        print(f"chat_db: {store.path}")
        print("status: failed")
        print(f"failure_reason: {exc}")
        print("execution_status: failed")
        if close_transcript is not None:
            close_transcript()
        return 1

    existing_messages = store.list_messages(session.session_id)
    if created and primary_system_prompt:
        store.append_message(
            session.session_id,
            role=MessageRole.SYSTEM,
            content=primary_system_prompt,
            metadata={"source": "repo_assistant_system_prompt"},
        )
        existing_messages = store.list_messages(session.session_id)
    user_message = store.append_message(
        session.session_id,
        role=MessageRole.USER,
        content=prompt,
        metadata={
            "original_prompt": args.prompt,
            "selected_files": [str(path) for path in args.file],
        },
    )
    config = backend_config_from_execution_target(orchestration.execution_plan.target)
    privacy_class = PrivacyClass(profile.privacy_class.value)
    primary_elapsed_seconds = None
    request = AIRequest(
        messages=(),
        model=config.model,
        privacy_class=privacy_class,
        metadata={
            "task_type": profile.task_type.value,
            "chat_session_id": session.session_id,
            "orchestrator_selected_provider": config.provider.value,
            "orchestrator_selected_model": config.model,
        },
    )
    try:
        primary_started = time.perf_counter()
        if args.start_ollama and config.provider is ProviderKind.OLLAMA:
            ollama_resource_profile = (
                get_ollama_resource_profile(args.ollama_profile)
                if args.ollama_profile is not None
                else None
            )
            ensure_ollama_server(
                config.base_url,
                command=args.ollama_command,
                startup_timeout_seconds=args.ollama_startup_timeout_seconds,
                log_path=args.ollama_log_file,
                resource_profile=ollama_resource_profile,
            )
        client = create_chat_client(config)
        context = _assemble_chat_context(
            store=store,
            session=session,
            messages=(*existing_messages, user_message),
            client=client,
            config=config,
            privacy_class=privacy_class,
            mode=args.chat_context_mode,
            budget_chars=args.chat_history_budget_chars,
            recent_message_count=args.chat_recent_message_count,
        )
        request = AIRequest(
            messages=context.messages,
            model=config.model,
            privacy_class=privacy_class,
            metadata={
                **request.metadata,
                "chat_context_mode": context.mode,
                "chat_context_summary_used": context.summary_used,
                "chat_context_summary_updated": context.summary_updated,
                "chat_context_raw_message_count": context.raw_message_count,
                "chat_context_omitted_message_count": context.omitted_message_count,
                "chat_context_total_chars": context.total_chars,
            },
        )
        if args.log_full_prompt:
            rendered_prompt = "\n\n".join(
                f"{message.role.value}:\n{message.content}" for message in request.messages
            )
            _print_model_input("Chat", system_prompt=primary_system_prompt, prompt=rendered_prompt)
        response = client.complete(request)
        primary_elapsed_seconds = time.perf_counter() - primary_started
    except ProviderError as exc:
        print("=== Repo Assistant Chat ===")
        print(f"mode: {args.mode}")
        print(f"repo_root: {repo_root}")
        print(f"chat_db: {store.path}")
        print(f"chat_session_id: {session.session_id}")
        print("status: failed")
        print(f"failure_reason: {exc}")
        print("execution_status: failed")
        _print_cli_closeout(
            args=args,
            response_text=None,
            status="failed",
            execution_status="failed",
            failure_reason=str(exc),
        )
        _print_run_metrics(
            metrics,
            primary_elapsed_seconds=primary_elapsed_seconds,
            primary_response=None,
            scrutiny_elapsed_seconds=None,
            scrutiny_response=None,
        )
        if close_transcript is not None:
            close_transcript()
        return 1

    store.append_message(
        session.session_id,
        role=MessageRole.ASSISTANT,
        content=response.message.content,
        provider=response.backend.provider,
        model=response.backend.model,
        metadata={
            "finish_reason": response.finish_reason.value,
            "usage_source": response.usage.source.value,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.total_tokens,
            "latency_ms": response.latency_ms,
        },
    )
    message_count = len(store.list_messages(session.session_id))

    print("=== Repo Assistant Chat ===")
    print(f"mode: {args.mode}")
    print(f"repo_root: {repo_root}")
    print(f"chat_db: {store.path}")
    print(f"chat_session_id: {session.session_id}")
    print(f"chat_session_created: {created}")
    print(f"chat_message_count: {message_count}")
    print(f"chat_context_mode: {context.mode}")
    print(f"chat_context_summary_used: {context.summary_used}")
    print(f"chat_context_summary_updated: {context.summary_updated}")
    print(f"chat_context_raw_message_count: {context.raw_message_count}")
    print(f"chat_context_omitted_message_count: {context.omitted_message_count}")
    print(f"chat_context_total_chars: {context.total_chars}")
    print(f"provider: {response.backend.provider}")
    print(f"model: {response.backend.model}")
    print("status: ready")
    print("execution_status: completed")
    _print_run_metrics(
        metrics,
        primary_elapsed_seconds=primary_elapsed_seconds,
        primary_response=response,
        scrutiny_elapsed_seconds=None,
        scrutiny_response=None,
    )
    _print_cli_closeout(
        args=args,
        response_text=response.message.content,
        status="ready",
        execution_status="completed",
    )
    if close_transcript is not None:
        close_transcript()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Optionally bind a durable session to this foreground invocation."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")

    from ai_provider.coding_sessions import ACTIVE_SESSION, CodingSession

    parser = build_argument_parser()
    parsed = parser.parse_args(argv)
    if not parsed.coding_session:
        if parsed.session_decision or parsed.coding_session_reconciled:
            parser.error("Session decisions/reconciliation require --coding-session")
        if parsed.shared_tools == "coding" and parsed.execute:
            from ai_provider.foreground_tools import ACTIVE_FOREGROUND, ForegroundTools

            root = parsed.repo_root.resolve() if parsed.repo_root else find_repo_root(Path.cwd())
            foreground = ForegroundTools(root)
            foreground_token = ACTIVE_FOREGROUND.set(foreground)
            try:
                return _main(argv)
            finally:
                try:
                    foreground.close()
                finally:
                    ACTIVE_FOREGROUND.reset(foreground_token)
        return _main(argv)
    if not parsed.execute or parsed.mode not in {"ask", "review", "implement"}:
        parser.error("--coding-session requires an executed ask/review/implement request")
    root = parsed.repo_root.resolve() if parsed.repo_root else find_repo_root(Path.cwd())
    from ai_provider.user_config import apply_user_defaults, load_user_config

    config_path = parsed.user_config or root / "user-config.toml"
    try:
        user_config = load_user_config(config_path, required=parsed.user_config is not None)
    except (OSError, ValueError, TypeError) as exc:
        parser.error(f"Invalid user config {config_path}: {exc}")
    apply_user_defaults(parsed, user_config)
    effective_cost_policy = parsed.cost_policy or user_config.cost_policy.value
    database = parsed.coding_session_db
    if not database.is_absolute():
        database = root / database
    try:
        session = CodingSession.open(
            database,
            parsed.coding_session,
            root,
            parsed.prompt or "",
            parsed.session_decision,
            reconciled=parsed.coding_session_reconciled,
            privacy_class=parsed.privacy,
            cost_policy=effective_cost_policy,
        )
    except (ValueError, OSError) as exc:
        print(f"failure_reason: {exc}")
        return 1
    print(f"coding_session_id: {session.session_id}")
    token = ACTIVE_SESSION.set(session)
    from ai_provider.foreground_tools import ACTIVE_FOREGROUND, ForegroundTools

    foreground = ForegroundTools(root, session)
    foreground_token = ACTIVE_FOREGROUND.set(foreground)
    finished = False
    try:
        status = _main(argv)
        finished = True
        session.status("completed" if status == 0 else "failed")
        return status
    finally:
        try:
            foreground.close()
            for handle in session.supervisor.processes:
                session.observe_process(session.supervisor.status(handle))
        finally:
            if not finished:
                session.status("interrupted")
            ACTIVE_SESSION.reset(token)
            ACTIVE_FOREGROUND.reset(foreground_token)


def _main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = build_argument_parser()
    from ai_provider.research_execution import validate_research_arguments

    args = parser.parse_args(argv)

    repo_root = (args.repo_root or find_repo_root(Path.cwd())).resolve()
    from ai_provider.user_config import load_user_config

    config_path = args.user_config or repo_root / "user-config.toml"
    try:
        user_config = load_user_config(config_path, required=args.user_config is not None)
    except (OSError, ValueError, TypeError) as exc:
        parser.error(f"Invalid user config {config_path}: {exc}")
    from ai_provider.user_config import apply_user_defaults

    apply_user_defaults(args, user_config)
    if args.cost_policy is None:
        args.cost_policy = user_config.cost_policy.value
    args.fallback_enabled = user_config.fallback_enabled
    from ai_orchestrator.fallback import FallbackQualityPolicy

    args.fallback_quality_policy = FallbackQualityPolicy(
        args.fallback_quality_policy or user_config.fallback_quality_policy
    )
    if args.list_skills:
        if any(
            (
                args.execute,
                args.fallback_readiness,
                args.local_capabilities,
                args.start_ollama,
                args.codex_login,
                args.codex_login_device,
                args.codex_plugin_install,
                args.codex_plugin_remove,
                args.codex_mcp_setup,
                args.codex_mcp_register_global,
                args.skill,
            )
        ):
            parser.error(
                "--list-skills cannot be combined with execution, setup, or selected skills"
            )
        return _print_skill_discovery(args, repo_root)
    if args.fallback_readiness:
        if any(
            (
                args.execute,
                args.start_ollama,
                args.codex_login,
                args.codex_login_device,
                args.codex_plugin_install,
                args.codex_plugin_remove,
                args.codex_mcp_setup,
                args.codex_mcp_register_global,
            )
        ):
            parser.error("--fallback-readiness cannot be combined with execution or setup actions")
        if args.native_tools and args.no_native_tools:
            parser.error("--native-tools cannot be combined with --no-native-tools")
        if args.codex_persist_session and args.codex_resume:
            parser.error("--codex-persist-session cannot be combined with --codex-resume")
        if args.skill and not args.shared_tools:
            args.shared_tools = "inspection"
        if args.shared_tools:
            if args.apply_actions or args.no_native_tools or args.codex_mcp_tools:
                parser.error("--shared-tools conflicts with legacy action or Codex MCP settings")
            if args.tool_profile != "coding":
                parser.error("--shared-tools inspection cannot be combined with research tools")
            if args.shared_tools == "inspection":
                args.approval_policy = "read_only"
        return _print_fallback_readiness(args, repo_root)
    if args.codex_login or args.codex_login_device:
        return _run_codex_login(args=args, repo_root=repo_root, parser=parser)
    if args.codex_plugin_install or args.codex_plugin_remove:
        return _run_codex_plugin_management(args=args, repo_root=repo_root, parser=parser)
    if args.codex_mcp_setup:
        try:
            setup_result = setup_project_codex_mcp(
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
        print(f"codex_mcp_config: {setup_result.config_path}")
        print(f"codex_mcp_server: {setup_result.server_name}")
        print(f"codex_mcp_command: {setup_result.command}")
        print("codex_mcp_args_json: " + json.dumps(list(setup_result.args)))
        print("codex_mcp_enabled_tools_json: " + json.dumps(list(setup_result.enabled_tools)))
        print(f"codex_mcp_config_created: {setup_result.created}")
        print("codex_mcp_scope: project")
        print(f"codex_mcp_global_registered: {setup_result.global_registered}")
        if setup_result.global_add_stdout:
            print(f"codex_mcp_add_stdout: {setup_result.global_add_stdout}")
        if setup_result.global_add_stderr:
            print(f"codex_mcp_add_stderr: {setup_result.global_add_stderr}")
        return 0
    if args.mode == "diagnose" or args.local_capabilities:
        snapshot = get_local_provider_capability_snapshot()
        print(json.dumps(_capability_report(snapshot), indent=2, default=str))
        return 0
    if args.chat_list and args.mode != "chat":
        parser.error("--chat-list requires --mode chat")
    if args.chat_list_limit <= 0:
        parser.error("--chat-list-limit must be greater than zero")
    if args.chat_history_budget_chars < 0:
        parser.error("--chat-history-budget-chars must be zero or greater")
    if args.chat_recent_message_count <= 0:
        parser.error("--chat-recent-message-count must be greater than zero")
    if args.mode != "chat" and (
        args.chat_session is not None
        or args.chat_title is not None
        or args.chat_db != DEFAULT_CHAT_TRANSCRIPT_DB
        or args.chat_context_mode != "rolling_summary"
        or args.chat_history_budget_chars != DEFAULT_CHAT_HISTORY_BUDGET_CHARS
        or args.chat_recent_message_count != DEFAULT_CHAT_RECENT_MESSAGE_COUNT
    ):
        parser.error("--chat-* options require --mode chat")
    if not args.prompt and not (args.mode == "chat" and args.chat_list):
        parser.error("prompt is required unless --local-capabilities is used")
    if args.mode == "plan":
        args.execute = False
    _configure_away_mode(args, argv, parser)
    if args.orchestrated and args.away_minutes is None:
        parser.error("--orchestrated requires --away-minutes")
    if args.validation_timeout_seconds <= 0:
        parser.error("--validation-timeout-seconds must be greater than zero")
    if args.max_repair_cycles < -1:
        parser.error("--max-repair-cycles must be -1 or greater")
    if args.native_tools and args.no_native_tools:
        parser.error("--native-tools cannot be combined with --no-native-tools")
    if args.skill and not args.shared_tools:
        args.shared_tools = "inspection"
    if args.shared_tools:
        if args.apply_actions or args.no_native_tools or args.codex_mcp_tools:
            parser.error("--shared-tools conflicts with legacy action or Codex MCP settings")
        if args.tool_profile != "coding":
            parser.error("--shared-tools inspection cannot be combined with research tools")
        if args.shared_tools == "inspection":
            args.approval_policy = "read_only"
    use_native_tools = (
        args.native_tools
        or bool(args.shared_tools)
        or (args.mode == "implement" and args.execute and not args.no_native_tools)
    )
    args.native_tools = use_native_tools
    validate_research_arguments(args, repo_root, parser)
    if (
        args.mode in {"ask", "review"}
        and (args.apply_actions or args.native_tools)
        and not args.shared_tools
    ):
        parser.error(f"--mode {args.mode} does not permit file or command actions")
    if args.scrutinize_response and not args.execute:
        parser.error("--scrutinize-response requires --execute")
    if args.scrutinize_response and args.mode not in {"ask", "review"}:
        parser.error("--scrutinize-response is available only in ask or review mode")
    if args.mode == "implement" and not args.execute:
        parser.error("--mode implement requires --execute")
    if args.mode == "implement" and not (
        args.apply_actions or args.native_tools or args.no_native_tools
    ):
        parser.error("--mode implement requires --apply-actions or native tools")
    if args.mode == "chat" and (args.apply_actions or args.native_tools):
        parser.error("--mode chat does not permit file or command actions")
    if args.mode == "chat" and args.orchestrated:
        parser.error("--mode chat cannot be combined with --orchestrated")
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

    if args.mode == "chat" and args.chat_list:
        store = SQLiteChatTranscriptStore(_resolve_chat_db_path(args, repo_root))
        _print_chat_sessions(store.list_sessions(limit=args.chat_list_limit))
        if close_transcript_func is not None:
            close_transcript_func()
        return 0

    metrics = _start_run_metrics()
    context_budget_chars = None if args.context_budget_chars == 0 else args.context_budget_chars
    try:
        context_files = load_prompt_context(
            repo_root,
            args.file,
            allow_outside_files=args.allow_outside_files,
            context_budget_chars=context_budget_chars,
            context_file_budget_chars=args.context_file_budget_chars,
            instruction_budget_chars=args.instruction_budget_chars,
            diagnostic=print,
        )
    except (ValueError, OSError) as exc:
        print(f"failure_reason: {exc}")
        print("execution_status: failed")
        if close_transcript_func is not None:
            close_transcript_func()
        return 1
    prompt = build_repo_prompt(args.prompt, context_files)
    from ai_provider.coding_sessions import ACTIVE_SESSION

    active_session = ACTIVE_SESSION.get()
    if active_session is not None:
        prompt += "\n\n" + active_session.handoff()
    required_files = tuple(item for item in context_files if item.required_instruction)
    args.required_context = (
        build_repo_prompt("", required_files).partition("# Repository context\n")[2]
        if required_files
        else ""
    )
    args.skill_instructions = ""
    if args.shared_tools:
        from ai_agent.skills import load_development_skills, skill_prompt
        from ai_agent.tool_profiles import shared_tool_profile

        try:
            skills = load_development_skills(
                args.skill,
                [path if path.is_absolute() else repo_root / path for path in args.skill_dir]
                if args.skill_dir
                else [repo_root / ".agents/skills", repo_root / "packages/ai_agent/skills"],
                available_tools=frozenset(shared_tool_profile(args.shared_tools).tool_names),
            )
        except (ValueError, OSError) as exc:
            print(f"failure_reason: {exc}")
            if close_transcript_func is not None:
                close_transcript_func()
            return 1
        if skills:
            args.skill_instructions = skill_prompt(skills)
            prompt += "\n\n" + args.skill_instructions
        print(f"shared_tool_profile: {args.shared_tools}")
        print("selected_skills: " + (", ".join(skill.name for skill in skills) or "none"))
    if args.away_minutes is not None:
        prompt = _prompt_with_away_budget(prompt, away_minutes=args.away_minutes)
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
    if args.tool_profile == "research":
        profile = replace(
            profile,
            task_type=TaskType.GENERAL,
            required_capabilities=frozenset({TaskCapability.CHAT, TaskCapability.TOOLS}),
        )
    elif args.native_tools:
        catalog = native_coding_catalog(catalog, profile)
    delegation_status = "disabled"
    primary_system_prompt = build_default_system_prompt(
        args.system,
        actions_enabled=args.apply_actions,
    )
    if args.tool_profile == "research":
        from ai_provider.research_execution import RESEARCH_SYSTEM_PROMPT

        primary_system_prompt = RESEARCH_SYSTEM_PROMPT + ("\n" + args.system if args.system else "")
    if args.away_minutes is not None:
        primary_system_prompt = _system_prompt_with_away_budget(
            primary_system_prompt,
            away_minutes=args.away_minutes,
        )
    primary_system_prompt = _system_prompt_with_final_response_contract(primary_system_prompt)
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
    args.fallback_session = None
    if (
        args.tool_profile == "research"
        and external_orchestration.execution_plan is not None
        and _is_external_agent_access_method(
            external_orchestration.execution_plan.target.access_method
        )
    ):
        parser.error(
            "research tools require a provider-native executor; external clients own their tools"
        )
    if (
        args.execute
        and args.mode != "plan"
        and args.mode != "chat"
        and external_orchestration.execution_plan is not None
    ):
        args.fallback_session = FallbackSession(
            profile,
            catalog,
            external_orchestration.execution_plan.target,
            compatible=lambda target: _fallback_target_compatible(target, args, repo_root),
            incompatibility_reason=lambda target: _fallback_target_incompatibility(
                target, args, repo_root, probe_provider=False
            ),
            enabled=args.fallback_enabled,
            quality_policy=args.fallback_quality_policy,
            save_handoff=lambda summary: _save_fallback_handoff(
                repo_root, {"objective": args.prompt or "", **summary}
            ),
        )
        if args.away_minutes:
            args.fallback_session.deadline = time.perf_counter() + args.away_minutes * 60
        if not args.fallback_session.primary_ready:
            print("failure_reason: Sign into the primary client before execution; no task started.")
            print("execution_status: failed")
            if close_transcript_func is not None:
                close_transcript_func()
            return 1
    if args.delegate_context and args.execute:
        delegated_summary, delegation_status = run_local_context_delegation(
            context_files,
            profile,
            catalog,
            max_chars=args.delegation_context_budget_chars,
            progress_callback=print,
        )
        if delegated_summary is not None:
            prompt = f"{prompt}\n\n## Local context with source references\n{delegated_summary}"
            external_orchestration = replace(external_orchestration, original_prompt=prompt)
    elif args.delegate_context:
        delegation_status = "planned: requires --execute"
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
        args.codex_mcp_tools
        and external_orchestration.is_ready
        and external_orchestration.execution_plan is not None
        and external_orchestration.execution_plan.target.access_method is not AccessMethod.CODEX_CLI
    ):
        parser.error("--codex-mcp-tools requires a Codex CLI route")
    if (
        args.codex_image
        and external_orchestration.is_ready
        and external_orchestration.execution_plan is not None
        and external_orchestration.execution_plan.target.access_method is not AccessMethod.CODEX_CLI
    ):
        parser.error("--codex-image requires a Codex CLI route")
    if args.mode == "chat":
        return _run_chat_mode(
            args=args,
            repo_root=repo_root,
            prompt=prompt,
            primary_system_prompt=primary_system_prompt,
            profile=profile,
            orchestration=external_orchestration,
            metrics=metrics,
            close_transcript=close_transcript_func,
        )
    if (
        external_orchestration.is_ready
        and external_orchestration.execution_plan is not None
        and _is_external_agent_access_method(
            external_orchestration.execution_plan.target.access_method
        )
    ):
        if (
            external_orchestration.execution_plan.target.access_method is AccessMethod.CODEX_CLI
            and not getattr(args, "shared_tools", None)
            and _prompt_requests_git_metadata_write(args.prompt)
            and ApprovalPolicyPreset(args.approval_policy) is not ApprovalPolicyPreset.TRUSTED_LOCAL
        ):
            parser.error(
                "Codex CLI requests that write Git metadata, such as git add or git commit, "
                "require --approval-policy trusted_local so the run can use Codex "
                "danger-full-access."
            )
        return _run_external_agent_cli_mode(
            prompt=prompt,
            system_prompt=primary_system_prompt,
            args=args,
            repo_root=repo_root,
            profile=profile,
            catalog=catalog,
            context_files=context_files,
            context_budget_chars=context_budget_chars,
            orchestration=external_orchestration,
            delegation_status=delegation_status,
            metrics=metrics,
            close_transcript=close_transcript_func,
        )

    if args.native_tools and args.tool_profile != "research":
        primary_system_prompt = build_native_tool_system_prompt(args.system)
        if args.away_minutes is not None:
            primary_system_prompt = _system_prompt_with_away_budget(
                primary_system_prompt,
                away_minutes=args.away_minutes,
            )
        primary_system_prompt = _system_prompt_with_final_response_contract(primary_system_prompt)
    if args.log_full_prompt:
        _print_model_input("Primary", system_prompt=primary_system_prompt, prompt=prompt)
    primary_elapsed_seconds = None
    try:
        primary_started = time.perf_counter()
        result = _run_coding_prompt_with_fallback(
            prompt,
            profile,
            catalog,
            args=args,
            repo_root=repo_root,
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
            progress_callback=print if args.execute and not args.native_tools else None,
            progress_prefix="local_agent_activity",
        )
        primary_elapsed_seconds = time.perf_counter() - primary_started
    except ProviderError as exc:
        print("=== Repo Coding Assistant ===")
        print(f"mode: {args.mode}")
        print(f"repo_root: {repo_root}")
        print("status: failed")
        print(f"failure_reason: {exc}")
        print("execution_status: failed")
        _print_cli_closeout(
            args=args,
            response_text=None,
            status="failed",
            execution_status="failed",
            failure_reason=str(exc),
        )
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
    if args.away_minutes is not None:
        print(f"away_budget_minutes: {args.away_minutes:g}")
        print(f"away_budget_seconds: {args.away_minutes * 60:g}")
        print(f"away_timeout_seconds: {args.timeout_seconds:g}")
    optional_chars = sum(
        len(item.content) for item in context_files if not item.required_instruction
    )
    required_chars = sum(len(item.content) for item in context_files if item.required_instruction)
    print(
        f"context_chars: {optional_chars}"
        + (f"/{args.context_budget_chars}" if context_budget_chars is not None else "/unlimited")
    )
    print(f"instruction_chars: {required_chars}/{args.instruction_budget_chars}")
    for context_file in context_files:
        print(f"context: {context_file.display_path}")
    final_status = result.orchestration.status.value
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
    if args.native_tools:
        _print_provider_native_policy_diagnostics(
            args.approval_policy,
            delegation_enabled=(
                args.mode == "implement"
                and not args.no_native_tools
                and args.tool_profile == "coding"
            ),
        )
    orchestrated_tracker = None
    orchestrated_deadline = None
    auxiliary_status = None
    validation_stage = None
    if args.orchestrated:
        assert args.away_minutes is not None
        orchestrated_deadline = time.perf_counter() + args.away_minutes * 60
        orchestrated_tracker, stage_records = OrchestratedRunTracker.create(
            args=args,
            repo_root=repo_root,
            orchestration=result.orchestration,
            prompt=args.prompt,
        )
        _print_orchestrated_stage_plan(
            args=args,
            orchestration=result.orchestration,
            run_record=orchestrated_tracker.run_record,
            stage_records=stage_records,
        )
        if args.mode == "implement" and args.execute:
            orchestrated_tracker.begin_run()
            if args.tool_profile == "research":
                from ai_provider.research_execution import prepare_research_run

                if not prepare_research_run(
                    args, orchestrated_tracker, result.orchestration, result.config, repo_root
                ):
                    if close_transcript_func is not None:
                        close_transcript_func()
                    return 1
            orchestrated_tracker.start_stage(
                "auxiliary_panel",
                details={"route_policy": "derived_local_cheap"},
            )
            print("\n=== Auxiliary panel ===")
            auxiliary_result = run_auxiliary_panel(
                prompt
                + (
                    "\nResearch preflight reviewer: you have no search/fetch tools. "
                    "Propose checks only; never claim sources were retrieved "
                    "or invent access dates."
                    if args.tool_profile == "research"
                    else ""
                ),
                profile,
                catalog,
                timeout_seconds=args.timeout_seconds,
                start_ollama=args.start_ollama,
                ollama_command=args.ollama_command,
                ollama_startup_timeout_seconds=args.ollama_startup_timeout_seconds,
                ollama_log_path=args.ollama_log_file,
                ollama_resource_profile=(
                    get_ollama_resource_profile(args.ollama_profile)
                    if args.ollama_profile is not None
                    else None
                ),
                progress_callback=print,
            )
            if auxiliary_result.route_id is not None:
                print(f"auxiliary_panel_route_id: {auxiliary_result.route_id}")
            if auxiliary_result.provider is not None:
                print(f"auxiliary_panel_provider: {auxiliary_result.provider}")
            if auxiliary_result.model is not None:
                print(f"auxiliary_panel_model: {auxiliary_result.model}")
            if auxiliary_result.response_text is not None:
                print(auxiliary_result.response_text)
            if auxiliary_result.failure_reason is not None:
                print(f"auxiliary_panel_failure_reason: {auxiliary_result.failure_reason}")
            print(f"auxiliary_panel_status: {auxiliary_result.status}")
            auxiliary_status = auxiliary_result.status
            orchestrated_tracker.complete_stage(
                "auxiliary_panel",
                status=auxiliary_result.status,
                details={
                    "route_id": auxiliary_result.route_id or "",
                    "provider": auxiliary_result.provider or "",
                    "model": auxiliary_result.model or "",
                    "failure_reason": auxiliary_result.failure_reason or "",
                },
            )
    assistant_response_text = None
    if args.native_tools and args.execute and result.config is not None:
        if orchestrated_tracker is not None and args.mode == "implement":
            orchestrated_tracker.start_stage(
                "implementation",
                details={
                    "route_id": result.orchestration.execution_plan.target.route_id
                    if result.orchestration.execution_plan is not None
                    else "",
                    "provider": result.config.provider.value,
                    "model": result.config.model,
                },
            )
        try:
            native_result = _run_native_agent_with_fallback(
                prompt,
                result.config,
                profile,
                args,
                repo_root,
                progress_callback=print,
            )
        except ProviderError as exc:
            print(f"failure_reason: {exc}")
            final_status = "failed"
            execution_status = "failed"
            if orchestrated_tracker is not None and args.mode == "implement":
                orchestrated_tracker.complete_stage(
                    "implementation",
                    status="failed",
                    details={"failure_reason": str(exc), **_fallback_details(args)},
                )
                validation_stage = orchestrated_tracker.record_validation_stage(
                    args=args,
                    repo_root=repo_root,
                    execution_status=execution_status,
                )
                execution_status = _run_orchestrated_scrutiny(
                    args=args,
                    tracker=orchestrated_tracker,
                    repo_root=repo_root,
                    profile=profile,
                    catalog=catalog,
                    validation_stage=validation_stage,
                    assistant_response_text=assistant_response_text,
                    execution_status=execution_status,
                    deadline=orchestrated_deadline,
                )
                orchestrated_tracker.complete_stage(
                    "repair",
                    status="skipped",
                    details={"skip_reason": "primary execution failed before repair"},
                )
                execution_status = _execution_status_with_validation_stage(
                    execution_status,
                    validation_stage,
                )
                orchestrated_tracker.record_final_handoff_stage(
                    execution_status=execution_status,
                    validation_stage=validation_stage,
                    repo_root=repo_root,
                    assistant_response_text=assistant_response_text,
                )
                orchestrated_tracker.finish_run(execution_status=execution_status)
            print(f"status: {final_status}")
            print(f"delegation: {delegation_status}")
            print(f"execution_status: {execution_status}")
            _print_cli_closeout(
                args=args,
                response_text=None,
                status=final_status,
                execution_status=execution_status,
                validation_stage=validation_stage,
                failure_reason=str(exc),
            )
            _print_run_metrics(
                metrics,
                primary_elapsed_seconds=primary_elapsed_seconds,
                primary_response=result.response,
                scrutiny_elapsed_seconds=None,
                scrutiny_response=None,
            )
            if close_transcript_func is not None:
                close_transcript_func()
            return 1
        assistant_response_text = native_result.response.message.content
        delegation_status = _delegation_status_after_native_tools(
            delegation_status,
            native_result.tool_results,
        )
        execution_status = (
            "completed_with_tool_errors"
            if any(item.is_error for item in native_result.tool_results)
            else "completed"
        )
        if orchestrated_tracker is not None and args.mode == "implement":
            orchestrated_tracker.complete_stage(
                "implementation",
                status=execution_status,
                details={
                    "tool_results": len(native_result.tool_results),
                    "tool_errors": sum(1 for item in native_result.tool_results if item.is_error),
                    **_fallback_details(args),
                },
            )
    elif result.response is not None:
        assistant_response_text = result.response.message.content
        if orchestrated_tracker is not None and args.mode == "implement":
            orchestrated_tracker.start_stage(
                "implementation",
                details={
                    "route_id": result.orchestration.execution_plan.target.route_id
                    if result.orchestration.execution_plan is not None
                    else "",
                    "provider": result.config.provider.value if result.config is not None else "",
                    "model": result.config.model if result.config is not None else "",
                },
            )
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
        if orchestrated_tracker is not None and args.mode == "implement":
            orchestrated_tracker.complete_stage("implementation", status=execution_status)
    elif result.orchestration.failure_reason:
        print(f"failure_reason: {result.orchestration.failure_reason}")
    elif result.orchestration.prompt_judge and result.orchestration.prompt_judge.should_refine:
        for issue in result.orchestration.prompt_judge.issues:
            print(f"prompt_issue: {issue.severity.value} {issue.code}: {issue.message}")
        if result.orchestration.prompt_judge.refined_prompt:
            print(f"suggested_prompt: {result.orchestration.prompt_judge.refined_prompt}")
    if result.orchestration.failure_reason:
        final_status = "failed"
        execution_status = "failed"
    scrutiny_result = None
    scrutiny_elapsed_seconds = None
    if (
        args.scrutinize_response
        and assistant_response_text is not None
        and args.tool_profile != "research"
    ):
        print("\n=== Response scrutiny ===")
        scrutiny_failed = False
        scrutiny_stage_status = "completed"
        scrutiny_stage_details: dict[str, object] = {"route_policy": "derived_local_cheap"}
        if orchestrated_tracker is not None:
            if orchestrated_tracker.run_record.status == "planned":
                orchestrated_tracker.begin_run()
            orchestrated_tracker.start_stage("scrutiny", details=scrutiny_stage_details)
        try:
            scrutiny_started = time.perf_counter()
            scrutiny_prompt = build_response_scrutiny_prompt(prompt, assistant_response_text)
            scrutiny_profile = derive_subtask_profile(
                parent=profile,
                task_type=TaskType.CLASSIFICATION,
                quality_threshold=QualityThreshold.STANDARD,
                latency_target=LatencyTarget.BACKGROUND,
                cost_policy_tier=CostPolicyTier.LOCAL_ONLY,
                privacy_class=OrchestratorPrivacyClass.LOCAL_ONLY,
            )
            if args.log_full_prompt:
                _print_model_input(
                    "Scrutiny",
                    system_prompt=_RESPONSE_SCRUTINY_SYSTEM_PROMPT,
                    prompt=scrutiny_prompt,
                )
            scrutiny_result = run_coding_prompt(
                scrutiny_prompt,
                scrutiny_profile,
                catalog,
                review_prompt=False,
                timeout_seconds=args.timeout_seconds,
                execute=True,
                system_prompt=_RESPONSE_SCRUTINY_SYSTEM_PROMPT,
                start_ollama=False,
                progress_callback=print,
                progress_prefix="scrutiny_activity",
            )
            scrutiny_elapsed_seconds = time.perf_counter() - scrutiny_started
        except ProviderError as exc:
            print("scrutiny_status: failed")
            print(f"scrutiny_failure_reason: {exc}")
            scrutiny_failed = True
            scrutiny_stage_status = "failed"
            scrutiny_stage_details["failure_reason"] = str(exc)
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
                    scrutiny_stage_status = "invalid"
                    scrutiny_stage_details["failure_reason"] = str(exc)
                else:
                    print(f"scrutiny_verdict: {scrutiny_report.verdict}")
                    print(f"scrutiny_score: {scrutiny_report.score}")
                    print("scrutiny_status: completed")
                    scrutiny_stage_details["verdict"] = scrutiny_report.verdict
                    scrutiny_stage_details["score"] = scrutiny_report.score
                    if scrutiny_report.verdict != "pass" and execution_status == "completed":
                        execution_status = "completed_with_scrutiny_findings"
            else:
                print("scrutiny_status: failed")
                scrutiny_failed = True
                scrutiny_stage_status = "failed"
                if scrutiny_result.orchestration.failure_reason:
                    scrutiny_stage_details["failure_reason"] = (
                        scrutiny_result.orchestration.failure_reason
                    )
                    print(
                        f"scrutiny_failure_reason: {scrutiny_result.orchestration.failure_reason}"
                    )
        if scrutiny_failed and execution_status == "completed":
            execution_status = "completed_with_scrutiny_errors"
        if orchestrated_tracker is not None:
            orchestrated_tracker.complete_stage(
                "scrutiny",
                status=scrutiny_stage_status,
                details=scrutiny_stage_details,
            )
    execution_status = _execution_status_with_auxiliary_result(
        execution_status,
        auxiliary_status,
    )
    print(f"status: {final_status}")
    print(f"delegation: {delegation_status}")
    print(f"execution_status: {execution_status}")
    if orchestrated_tracker is not None and args.execute:
        validation_stage = orchestrated_tracker.record_validation_stage(
            args=args,
            repo_root=repo_root,
            execution_status=execution_status,
        )
        execution_status = _execution_status_with_validation_stage(
            execution_status,
            validation_stage,
        )
        if args.mode == "implement":

            def repair_attempt(
                repair_prompt: str,
                _attempt_number: int,
                timeout_seconds: float,
            ) -> tuple[str, str | None]:
                repair_args = copy.copy(args)
                repair_args.timeout_seconds = timeout_seconds
                if args.tool_profile == "research":
                    repair_args.research_attempt_deadline = time.perf_counter() + timeout_seconds
                if repair_args.native_tools and result.config is not None:
                    native_repair = _run_native_agent_with_fallback(
                        repair_prompt,
                        result.config,
                        profile,
                        repair_args,
                        repo_root,
                        progress_callback=print,
                    )
                    status = (
                        "completed_with_tool_errors"
                        if any(item.is_error for item in native_repair.tool_results)
                        else "completed"
                    )
                    return status, native_repair.response.message.content
                repair_result = _run_coding_prompt_with_fallback(
                    repair_prompt,
                    profile,
                    catalog,
                    args=repair_args,
                    repo_root=repo_root,
                    review_prompt=False,
                    timeout_seconds=timeout_seconds,
                    execute=True,
                    system_prompt=primary_system_prompt,
                    start_ollama=False,
                    progress_callback=print,
                    progress_prefix="repair_activity",
                )
                if repair_result.response is None:
                    return "failed", None
                return "completed", repair_result.response.message.content

            execution_status, validation_stage, assistant_response_text = (
                _run_orchestrated_repair_loop(
                    args=args,
                    tracker=orchestrated_tracker,
                    repo_root=repo_root,
                    execution_status=execution_status,
                    validation_stage=validation_stage,
                    original_prompt=args.prompt
                    + (
                        "\n\nReport-only structural repair: preserve correct saved content "
                        "and source declarations. Length alone never requires repair; "
                        "improve substantive analysis "
                        "in the requested sections instead of shortening/recreating the draft. "
                        "Read the full report before replacement if the excerpt is truncated.\n"
                        + args.research_execution.repair_context()
                        if args.tool_profile == "research"
                        else ""
                    ),
                    assistant_response_text=assistant_response_text,
                    deadline=orchestrated_deadline,
                    repair_attempt=repair_attempt,
                )
            )
            if (
                args.tool_profile == "research"
                and execution_status == "completed_with_tool_errors"
                and _validation_status_from_stage(validation_stage) == "passed"
            ):
                print(
                    "research_recovered_tool_errors: report passed validation; "
                    "earlier tool errors remain recorded"
                )
                execution_status = "completed"
            if args.tool_profile == "research":
                from ai_provider.research_refinement import run_research_refinement

                execution_status, validation_stage, assistant_response_text = (
                    run_research_refinement(
                        args=args,
                        tracker=orchestrated_tracker,
                        repo_root=repo_root,
                        profile=profile,
                        catalog=catalog,
                        validation_stage=validation_stage,
                        assistant_response_text=assistant_response_text,
                        execution_status=execution_status,
                        deadline=orchestrated_deadline,
                        repair_attempt=repair_attempt,
                        review=_run_orchestrated_scrutiny,
                    )
                )
            else:
                execution_status = _run_orchestrated_scrutiny(
                    args=args,
                    tracker=orchestrated_tracker,
                    repo_root=repo_root,
                    profile=profile,
                    catalog=catalog,
                    validation_stage=validation_stage,
                    assistant_response_text=assistant_response_text,
                    execution_status=execution_status,
                    deadline=orchestrated_deadline,
                )
        print(f"final_execution_status: {execution_status}")
        orchestrated_tracker.record_final_handoff_stage(
            execution_status=execution_status,
            validation_stage=validation_stage,
            repo_root=repo_root,
            assistant_response_text=assistant_response_text,
        )
        orchestrated_tracker.finish_run(execution_status=execution_status)
    _print_run_metrics(
        metrics,
        primary_elapsed_seconds=primary_elapsed_seconds,
        primary_response=result.response,
        scrutiny_elapsed_seconds=scrutiny_elapsed_seconds,
        scrutiny_response=scrutiny_result.response if scrutiny_result is not None else None,
    )
    _print_cli_closeout(
        args=args,
        response_text=assistant_response_text,
        status=final_status,
        execution_status=execution_status,
        validation_stage=validation_stage if orchestrated_tracker is not None else None,
        failure_reason=result.orchestration.failure_reason,
    )
    if close_transcript_func is not None:
        close_transcript_func()
    if args.tool_profile == "research" and args.execute and execution_status != "completed":
        return 1
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


def _run_codex_login(
    *,
    args: argparse.Namespace,
    repo_root: Path,
    parser: argparse.ArgumentParser,
) -> int:
    """Run explicit Codex CLI login refresh."""

    if args.codex_login and args.codex_login_device:
        parser.error("--codex-login and --codex-login-device are mutually exclusive")
    if args.prompt:
        parser.error("Codex login cannot be combined with a prompt request")
    command = external_agent_command(AccessMethod.CODEX_CLI)
    if command is None:
        print("=== Codex login ===")
        print(f"repo_root: {repo_root}")
        print("codex_login_status: failed")
        print("failure_reason: Could not find Codex CLI. Set CODEX_COMMAND or install Codex CLI.")
        return 1

    login_command = [command, "login"]
    if args.codex_login_device:
        login_command.append("--device-auth")

    print("=== Codex login ===")
    print(f"repo_root: {repo_root}")
    print(f"codex_command: {command}")
    print(
        "codex_login_auth_boundary: local Codex auth refresh only; "
        "no token values are read or printed"
    )
    print("codex_login_command_line_json: " + json.dumps(login_command))
    try:
        result = subprocess.run(tuple(login_command), text=True)
    except OSError as exc:
        print("codex_login_status: failed")
        print(f"failure_reason: {exc}")
        print("execution_status: failed")
        return 1

    status = run_diagnostic_command(command, "login", "status", timeout_seconds=10.0)
    print(f"codex_login_returncode: {result.returncode}")
    print(f"codex_login_status_ok: {status['ok']}")
    if status["stdout"]:
        print(f"codex_login_status_stdout: {status['stdout']}")
    if status["stderr"]:
        print(f"codex_login_status_stderr: {status['stderr']}")
    execution_status = "completed" if result.returncode == 0 and status["ok"] else "failed"
    print(f"execution_status: {execution_status}")
    return 0 if execution_status == "completed" else result.returncode or 1


def _run_coding_prompt_with_fallback(
    prompt: str,
    profile: Any,
    catalog: tuple,
    *,
    args: argparse.Namespace,
    repo_root: Path,
    **kwargs: Any,
) -> Any:
    session = getattr(args, "fallback_session", None)
    if not kwargs.get("execute") or session is None or not session.enabled:
        return run_coding_prompt(prompt, profile, catalog, **kwargs)

    def execute(target: Any, payload: str) -> Any:
        if target.route_id == session.initial.route_id:
            return run_coding_prompt(payload, profile, catalog, **kwargs)
        return _execute_fallback_route(
            target,
            payload,
            args=args,
            profile=profile,
            repo_root=repo_root,
            progress_callback=print,
        )

    result = session.run(prompt, execute, _fallback_limited, observe=_fallback_observed)
    print(f"effective_route_id: {session.current.route_id}")
    if hasattr(result, "orchestration"):
        return result
    from ai_orchestrator import ExecutionPlan
    from ai_provider.coding_assist import CodingAssistResult

    if isinstance(result, ExternalAgentResult):
        response = _external_fallback_response(result, session.current)
        config = None
    else:
        response = result.response
        config = backend_config_from_execution_target(session.current)
    effective_profile = replace(
        profile,
        user_route_id_override=session.current.route_id,
        user_access_method_override=None,
        user_backend_override=None,
        user_model_override=None,
    )
    orchestration = prepare_execution(prompt, effective_profile, catalog, review_prompt=False)
    orchestration = replace(
        orchestration,
        execution_plan=ExecutionPlan(
            target=session.current, reasons=("Continued after usage exhaustion.",)
        ),
    )
    return CodingAssistResult(orchestration=orchestration, config=config, response=response)


def _external_fallback_response(result: ExternalAgentResult, target: Any) -> Any:
    from ai_provider.contracts import AIResponse, BackendInfo, BackendLocation

    failure = result.events.failure_reason if result.events else None
    if result.returncode or failure:
        raise ProviderError(f"Fallback client failed: {failure or result.returncode}")
    text = result.events.final_answer if result.events else result.stdout
    return AIResponse(
        message=AIMessage(MessageRole.ASSISTANT, text or result.last_message or ""),
        backend=BackendInfo(
            provider=target.provider, model=target.model, location=BackendLocation.EXTERNAL
        ),
        raw_metadata={"route_id": target.route_id, "external_agent": True},
    )


def _fallback_config(target: Any, args: argparse.Namespace, repo_root: Path) -> ExternalAgentConfig:
    return ExternalExecutionSettings.from_namespace(args).build(target, repo_root)


def _fallback_target_compatible(target: Any, args: argparse.Namespace, repo_root: Path) -> bool:
    """Preserve tool/approval constraints and verify provider credentials without inference."""
    return _fallback_target_incompatibility(target, args, repo_root) is None


def _fallback_executable_status(target: Any, repo_root: Path) -> str:
    """Check local external-client executable presence without invoking it."""

    if not _is_external_agent_access_method(target.access_method):
        return "not_applicable"
    command = external_agent_command(target.access_method)
    if command is None:
        return "unavailable"
    path = Path(command)
    if path.is_absolute() or path.parent != Path("."):
        candidate = path if path.is_absolute() else repo_root / path
        return "available" if candidate.is_file() else "unavailable"
    return "available" if shutil.which(command) else "unavailable"


def _fallback_target_incompatibility(
    target: Any,
    args: argparse.Namespace,
    repo_root: Path,
    *,
    probe_provider: bool = True,
) -> str | None:
    """Explain a refusal; offline declarations never establish authenticated readiness."""
    if _is_external_agent_access_method(target.access_method):
        if getattr(args, "tool_profile", "coding") == "research":
            return "research tools require provider-native execution"
        if args.no_native_tools or args.apply_actions:
            return "external fallback cannot preserve legacy action/native-tool settings"
        try:
            _build_external_agent_command(_fallback_config(target, args, repo_root))
            return None
        except (FileNotFoundError, NotImplementedError, ValueError) as exc:
            return str(exc)
    if (
        (getattr(args, "shared_tools", None) or getattr(args, "native_tools", False))
        and getattr(args, "tool_profile", "coding") != "research"
        and target.provider == "ollama"
    ):
        evidence = next((item for item in NATIVE_TOOL_EVIDENCE if item.model == target.model), None)
        if evidence is None:
            return f"Native tool compatibility is unknown for {target.model}"
        if probe_provider:
            try:
                identity = installed_native_identity(backend_config_from_execution_target(target))
            except ProviderError as exc:
                return str(exc)
            reason = native_tool_incompatibility(
                target.model, model_digest=identity[0], runtime_version=identity[1]
            )
            if reason:
                return reason
        elif not evidence.supported:
            return (
                f"Native tool execution failed the runtime compatibility probe for {target.model}"
            )
    requested = [
        flag
        for flag, value in (
            ("--codex-resume", args.codex_resume),
            ("--codex-persist-session", args.codex_persist_session),
            ("--codex-search", args.codex_search),
            ("--codex-image", args.codex_image),
            ("--codex-output-schema", args.codex_output_schema),
            ("--codex-mcp-tools", args.codex_mcp_tools),
            ("--codex-output-last-message", args.codex_output_last_message),
        )
        if value
    ]
    if requested:
        return "provider executor cannot preserve requested options: " + ", ".join(requested)
    if args.mode == "implement" and args.no_native_tools:
        return "provider implement fallback requires native tools"
    try:
        config = backend_config_from_execution_target(target)
        if not probe_provider:
            return None
        if config.provider is ProviderKind.OLLAMA:
            return (
                None
                if is_ollama_server_available(config.base_url)
                else "local Ollama service could not be reached"
            )
        from urllib.request import Request, urlopen

        from ai_provider.adapters.openai_compatible import OpenAICompatibleChatClient

        client = OpenAICompatibleChatClient(config)
        request = Request(f"{client.base_url}/models", headers=client._headers())
        with urlopen(request, timeout=10) as response:
            models = json.loads(response.read().decode("utf-8"))
        if any(
            row.get("id") == target.model for row in models.get("data", []) if isinstance(row, dict)
        ):
            return None
        return "configured model was not found in the provider model list"
    except (ProviderError, ValueError, OSError):
        return "provider configuration or model availability could not be verified"


def _print_fallback_readiness(args: argparse.Namespace, repo_root: Path) -> int:
    """Report static eligibility without loading context or starting account/tool probes."""
    from ai_provider.fallback_diagnostics import fallback_readiness_report

    catalog = load_model_catalog(args.catalog)
    profile = coding_task_profile(
        privacy_class=OrchestratorPrivacyClass(args.privacy),
        quality_threshold=QualityThreshold(args.quality),
        latency_target=LatencyTarget.INTERACTIVE,
        max_expected_latency_seconds=args.max_latency_seconds,
        cost_policy_tier=CostPolicyTier(args.cost_policy),
        route_id_override=args.route_id,
        access_method_override=AccessMethod(args.access_method) if args.access_method else None,
        provider_override=args.provider,
        model_override=args.model,
    )
    if args.tool_profile == "research":
        profile = replace(
            profile,
            task_type=TaskType.GENERAL,
            required_capabilities=frozenset({TaskCapability.CHAT, TaskCapability.TOOLS}),
        )
    elif getattr(args, "native_tools", False) or getattr(args, "shared_tools", None):
        catalog = native_coding_catalog(catalog, profile)
    result = prepare_execution(
        args.prompt or "Inspect fallback readiness",
        profile,
        catalog,
        review_prompt=False,
        timeout_seconds=args.timeout_seconds,
    )
    if result.execution_plan is None:
        print(json.dumps({"status": "blocked", "reason": result.failure_reason}))
        return 1
    selected_skills: tuple[str, ...] = ()
    if args.skill:
        from ai_agent.skills import load_development_skills
        from ai_agent.tool_profiles import shared_tool_profile

        directories = (
            [path if path.is_absolute() else repo_root / path for path in args.skill_dir]
            if args.skill_dir
            else [repo_root / ".agents/skills", repo_root / "packages/ai_agent/skills"]
        )
        try:
            skills = load_development_skills(
                args.skill,
                directories,
                available_tools=frozenset(shared_tool_profile(args.shared_tools).tool_names),
            )
        except (ValueError, OSError) as exc:
            print(json.dumps({"status": "blocked", "reason": str(exc)}))
            return 1
        selected_skills = tuple(skill.name for skill in skills)
    report = fallback_readiness_report(
        profile,
        catalog,
        result.execution_plan.target,
        incompatibility=lambda target: _fallback_target_incompatibility(
            target, args, repo_root, probe_provider=False
        ),
        executable_status=lambda target: _fallback_executable_status(target, repo_root),
        enabled=args.fallback_enabled,
        quality_policy=args.fallback_quality_policy,
    )
    report["requirements"] = {
        "shared_tool_profile": args.shared_tools,
        "approval_policy": args.approval_policy,
        "selected_skills": list(selected_skills),
    }
    print(json.dumps(report, indent=2))
    return 0


def _print_skill_discovery(args: argparse.Namespace, repo_root: Path) -> int:
    """Report supported skill sources and prerequisites without execution."""
    from ai_agent.skills import discover_development_skills
    from ai_agent.tool_profiles import shared_tool_profile

    directories = (
        [path if path.is_absolute() else repo_root / path for path in args.skill_dir]
        if args.skill_dir
        else [repo_root / ".agents/skills", repo_root / "packages/ai_agent/skills"]
    )
    profile = args.shared_tools or "inspection"
    try:
        skills = discover_development_skills(
            directories,
            available_tools=frozenset(shared_tool_profile(profile).tool_names),
        )
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, indent=2))
        return 1

    records = []
    for skill in skills:
        source = skill.source
        if source is not None:
            try:
                source = source.relative_to(repo_root)
            except ValueError:
                pass
        records.append(
            {
                "name": skill.name,
                "available": skill.available,
                "source": str(source) if source is not None else None,
                "required_tools": list(skill.required_tools),
                "reason": skill.reason,
            }
        )
    print(
        json.dumps(
            {
                "status": "ready" if all(item.available for item in skills) else "blocked",
                "shared_tool_profile": profile,
                "skills": records,
                "execution": "offline; no client, provider, or skill installation was started",
            },
            indent=2,
        )
    )
    return 0 if all(item.available for item in skills) else 1


def _execute_fallback_route(
    target: Any,
    prompt: str,
    *,
    args: argparse.Namespace,
    profile: Any,
    repo_root: Path,
    progress_callback: Any,
) -> Any:
    from ai_provider.coding_sessions import ACTIVE_SESSION

    active_session = ACTIVE_SESSION.get()
    if active_session is not None:
        prompt += "\n\n" + active_session.handoff()
    if _is_external_agent_access_method(target.access_method):
        config = _fallback_config(target, args, repo_root)
        external_prompt = _external_agent_prompt_with_execution_metadata(
            prompt,
            system_prompt=build_default_system_prompt(args.system, actions_enabled=False),
            approval_policy=args.approval_policy,
            sandbox=config.sandbox,
            mode=args.mode,
        )
        return _run_external_agent(
            external_prompt,
            config,
            progress_callback=progress_callback,
            deadline=getattr(getattr(args, "fallback_session", None), "deadline", None),
        )
    config = backend_config_from_execution_target(target)
    if args.mode == "implement" or getattr(args, "shared_tools", None):
        return _run_native_agent(
            prompt, config, profile, args, repo_root, progress_callback=progress_callback
        )
    from ai_provider.coding_assist import coding_request_from_prompt

    from ai_agent.loop import AgentResult

    response = create_chat_client(config).complete(
        coding_request_from_prompt(prompt, profile, config)
    )
    return AgentResult(response=response)


def _fallback_limited(result: Any) -> bool:
    return isinstance(result, ExternalAgentResult) and external_usage_limit(result)


def _fallback_observed(result: Any) -> str:
    if isinstance(result, ExternalAgentResult):
        events = result.events
        if events is not None:
            return (
                f"Observed {len(events.tool_events)} tool events, "
                f"{len(events.file_change_events)} file-change events, and "
                f"{len(events.command_events)} command events. "
                "Raw arguments and outputs are omitted; inspect current files."
            )
        return "Client reported a usage limit; inspect current files for partial work."
    return "Provider reported a usage limit; inspect current files for partial work."


def _run_external_agent_with_fallback(
    prompt: str,
    config: ExternalAgentConfig,
    *,
    args: argparse.Namespace,
    profile: Any,
    repo_root: Path,
    progress_callback: Any = None,
) -> ExternalAgentResult:
    session = getattr(args, "fallback_session", None)
    if session is None or not session.enabled:
        return _run_external_agent(prompt, config, progress_callback=progress_callback)
    args.shared_task_id = config.shared_task_id

    def execute(target: Any, payload: str) -> Any:
        if target.route_id == session.initial.route_id:
            return _run_external_agent(
                payload,
                replace(config, timeout_seconds=target.timeout_seconds),
                progress_callback=progress_callback,
                deadline=session.deadline,
            )
        return _execute_fallback_route(
            target,
            payload,
            args=args,
            profile=profile,
            repo_root=repo_root,
            progress_callback=progress_callback,
        )

    result = session.run(prompt, execute, _fallback_limited, observe=_fallback_observed)
    print(f"effective_route_id: {session.current.route_id}")
    if isinstance(result, ExternalAgentResult):
        return result
    return ExternalAgentResult(
        command=(), returncode=0, stdout=result.response.message.content, stderr=""
    )


def _run_native_agent_with_fallback(
    prompt: str,
    config: BackendConfig,
    profile: Any,
    args: argparse.Namespace,
    repo_root: Path,
    progress_callback: Any = None,
) -> Any:
    session = getattr(args, "fallback_session", None)
    if session is None or not session.enabled:
        return _run_native_agent(
            prompt, config, profile, args, repo_root, progress_callback=progress_callback
        )

    def execute(target: Any, payload: str) -> Any:
        if target.route_id == session.initial.route_id:
            return _run_native_agent(
                payload, config, profile, args, repo_root, progress_callback=progress_callback
            )
        return _execute_fallback_route(
            target,
            payload,
            args=args,
            profile=profile,
            repo_root=repo_root,
            progress_callback=progress_callback,
        )

    result = session.run(prompt, execute, _fallback_limited, observe=_fallback_observed)
    print(f"effective_route_id: {session.current.route_id}")
    if not isinstance(result, ExternalAgentResult):
        return result
    from ai_agent.loop import AgentResult

    return AgentResult(response=_external_fallback_response(result, session.current))


def _save_fallback_handoff(repo_root: Path, summary: dict[str, Any]) -> None:
    """Save a metadata-only stop receipt without invoking a weaker model or touching edits."""
    import uuid

    directory = repo_root / "artifacts" / "fallback-handoffs"
    if not directory.resolve().is_relative_to(repo_root.resolve()):
        raise ValueError("Fallback handoff directory leaves the workspace")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (uuid.uuid4().hex + ".json")
    try:
        status = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--short"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if status.returncode == 0:
            summary = {
                **summary,
                "working_tree_status": status.stdout[:8000],
                "working_tree_status_truncated": len(status.stdout) > 8000,
            }
    except (OSError, subprocess.TimeoutExpired):
        pass
    with target.open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2)
    print(f"fallback_handoff_file: {target}")


def _run_external_agent_cli_mode(
    *,
    prompt: str,
    system_prompt: str,
    args: argparse.Namespace,
    repo_root: Path,
    profile: Any,
    catalog: tuple[Any, ...],
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
    if args.codex_mcp_tools and delegation_status == "disabled":
        delegation_status = "enabled: external Codex MCP delegate_task available"
    print("=== Repo Coding Assistant ===")
    print(f"mode: {args.mode}")
    print(f"repo_root: {repo_root}")
    if args.away_minutes is not None:
        print(f"away_budget_minutes: {args.away_minutes:g}")
        print(f"away_budget_seconds: {args.away_minutes * 60:g}")
        print(f"away_timeout_seconds: {args.timeout_seconds:g}")
    optional_chars = sum(
        len(item.content) for item in context_files if not item.required_instruction
    )
    required_chars = sum(len(item.content) for item in context_files if item.required_instruction)
    print(
        f"context_chars: {optional_chars}"
        + (f"/{args.context_budget_chars}" if context_budget_chars is not None else "/unlimited")
    )
    print(f"instruction_chars: {required_chars}/{args.instruction_budget_chars}")
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
    final_answer_text: str | None = None
    failure_reason: str | None = None
    orchestrated_tracker = None
    orchestrated_deadline = None
    auxiliary_status = None
    validation_stage = None
    execution_settings = ExternalExecutionSettings.from_namespace(args)
    try:
        config = execution_settings.build(target, repo_root, timeout_seconds=args.timeout_seconds)
        print(f"external_agent_command: {config.command}")
        print(f"approval_policy: {args.approval_policy}")
        print(f"external_agent_sandbox: {config.sandbox}")
        command = _build_external_agent_command(config)
        print("external_agent_command_line_json: " + json.dumps(list(command)))
        print(f"external_agent_ephemeral: {config.ephemeral}")
        if config.resume is not None:
            print(f"external_agent_resume: {config.resume}")
        if config.output_last_message_path is not None:
            print(f"external_agent_output_last_message: {config.output_last_message_path}")
        if config.output_schema_path is not None:
            print(f"external_agent_output_schema: {config.output_schema_path}")
        print(f"external_agent_web_search: {config.web_search}")
        print(f"external_agent_mcp_tools: {config.codex_mcp_tools}")
        print("external_agent_timeout_mode: inactivity")
        print(f"external_agent_inactivity_timeout_seconds: {config.timeout_seconds:g}")
        if config.image_paths:
            print(
                "external_agent_images_json: "
                + json.dumps([str(path) for path in config.image_paths])
            )
        if args.orchestrated:
            assert args.away_minutes is not None
            orchestrated_deadline = time.perf_counter() + args.away_minutes * 60
            orchestrated_tracker, stage_records = OrchestratedRunTracker.create(
                args=args,
                repo_root=repo_root,
                orchestration=orchestration,
                prompt=args.prompt,
            )
            _print_orchestrated_stage_plan(
                args=args,
                orchestration=orchestration,
                run_record=orchestrated_tracker.run_record,
                stage_records=stage_records,
            )
            if args.execute and args.mode == "implement":
                orchestrated_tracker.begin_run()
                orchestrated_tracker.start_stage(
                    "auxiliary_panel",
                    details={"route_policy": "derived_local_cheap"},
                )
                print("\n=== Auxiliary panel ===")
                auxiliary_result = run_auxiliary_panel(
                    prompt,
                    profile,
                    catalog,
                    timeout_seconds=args.timeout_seconds,
                    start_ollama=args.start_ollama,
                    ollama_command=args.ollama_command,
                    ollama_startup_timeout_seconds=args.ollama_startup_timeout_seconds,
                    ollama_log_path=args.ollama_log_file,
                    ollama_resource_profile=(
                        get_ollama_resource_profile(args.ollama_profile)
                        if args.ollama_profile is not None
                        else None
                    ),
                    progress_callback=print,
                )
                if auxiliary_result.route_id is not None:
                    print(f"auxiliary_panel_route_id: {auxiliary_result.route_id}")
                if auxiliary_result.provider is not None:
                    print(f"auxiliary_panel_provider: {auxiliary_result.provider}")
                if auxiliary_result.model is not None:
                    print(f"auxiliary_panel_model: {auxiliary_result.model}")
                if auxiliary_result.response_text is not None:
                    print(auxiliary_result.response_text)
                if auxiliary_result.failure_reason is not None:
                    print(f"auxiliary_panel_failure_reason: {auxiliary_result.failure_reason}")
                print(f"auxiliary_panel_status: {auxiliary_result.status}")
                auxiliary_status = auxiliary_result.status
                orchestrated_tracker.complete_stage(
                    "auxiliary_panel",
                    status=auxiliary_result.status,
                    details={
                        "route_id": auxiliary_result.route_id or "",
                        "provider": auxiliary_result.provider or "",
                        "model": auxiliary_result.model or "",
                        "failure_reason": auxiliary_result.failure_reason or "",
                    },
                )
        if args.execute and args.mode != "plan":
            if orchestrated_tracker is not None and args.mode == "implement":
                orchestrated_tracker.start_stage(
                    "implementation",
                    details={
                        "route_id": target.route_id,
                        "provider": target.provider,
                        "model": target.model,
                    },
                )
            external_prompt = _external_agent_prompt_with_execution_metadata(
                prompt,
                system_prompt=system_prompt,
                approval_policy=args.approval_policy,
                sandbox=config.sandbox,
                mode=args.mode,
            )
            primary_started = time.perf_counter()
            external_result = _run_external_agent_with_fallback(
                external_prompt,
                config,
                args=args,
                profile=profile,
                repo_root=repo_root,
                progress_callback=print,
            )
            primary_elapsed_seconds = time.perf_counter() - primary_started
            print("\n=== External agent diagnostics ===")
            print(f"external_agent_returncode: {external_result.returncode}")
            if external_result.events is not None:
                _print_external_agent_event_summary(external_result.events)
                _write_external_agent_raw_jsonl(external_result.stdout)
                if external_result.events.final_answer:
                    final_answer_text = external_result.events.final_answer
                elif external_result.last_message:
                    final_answer_text = external_result.last_message
                else:
                    print("external_agent_final_answer: unavailable")
            elif external_result.stdout:
                final_answer_text = external_result.stdout
            if external_result.stderr:
                full_stderr_path = _write_external_agent_stderr(
                    external_result.stderr,
                    args.log_file,
                )
                if full_stderr_path is not None:
                    print(f"external_agent_stderr_file: {full_stderr_path}")
                print(_format_external_agent_stderr(external_result.stderr), end="")
            parsed_failure = (
                external_result.events.failure_reason
                if external_result.events is not None
                else None
            )
            if external_result.events is not None:
                delegation_status = _delegation_status_after_external_agent_events(
                    delegation_status,
                    external_result.events,
                )
                print(f"delegation: {delegation_status}")
            if external_result.returncode != 0 and parsed_failure is None:
                failure_reason = (
                    f"external agent process exited with code {external_result.returncode}"
                )
                print(
                    "external_agent_failure_reason: "
                    f"process exited with code {external_result.returncode}"
                )
                if external_result.stderr:
                    print("external_agent_failure_hint: inspect external_agent_stderr_file")
            elif parsed_failure is not None:
                failure_reason = parsed_failure
            execution_status = (
                "completed"
                if external_result.returncode == 0 and parsed_failure is None
                else "failed"
            )
            if orchestrated_tracker is not None and args.mode == "implement":
                orchestrated_tracker.complete_stage(
                    "implementation",
                    status=execution_status,
                    details={
                        "returncode": external_result.returncode,
                        "failure_reason": parsed_failure or "",
                        **_fallback_details(args),
                    },
                )
            exit_code = 0 if execution_status == "completed" else external_result.returncode or 1
        else:
            print("execution: skipped")
    except (
        FileNotFoundError,
        NotImplementedError,
        subprocess.TimeoutExpired,
        ProviderError,
    ) as exc:
        print(f"failure_reason: {exc}")
        failure_reason = str(exc)
        if isinstance(exc, subprocess.TimeoutExpired):
            _print_external_agent_timeout_output(exc)
        hint = _external_agent_exception_hint(exc)
        if hint is not None:
            print(f"failure_hint: {hint}")
        execution_status = "failed"
        if orchestrated_tracker is not None and args.mode == "implement":
            orchestrated_tracker.complete_stage(
                "implementation",
                status="failed",
                details={"failure_reason": str(exc), **_fallback_details(args)},
            )
        exit_code = 1

    execution_status = _execution_status_with_auxiliary_result(
        execution_status,
        auxiliary_status,
    )
    print(f"execution_status: {execution_status}")
    if orchestrated_tracker is not None and args.execute:
        validation_stage = orchestrated_tracker.record_validation_stage(
            args=args,
            repo_root=repo_root,
            execution_status=execution_status,
        )
        execution_status = _execution_status_with_validation_stage(
            execution_status,
            validation_stage,
        )
        if args.mode == "implement":

            def repair_attempt(
                repair_prompt: str,
                _attempt_number: int,
                timeout_seconds: float,
            ) -> tuple[str, str | None]:
                repair_config = execution_settings.build(
                    target,
                    repo_root,
                    timeout_seconds=timeout_seconds,
                )
                repair_external_prompt = _external_agent_prompt_with_execution_metadata(
                    repair_prompt,
                    system_prompt=system_prompt,
                    approval_policy=args.approval_policy,
                    sandbox=repair_config.sandbox,
                    mode=args.mode,
                )
                repair_result = _run_external_agent_with_fallback(
                    repair_external_prompt,
                    repair_config,
                    args=args,
                    profile=profile,
                    repo_root=repo_root,
                    progress_callback=print,
                )
                print(f"repair_external_agent_returncode: {repair_result.returncode}")
                parsed_failure = (
                    repair_result.events.failure_reason
                    if repair_result.events is not None
                    else None
                )
                if repair_result.events is not None:
                    if repair_result.events.final_answer:
                        return (
                            "completed"
                            if repair_result.returncode == 0 and parsed_failure is None
                            else "failed",
                            repair_result.events.final_answer,
                        )
                    if repair_result.last_message:
                        return (
                            "completed"
                            if repair_result.returncode == 0 and parsed_failure is None
                            else "failed",
                            repair_result.last_message,
                        )
                if repair_result.stdout:
                    return (
                        "completed"
                        if repair_result.returncode == 0 and parsed_failure is None
                        else "failed",
                        repair_result.stdout,
                    )
                return (
                    "completed"
                    if repair_result.returncode == 0 and parsed_failure is None
                    else "failed",
                    None,
                )

            execution_status, validation_stage, final_answer_text = _run_orchestrated_repair_loop(
                args=args,
                tracker=orchestrated_tracker,
                repo_root=repo_root,
                execution_status=execution_status,
                validation_stage=validation_stage,
                original_prompt=args.prompt,
                assistant_response_text=final_answer_text,
                deadline=orchestrated_deadline,
                repair_attempt=repair_attempt,
            )
            execution_status = _run_orchestrated_scrutiny(
                args=args,
                tracker=orchestrated_tracker,
                repo_root=repo_root,
                profile=profile,
                catalog=catalog,
                validation_stage=validation_stage,
                assistant_response_text=final_answer_text,
                execution_status=execution_status,
                deadline=orchestrated_deadline,
            )
        print(f"final_execution_status: {execution_status}")
        orchestrated_tracker.record_final_handoff_stage(
            execution_status=execution_status,
            validation_stage=validation_stage,
            repo_root=repo_root,
            assistant_response_text=None,
            final_answer_text=final_answer_text,
        )
        orchestrated_tracker.finish_run(execution_status=execution_status)
    _print_run_metrics(
        metrics,
        primary_elapsed_seconds=primary_elapsed_seconds,
        primary_response=None,
        scrutiny_elapsed_seconds=None,
        scrutiny_response=None,
    )
    _print_cli_closeout(
        args=args,
        response_text=final_answer_text,
        status="failed" if exit_code else "ready",
        execution_status=execution_status,
        validation_stage=validation_stage,
        failure_reason=failure_reason,
    )
    if close_transcript is not None:
        close_transcript()
    return exit_code


def _external_agent_prompt_with_execution_metadata(
    prompt: str,
    *,
    system_prompt: str,
    approval_policy: str,
    sandbox: str,
    mode: str,
) -> str:
    """Add execution metadata so external agents do not infer the wrong sandbox."""

    return (
        "# Repo assistant system prompt\n"
        f"{system_prompt.rstrip()}\n\n"
        f"{prompt}\n\n"
        "# External agent execution metadata\n"
        f"repo_assistant_mode: {mode}\n"
        f"repo_assistant_approval_policy: {approval_policy}\n"
        f"codex_sandbox: {sandbox}\n"
        "filesystem_note: Use the sandbox value above as the effective Codex CLI "
        "filesystem policy for this run. Do not describe the session as read-only "
        "unless a command result explicitly reports a read-only or permission-denied "
        "failure."
    )


def _print_external_agent_timeout_output(exc: subprocess.TimeoutExpired) -> None:
    """Print bounded partial output captured before an external-agent timeout."""

    stdout = _timeout_output_to_text(exc.output)
    stderr = _timeout_output_to_text(exc.stderr)
    if stdout:
        events = parse_external_agent_jsonl(stdout)
        _print_external_agent_event_summary(events)
        _write_external_agent_raw_jsonl(stdout)
    if stderr:
        print("\n=== External agent stderr ===")
        stderr_text = _format_external_agent_stderr(stderr)
        print(stderr_text, end="")
        if not stderr_text.endswith("\n"):
            print()


def _write_external_agent_raw_jsonl(raw_jsonl: str) -> None:
    """Preserve raw external-agent JSONL in transcript logs without console noise."""

    if not raw_jsonl:
        return
    _write_transcript_only("\n=== External agent raw JSONL ===\n")
    _write_transcript_only(raw_jsonl)
    if not raw_jsonl.endswith("\n"):
        _write_transcript_only("\n")


def _run_native_agent(
    prompt: str,
    config: BackendConfig,
    profile: Any,
    args: argparse.Namespace,
    repo_root: Path,
    *,
    progress_callback: Callable[[str], None] | None = None,
) -> Any:
    """Run the provider-native agent loop inside the repository boundary."""
    for instructions in (
        getattr(args, "required_context", ""),
        getattr(args, "skill_instructions", ""),
    ):
        if instructions and instructions not in prompt:
            prompt += "\n\n" + instructions
    config = replace(
        config,
        timeout_seconds=min(
            config.timeout_seconds, getattr(args, "timeout_seconds", config.timeout_seconds)
        ),
    )
    if progress_callback is not None:
        progress_callback(
            f"local_agent_activity: model_request - provider={config.provider.value} "
            f"model={config.model}"
        )
    if args.start_ollama and config.provider is ProviderKind.OLLAMA:
        if progress_callback is not None:
            progress_callback(f"local_agent_activity: ollama_start - base_url={config.base_url}")
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
        from ai_provider.coding_sessions import ACTIVE_SESSION

        session = ACTIVE_SESSION.get()
        task = session.session_id if session else "current foreground task"
        operation = json.dumps(call.arguments, ensure_ascii=True)
        try:
            answer = input(
                f"Task: {task}\nWorkspace: {repo_root.resolve()}\n"
                f"Allow {category.value} tool '{call.name}' {operation}? [y/N]: "
            )
        except (EOFError, OSError):
            return False
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
    child_depth = int(getattr(args, "_delegation_depth", 0))

    def run_delegated_task(task: str, context: ToolContext) -> ToolResult:
        if child_depth >= 1:
            return ToolResult(
                name="delegate_task",
                output="Error: nested delegation is disabled for bounded CLI runs.",
                is_error=True,
            )
        if progress_callback is not None:
            progress_callback(
                f"delegated_agent_activity: started - coding_subtask {_activity_preview(task)}"
            )
        try:
            child_profile = derive_subtask_profile(
                parent=profile,
                task_type=TaskType.CODING,
                required_capabilities=frozenset({TaskCapability.CHAT, TaskCapability.TOOLS}),
                quality_threshold=QualityThreshold.STANDARD,
                latency_target=LatencyTarget.BACKGROUND,
                cost_policy_tier=CostPolicyTier.LOCAL_ONLY,
                privacy_class=OrchestratorPrivacyClass.LOCAL_ONLY,
            )
            child_orchestration = prepare_execution(
                task,
                child_profile,
                native_coding_catalog(
                    load_model_catalog(
                        getattr(
                            args,
                            "catalog",
                            Path("packages/ai_orchestrator/examples/model_catalog.toml"),
                        )
                    ),
                    child_profile,
                ),
                review_prompt=False,
                timeout_seconds=getattr(args, "timeout_seconds", 180.0),
            )
            if not child_orchestration.is_ready or child_orchestration.execution_plan is None:
                reason = child_orchestration.failure_reason or child_orchestration.status.value
                return ToolResult(
                    name="delegate_task",
                    output=f"Error: delegated subtask route was not ready: {reason}",
                    is_error=True,
                )
            child_config = BackendConfig(
                provider=ProviderKind(child_orchestration.execution_plan.target.provider),
                model=child_orchestration.execution_plan.target.model,
                base_url=child_orchestration.execution_plan.target.base_url,
                timeout_seconds=child_orchestration.execution_plan.target.timeout_seconds,
            )
            if progress_callback is not None:
                progress_callback(
                    "delegated_agent_activity: model_request - "
                    f"route={child_orchestration.execution_plan.target.route_id} "
                    f"model={child_config.model}"
                )
            child_args = argparse.Namespace(**vars(args))
            child_args._delegation_depth = child_depth + 1
            child_result = _run_native_agent(
                task,
                child_config,
                child_profile,
                child_args,
                context.workspace_root,
                progress_callback=progress_callback,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                name="delegate_task",
                output=f"Error: delegated subtask failed: {exc}",
                is_error=True,
            )

        output = _format_delegated_task_output(
            task=task,
            child_output=child_result.response.message.content,
            iterations=child_result.iterations,
            tool_results=child_result.tool_results,
        )
        if progress_callback is not None:
            progress_callback(
                "delegated_agent_activity: completed - "
                f"iterations={child_result.iterations} "
                f"tool_results={len(child_result.tool_results)}"
            )
        return ToolResult(
            name="delegate_task",
            output=output,
            is_error=any(item.is_error for item in child_result.tool_results),
            metadata={
                "iterations": child_result.iterations,
                "tool_results": len(child_result.tool_results),
            },
        )

    registry = (
        default_coding_tools()
        if child_depth >= 1
        else coding_tools_with_delegation(run_delegated_task)
    )
    if getattr(args, "shared_tools", None):
        from ai_agent.tool_profiles import shared_tool_registry

        registry = shared_tool_registry(args.shared_tools, repo_root)
    research = getattr(args, "research_execution", None)
    if research is not None:
        from ai_provider.research_execution import (
            RESEARCH_SYSTEM_PROMPT,
            ResearchChatClient,
            research_runtime_options,
        )

        registry = research.registry
        resource_profile = getattr(args, "ollama_profile", None)
        research_context = (
            get_ollama_resource_profile(resource_profile).context_length
            if resource_profile
            else 32768
        )
        options = getattr(args, "research_runtime_options", None)
        client = ResearchChatClient(
            client,
            options
            if options is not None
            else research_runtime_options(config, context_length=research_context),
            deadline=getattr(args, "research_attempt_deadline", None),
            config=config,
            client_factory=create_chat_client,
        )
        system_prompt = RESEARCH_SYSTEM_PROMPT + ("\n" + args.system if args.system else "")
    else:
        system_prompt = build_native_tool_system_prompt(args.system)
        client = prepare_native_coding_client(client, config, args, progress_callback or print)
        away_minutes = getattr(args, "away_minutes", None)
        if away_minutes is not None:
            system_prompt = _system_prompt_with_away_budget(
                system_prompt,
                away_minutes=away_minutes,
            )
    from ai_provider.coding_sessions import ACTIVE_SESSION

    active_session = ACTIVE_SESSION.get()
    from ai_provider.foreground_tools import ACTIVE_FOREGROUND

    foreground = ACTIVE_FOREGROUND.get()
    if research is None and getattr(args, "shared_tools", None) == "coding" and foreground:
        registry = foreground.registry()
    if active_session is not None:
        if research is None and not getattr(args, "shared_tools", None):
            from ai_agent.processes import ProcessTool

            for operation in ("start", "status", "stop"):
                registry.register(ProcessTool(active_session.supervisor, operation))
        registry = active_session.observe_registry(registry)
    agent = AgentLoop(
        client,
        registry,
        ToolContext(workspace_root=repo_root),
        permissions=PermissionManager(
            policy=permission_policy,
            approval_callback=approval_callback,
        ),
        max_iterations=args.max_action_rounds,
    )
    try:
        result = agent.run(
            prompt,
            system_prompt=system_prompt,
            model=config.model,
            privacy_class=PrivacyClass(profile.privacy_class.value),
        )
    except ProviderError as exc:
        if progress_callback is not None:
            progress_callback("local_agent_activity: failed - earlier receipts follow")
            for message in exc.partial_messages:
                if message.role is MessageRole.TOOL:
                    progress_callback(
                        f"local_tool_activity: recorded - {message.name}: "
                        f"{_activity_preview(message.content)}"
                    )
        raise
    textual_request = _contains_textual_tool_request(
        result.response.message.content,
        {definition.name for definition in registry.list_definitions()},
    )
    if progress_callback is not None:
        progress_callback(
            f"local_agent_activity: {'incomplete' if textual_request else 'completed'} "
            f"- iterations={result.iterations} "
            f"tool_results={len(result.tool_results)}"
        )
        for tool_result in result.tool_results:
            status = "error" if tool_result.is_error else "ok"
            progress_callback(
                f"local_tool_activity: {status} - {tool_result.name}: "
                f"{_activity_preview(tool_result.output)}"
            )
    if textual_request:
        message = (
            "Native agent returned an unexecuted textual tool request after earlier tools. "
            "Earlier tool effects remain; inspect their receipts before continuing."
            if result.tool_results
            else "Native agent returned a textual tool request without executing any tools. "
            "No action was performed; this response cannot count as completed implementation."
        )
        raise ProviderError(
            message,
            category=ProviderErrorCategory.NON_RETRYABLE,
            provider=config.provider.value,
        )
    return result


def _contains_textual_tool_request(content: str, tool_names: set[str]) -> bool:
    """Recognize legacy JSON tool requests without executing model-authored text."""
    candidates = [content.strip(), *re.findall(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)]
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        items = value if isinstance(value, list) else [value]
        for item in items:
            if (
                isinstance(item, dict)
                and isinstance(item.get("name"), str)
                and item.get("name") in tool_names
                and isinstance(item.get("arguments"), dict)
            ):
                return True
    return False


def _format_delegated_task_output(
    *,
    task: str,
    child_output: str,
    iterations: int,
    tool_results: Sequence[ToolResult],
) -> str:
    """Build a bounded child-agent handoff for the primary model."""

    failed_count = sum(1 for result in tool_results if result.is_error)
    status = "failed" if failed_count else "completed"
    lines = [
        f"Delegated task status: {status}",
        f"Task: {_activity_preview(task, limit=240)}",
        f"Iterations: {iterations}",
        f"Tool results: {len(tool_results)} total, {failed_count} failed",
    ]
    if tool_results:
        lines.append("Tool result summary:")
        for index, result in enumerate(tool_results[:5], start=1):
            result_status = "error" if result.is_error else "ok"
            lines.append(
                f"- {index}. {result.name}: {result_status} - "
                f"{_activity_preview(result.output, limit=240)}"
            )
        if len(tool_results) > 5:
            lines.append(f"- ... {len(tool_results) - 5} additional tool result(s) omitted")
    lines.extend(["Child final response:", child_output.strip() or "(empty)"])
    return "\n".join(lines)


def _delegation_status_after_native_tools(
    current_status: str,
    tool_results: Sequence[ToolResult],
) -> str:
    """Reflect native delegate-tool usage in the final CLI delegation status."""

    delegated_results = [result for result in tool_results if result.name == "delegate_task"]
    if not delegated_results:
        return current_status
    native_status = (
        "failed: native delegate_task"
        if any(result.is_error for result in delegated_results)
        else "completed: native delegate_task"
    )
    if current_status == "disabled":
        return native_status
    return f"{current_status}; {native_status}"


def _print_provider_native_policy_diagnostics(
    approval_policy: str,
    *,
    delegation_enabled: bool,
) -> None:
    """Print secret-free provider-native tool policy diagnostics."""

    policy = PermissionPolicy.from_approval_preset(approval_policy)
    actions = {
        category.value: policy.action_for_category(category).value for category in ToolCategory
    }
    requires_approval = any(action == "ask_user" for action in actions.values())
    print("provider_native_tools: enabled")
    print(f"provider_native_approval_policy: {approval_policy}")
    print("provider_native_tool_policy_json: " + json.dumps(actions, sort_keys=True))
    print(f"provider_native_requires_interactive_approval: {requires_approval}")
    print(
        "provider_native_delegation: "
        + ("enabled: primary agent may call delegate_task" if delegation_enabled else "disabled")
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
            system_prompt=build_default_system_prompt(args.system, actions_enabled=True),
            start_ollama=args.start_ollama,
            ollama_command=args.ollama_command,
            ollama_startup_timeout_seconds=args.ollama_startup_timeout_seconds,
            ollama_log_path=args.ollama_log_file if args.start_ollama else None,
            progress_callback=print,
            progress_prefix="local_tool_activity",
        )
        if result.response is None:
            if result.orchestration.failure_reason:
                print(f"failure_reason: {result.orchestration.failure_reason}")
            return False
        current_response = result.response.message.content
        print(current_response)
    return all_actions_ok


def _prompt_requests_git_metadata_write(prompt: str) -> bool:
    """Return whether a prompt appears to require writing Git metadata."""

    normalized = prompt.lower()
    return any(
        phrase in normalized
        for phrase in (
            "git commit",
            "git add",
            "commit that",
            "commit this",
            "commit the",
            "make a commit",
            "create a commit",
            "stage and commit",
        )
    )


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
