from __future__ import annotations

import argparse
import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tracemalloc
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from io import TextIOBase
from pathlib import Path
from typing import Any

# Imports below use the repository's source layout when this example is run directly.
# ruff: noqa: E402, I001
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
    ApprovalPolicyPreset,
    PermissionManager,
    PermissionPolicy,
    ToolCategory,
    ToolContext,
    ToolResult,
    coding_tools_with_delegation,
    codex_authorization_registry,
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
    derive_subtask_profile,
    load_model_catalog,
    plan_delegated_subtask,
    prepare_execution,
)
from ai_orchestrator import PrivacyClass as OrchestratorPrivacyClass
from ai_provider import (
    AIMessage,
    AIRequest,
    AIResponse,
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
from ai_provider.codex_mcp import setup_project_codex_mcp
from ai_provider.external_agents import (
    build_codex_plugin_command,
    codex_plugin_status_by_name,
    parse_codex_plugin_list,
    run_codex_plugin_operation,
)

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
APPROVAL_POLICY_PRESETS = tuple(item.value for item in ApprovalPolicyPreset)
_TIMEOUT_OPTION_NAMES = ("--timeout-seconds",)
_ORCHESTRATED_STAGE_PLAN: tuple[tuple[str, str, str], ...] = (
    (
        "prompt_review",
        "deterministic/local",
        "review the user request and refine or block before provider execution",
    ),
    (
        "planning",
        "primary",
        "ask the primary route for a bounded implementation plan",
    ),
    (
        "auxiliary_panel",
        "derived_local_cheap",
        "run local or cheaper reviewer/test/risk support passes",
    ),
    (
        "implementation",
        "primary",
        "run the selected implementation route with approved local tools",
    ),
    (
        "validation",
        "deterministic/local",
        "run allowed checks and record skipped or failed validation",
    ),
    (
        "scrutiny",
        "derived_local_cheap",
        "critique the final response and claimed validation",
    ),
    (
        "repair",
        "policy_bounded",
        "attempt one targeted repair only when time and findings justify it",
    ),
    (
        "final_handoff",
        "deterministic/local",
        "report changed files, validation, blockers, risks, and next action",
    ),
)
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
_RESPONSE_SCRUTINY_HEADINGS = (
    "VERDICT",
    "SCORE",
    "STRENGTHS",
    "ISSUES",
    "RECOMMENDED_NEXT_ACTION",
    "REVISED_RESPONSE",
)
_RESPONSE_SCRUTINY_VERDICTS = {"pass", "needs_revision", "fail"}
_RESPONSE_SCRUTINY_HEADING_PATTERN = (
    r"(?mi)^[ \t]*(?:#{1,6}[ \t]+)?(?:\*\*)?"
    r"(VERDICT|SCORE|STRENGTHS|ISSUES|RECOMMENDED[ _]NEXT[ _]ACTION|REVISED[ _]RESPONSE)"
    r"(?:\*\*)?:(?:\*\*)?[ \t]*(.*)$"
)
_FENCED_JSON_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


@dataclass(frozen=True)
class ResponseScrutinyReport:
    """Parsed second-pass response-quality report."""

    verdict: str
    score: int
    strengths: str
    issues: str
    recommended_next_action: str
    revised_response: str
    raw_text: str


@dataclass(frozen=True)
class RunMetrics:
    """Local process metrics captured for one CLI run."""

    started_wall_seconds: float
    started_cpu_seconds: float
    tracemalloc_started: bool


@dataclass(frozen=True)
class ExternalAgentConfig:
    """Runtime configuration for an external coding-agent CLI."""

    access_method: AccessMethod
    command: str
    model: str
    cwd: Path
    timeout_seconds: float
    sandbox: str = "workspace-write"
    approval_policy: str = "never"
    ephemeral: bool = True
    json_output: bool = True
    resume: str | None = None
    output_last_message_path: Path | None = None
    output_schema_path: Path | None = None
    web_search: bool = False
    image_paths: tuple[Path, ...] = ()


@dataclass(frozen=True)
class ExternalAgentEventSummary:
    """Structured summary parsed from an external agent JSONL event stream."""

    final_answer: str | None
    command_events: tuple[dict[str, Any], ...]
    tool_events: tuple[dict[str, Any], ...]
    web_search_events: tuple[dict[str, Any], ...]
    file_change_events: tuple[dict[str, Any], ...]
    usage: dict[str, Any] | None
    failure_reason: str | None
    parse_errors: tuple[str, ...]


@dataclass(frozen=True)
class ExternalAgentResult:
    """Completed external coding-agent process result."""

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    last_message: str | None = None
    events: ExternalAgentEventSummary | None = None


class _TeeOutput(TextIOBase):
    """Write CLI output to the terminal and an optional transcript file."""

    def __init__(self, terminal: Any, transcript: Any) -> None:
        self._terminal = terminal
        self._transcript = transcript

    def write(self, text: str) -> int:
        self._transcript.write(text)
        try:
            self._terminal.write(text)
        except UnicodeEncodeError:
            encoding = getattr(self._terminal, "encoding", None) or "utf-8"
            safe_text = text.encode(encoding, errors="replace").decode(encoding)
            self._terminal.write(safe_text)
        return len(text)

    def write_transcript_only(self, text: str) -> int:
        """Write text only to the transcript file, not the terminal."""

        return self._transcript.write(text)

    def flush(self) -> None:
        self._terminal.flush()
        if not self._transcript.closed:
            self._transcript.flush()


def _print_transcript_header(args: argparse.Namespace, argv: Sequence[str] | None) -> None:
    """Print reproducible CLI invocation metadata for transcript logs."""

    effective_argv = list(argv) if argv is not None else sys.argv[1:]
    print("=== CLI invocation ===")
    print(f"timestamp_utc: {datetime.now(UTC).isoformat()}")
    print(f"cwd: {Path.cwd()}")
    print("argv_json: " + json.dumps(effective_argv, ensure_ascii=False))
    print("request:")
    assert args.prompt is not None
    print(args.prompt)
    print()


def _print_model_input(label: str, *, system_prompt: str, prompt: str) -> None:
    """Print the exact model input for evaluation transcripts."""

    print(f"\n=== {label} model input ===")
    print("system_prompt:")
    print("```text")
    print(system_prompt.rstrip())
    print("```")
    print("user_prompt:")
    print("```text")
    print(prompt.rstrip())
    print("```")


def _print_external_agent_input(label: str, *, prompt: str) -> None:
    """Print the exact stdin prompt sent to an external agent CLI."""

    print(f"\n=== {label} external-agent input ===")
    print("stdin_prompt:")
    print("```text")
    print(prompt.rstrip())
    print("```")


def _write_transcript_only(text: str) -> None:
    """Write content to the transcript side of stdout when tee logging is active."""

    writer = getattr(sys.stdout, "write_transcript_only", None)
    if callable(writer):
        writer(text)


def _start_run_metrics() -> RunMetrics:
    """Start local process metrics for transcript observability."""

    tracemalloc_started = False
    if not tracemalloc.is_tracing():
        tracemalloc.start()
        tracemalloc_started = True
    return RunMetrics(
        started_wall_seconds=time.perf_counter(),
        started_cpu_seconds=time.process_time(),
        tracemalloc_started=tracemalloc_started,
    )


def _print_response_usage(prefix: str, response: AIResponse | None) -> None:
    """Print token and provider latency metrics for one response."""

    if response is None:
        print(f"{prefix}_usage_source: unavailable")
        return
    print(f"{prefix}_usage_source: {response.usage.source.value}")
    print(f"{prefix}_input_tokens: {response.usage.input_tokens}")
    print(f"{prefix}_output_tokens: {response.usage.output_tokens}")
    print(f"{prefix}_total_tokens: {response.usage.total_tokens}")
    print(f"{prefix}_provider_latency_ms: {response.latency_ms}")


def _print_run_metrics(
    metrics: RunMetrics,
    *,
    primary_elapsed_seconds: float | None,
    primary_response: AIResponse | None,
    scrutiny_elapsed_seconds: float | None,
    scrutiny_response: AIResponse | None,
) -> None:
    """Print local process and provider-reported metrics for transcript analysis."""

    current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    total_wall_seconds = time.perf_counter() - metrics.started_wall_seconds
    total_cpu_seconds = time.process_time() - metrics.started_cpu_seconds
    print("\n=== Run metrics ===")
    print(f"total_wall_seconds: {total_wall_seconds:.3f}")
    print(f"process_cpu_seconds: {total_cpu_seconds:.3f}")
    print(f"python_memory_current_bytes: {current_bytes}")
    print(f"python_memory_peak_bytes: {peak_bytes}")
    print(f"primary_elapsed_seconds: {_format_optional_seconds(primary_elapsed_seconds)}")
    _print_response_usage("primary", primary_response)
    print(f"scrutiny_elapsed_seconds: {_format_optional_seconds(scrutiny_elapsed_seconds)}")
    _print_response_usage("scrutiny", scrutiny_response)
    if metrics.tracemalloc_started:
        tracemalloc.stop()


def _format_optional_seconds(value: float | None) -> str:
    """Format an optional elapsed-time value for stable transcript output."""

    if value is None:
        return "None"
    return f"{value:.3f}"


def _is_external_agent_access_method(access_method: AccessMethod) -> bool:
    """Return whether an access method uses an external coding-agent client."""

    return access_method in {
        AccessMethod.CODEX_CLI,
        AccessMethod.ANTIGRAVITY_CLI,
        AccessMethod.COPILOT_CLI,
        AccessMethod.KIRO_CLI,
    }


def _default_codex_command() -> str | None:
    """Return Codex CLI from env, PATH, or the PyCharm bundled install."""

    configured = os.environ.get("CODEX_COMMAND")
    if configured:
        return configured

    command = shutil.which("codex")
    if command:
        return command

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None

    bundled = (
        Path(local_app_data)
        / "JetBrains"
        / "PyCharm2025.3"
        / "aia"
        / "codex"
        / "bin"
        / "codex-x86_64-pc-windows-msvc.exe"
    )
    return str(bundled) if bundled.exists() else None


def _external_agent_command(access_method: AccessMethod) -> str | None:
    """Return the configured command for a supported external coding-agent route."""

    if access_method is AccessMethod.CODEX_CLI:
        return _default_codex_command()
    if access_method is AccessMethod.ANTIGRAVITY_CLI:
        return os.environ.get("ANTIGRAVITY_COMMAND") or shutil.which("antigravity")
    if access_method is AccessMethod.COPILOT_CLI:
        return os.environ.get("GITHUB_COPILOT_COMMAND") or shutil.which("copilot")
    if access_method is AccessMethod.KIRO_CLI:
        return os.environ.get("KIRO_COMMAND") or shutil.which("kiro")
    return None


def _external_agent_status() -> dict[str, Any]:
    """Return local discovery status for configured external coding-agent clients."""

    codex_command = _external_agent_command(AccessMethod.CODEX_CLI)
    return {
        "codex_available": codex_command is not None,
        "codex_command": codex_command,
        "codex": _codex_capability_status(codex_command),
        "antigravity_available": _external_agent_command(AccessMethod.ANTIGRAVITY_CLI) is not None,
        "antigravity_command": _external_agent_command(AccessMethod.ANTIGRAVITY_CLI),
        "copilot_available": _external_agent_command(AccessMethod.COPILOT_CLI) is not None,
        "copilot_command": _external_agent_command(AccessMethod.COPILOT_CLI),
        "kiro_available": _external_agent_command(AccessMethod.KIRO_CLI) is not None,
        "kiro_command": _external_agent_command(AccessMethod.KIRO_CLI),
    }


def _run_diagnostic_command(
    command: str,
    *args: str,
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    """Run a read-only local diagnostic command and return redacted process metadata."""

    try:
        completed = subprocess.run(
            (command, *args),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _codex_config_path(command: str | None = None) -> str:
    """Return the Codex config path without reading config contents."""

    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return str(Path(codex_home) / "config.toml")
    if command:
        command_path = Path(command)
        if command_path.parent.name == "bin":
            return str(command_path.parent.parent / "config.toml")
    return str(Path.home() / ".codex" / "config.toml")


def _codex_capability_status(command: str | None) -> dict[str, Any]:
    """Return best-effort Codex CLI diagnostics without exposing secrets."""

    if command is None:
        return {
            "available": False,
            "command": None,
            "version": None,
            "login_status": "unavailable",
            "exec_json_supported": False,
            "config_path": _codex_config_path(command),
            "mcp_list": None,
            "plugin_list": None,
            "plugin_summary": None,
        }

    version = _run_diagnostic_command(command, "--version")
    login = _run_diagnostic_command(command, "login", "status")
    exec_help = _run_diagnostic_command(command, "exec", "--help")
    mcp_list = _run_diagnostic_command(command, "mcp", "list")
    plugin_list = _run_diagnostic_command(command, "plugin", "list")
    return {
        "available": True,
        "command": command,
        "version": version["stdout"] or version["stderr"] or None,
        "login_status": login["stdout"] or login["stderr"] or None,
        "exec_json_supported": "--json" in str(exec_help["stdout"]),
        "config_path": _codex_config_path(command),
        "mcp_list": _diagnostic_text_result(mcp_list),
        "plugin_list": _diagnostic_text_result(plugin_list),
        "plugin_summary": _parse_codex_plugin_list(plugin_list["stdout"])
        if plugin_list["ok"]
        else None,
    }


def _diagnostic_text_result(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize a diagnostic command result for JSON reporting."""

    return {
        "ok": result["ok"],
        "returncode": result["returncode"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
    }


def _parse_codex_plugin_list(text: str) -> dict[str, Any]:
    """Parse the table-like output from `codex plugin list`."""

    marketplaces: list[str] = []
    plugins: list[dict[str, str | None]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("Marketplace `") and line.endswith("`"):
            marketplaces.append(line.removeprefix("Marketplace `").removesuffix("`"))
            continue
        if (
            line.startswith("PLUGIN ")
            or line.startswith("PATH")
            or line.endswith("marketplace.json")
        ):
            continue
        if "@" not in line:
            continue
        plugin = _parse_codex_plugin_row(line)
        if plugin is not None:
            plugins.append(plugin)
    return {
        "marketplaces": marketplaces,
        "available_count": len(plugins),
        "installed_count": sum(
            1 for plugin in plugins if str(plugin["status"]).startswith("installed")
        ),
        "plugins": plugins,
    }


def _parse_codex_plugin_row(line: str) -> dict[str, str | None] | None:
    parts = line.split()
    if len(parts) < 3 or "@" not in parts[0]:
        return None
    name = parts[0]
    if parts[1] == "not" and len(parts) >= 4 and parts[2] == "installed":
        return {
            "name": name,
            "status": "not installed",
            "version": None,
            "path": " ".join(parts[3:]) or None,
        }
    if parts[1].startswith("installed") and len(parts) >= 5 and parts[2] == "enabled":
        return {
            "name": name,
            "status": "installed, enabled",
            "version": parts[3] if parts[3] != "-" else None,
            "path": " ".join(parts[4:]) or None,
        }
    return {
        "name": name,
        "status": parts[1],
        "version": parts[2] if parts[2] != "-" else None,
        "path": " ".join(parts[3:]) if len(parts) > 3 else None,
    }


def _external_agent_config_from_orchestration(
    orchestration: OrchestrationResult,
    *,
    repo_root: Path,
    timeout_seconds: float,
    sandbox: str = "workspace-write",
    approval_policy: str = "never",
    codex_persist_session: bool = False,
    codex_resume: str | None = None,
    output_last_message_path: Path | None = None,
    output_schema_path: Path | None = None,
    web_search: bool = False,
    image_paths: tuple[Path, ...] = (),
) -> ExternalAgentConfig:
    """Adapt a ready orchestration result to an external-agent runtime config."""

    assert orchestration.execution_plan is not None
    target = orchestration.execution_plan.target
    if target.access_method is not AccessMethod.CODEX_CLI:
        raise NotImplementedError(
            f"{target.access_method.value} execution is not implemented yet. "
            "Configure the official command first, then add an executor adapter."
        )
    command = _external_agent_command(target.access_method)
    if command is None:
        raise FileNotFoundError(
            "Could not find Codex CLI. Set CODEX_COMMAND or install/configure Codex CLI."
        )
    return ExternalAgentConfig(
        access_method=target.access_method,
        command=command,
        model=target.model,
        cwd=repo_root,
        timeout_seconds=timeout_seconds,
        sandbox=sandbox,
        approval_policy=approval_policy,
        ephemeral=not codex_persist_session and codex_resume is None,
        resume=codex_resume,
        output_last_message_path=output_last_message_path,
        output_schema_path=output_schema_path,
        web_search=web_search,
        image_paths=image_paths,
    )


def parse_external_agent_jsonl(text: str) -> ExternalAgentEventSummary:
    """Parse Codex-style JSONL events into the stable fields this CLI reports."""

    final_answer = None
    command_events: list[dict[str, Any]] = []
    tool_events: list[dict[str, Any]] = []
    web_search_events: list[dict[str, Any]] = []
    file_change_events: list[dict[str, Any]] = []
    usage = None
    failure_reason = None
    parse_errors: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError as exc:
            parse_errors.append(f"line {line_number}: {exc.msg}")
            continue
        if not isinstance(event, dict):
            parse_errors.append(f"line {line_number}: expected JSON object")
            continue
        event_type = _event_type(event)
        if _is_command_event(event, event_type):
            command_events.append(event)
        if _is_tool_event(event, event_type):
            tool_events.append(event)
        if _is_web_search_event(event, event_type):
            web_search_events.append(event)
        if _is_file_change_event(event, event_type):
            file_change_events.append(event)
        event_usage = _find_usage(event)
        if event_usage is not None:
            usage = event_usage
        event_failure = _find_failure_reason(event, event_type)
        if event_failure is not None:
            failure_reason = event_failure
        event_answer = _find_final_answer(event, event_type)
        if event_answer:
            final_answer = event_answer
    return ExternalAgentEventSummary(
        final_answer=final_answer,
        command_events=tuple(command_events),
        tool_events=tuple(tool_events),
        web_search_events=tuple(web_search_events),
        file_change_events=tuple(file_change_events),
        usage=usage,
        failure_reason=failure_reason,
        parse_errors=tuple(parse_errors),
    )


def _event_type(event: dict[str, Any]) -> str:
    """Return the best-effort type label for a JSONL event."""

    for key in ("type", "event", "kind", "name"):
        value = event.get(key)
        if isinstance(value, str):
            return value.lower()
    nested = event.get("item")
    if isinstance(nested, dict):
        return _event_type(nested)
    return ""


def _is_command_event(event: dict[str, Any], event_type: str) -> bool:
    """Return whether an event appears to describe shell command activity."""

    haystack = _event_haystack(event, event_type)
    return any(token in haystack for token in ("command", "shell", "exec", "terminal"))


def _is_tool_event(event: dict[str, Any], event_type: str) -> bool:
    """Return whether an event appears to describe a tool call."""

    haystack = _event_haystack(event, event_type)
    return "tool" in haystack or "function_call" in haystack


def _is_web_search_event(event: dict[str, Any], event_type: str) -> bool:
    """Return whether an event appears to describe Codex web search activity."""

    haystack = _event_haystack(event, event_type)
    return "web_search" in haystack


def _is_file_change_event(event: dict[str, Any], event_type: str) -> bool:
    """Return whether an event appears to describe a file modification."""

    haystack = _event_haystack(event, event_type)
    return any(token in haystack for token in ("file_change", "patch", "diff", "edit", "write"))


def _event_haystack(event: dict[str, Any], event_type: str) -> str:
    """Build a shallow searchable label string for classifying event families."""

    labels = [event_type]
    for key in ("type", "event", "kind", "name", "subtype", "status"):
        value = event.get(key)
        if isinstance(value, str):
            labels.append(value.lower())
    nested = event.get("item")
    if isinstance(nested, dict):
        labels.append(_event_haystack(nested, _event_type(nested)))
    return " ".join(labels)


def _find_usage(value: Any) -> dict[str, Any] | None:
    """Find the first nested usage/token payload in an event."""

    if isinstance(value, dict):
        for key, nested in value.items():
            key_lower = key.lower()
            if key_lower == "usage" and isinstance(nested, dict):
                return nested
            if "token" in key_lower and isinstance(nested, dict):
                return nested
            found = _find_usage(nested)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_usage(item)
            if found is not None:
                return found
    return None


def _find_failure_reason(event: dict[str, Any], event_type: str) -> str | None:
    """Find a failure or error reason in an event."""

    if not _has_failure_marker(event, event_type):
        return None
    for key in ("error", "failure", "details"):
        value = event.get(key)
        if isinstance(value, dict):
            for nested_key in ("message", "error", "failure_reason", "reason", "detail"):
                nested_value = value.get(nested_key)
                if isinstance(nested_value, str) and nested_value.strip():
                    return nested_value.strip()
            nested = _find_failure_reason(value, _event_type(value) or key)
            if nested is not None:
                return nested
    for key in ("message", "error", "failure_reason", "reason", "detail"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    nested = event.get("item")
    if isinstance(nested, dict):
        nested_failure = _find_failure_reason(nested, _event_type(nested))
        if nested_failure is not None:
            return nested_failure
    return event_type or "external agent reported failure"


def _has_failure_marker(event: dict[str, Any], event_type: str) -> bool:
    """Return whether event labels explicitly report a failure."""

    labels = [event_type]
    for key in ("type", "event", "kind", "name", "subtype", "status"):
        value = event.get(key)
        if isinstance(value, str):
            labels.append(value.lower())
    nested = event.get("item")
    if isinstance(nested, dict):
        labels.append(_event_type(nested))
        status = nested.get("status")
        if isinstance(status, str):
            labels.append(status.lower())
    return any(
        label in {"error", "failed", "failure"}
        or label.endswith(".failed")
        or label.endswith("_failed")
        or label.endswith(".error")
        or label.endswith("_error")
        for label in labels
    )


def _find_final_answer(event: dict[str, Any], event_type: str) -> str | None:
    """Find a final assistant answer in a Codex JSONL event."""

    explicit = event.get("final_answer")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    if "final" in event_type or event.get("role") == "assistant":
        text = _find_text_payload(event)
        if text:
            return text
    if event_type in {"assistant_message", "agent_message", "message", "response"}:
        text = _find_text_payload(event)
        if text:
            return text
    nested = event.get("item")
    if isinstance(nested, dict):
        return _find_final_answer(nested, _event_type(nested))
    return None


def _find_text_payload(value: Any) -> str | None:
    """Find a human-readable text payload inside common event shapes."""

    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for key in ("text", "content", "message", "answer", "output"):
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
        for key in ("content", "message", "delta", "item"):
            nested = value.get(key)
            found = _find_text_payload(nested)
            if found:
                return found
    if isinstance(value, list):
        parts = [_find_text_payload(item) for item in value]
        text = "\n".join(part for part in parts if part)
        return text or None
    return None


def _build_external_agent_command(config: ExternalAgentConfig) -> tuple[str, ...]:
    """Build the noninteractive command for an external coding-agent client."""

    if config.access_method is not AccessMethod.CODEX_CLI:
        raise NotImplementedError(f"{config.access_method.value} execution is not implemented.")

    command = [config.command]
    if config.web_search:
        command.append("--search")
    if config.approval_policy:
        command.extend(
            [
                "--ask-for-approval",
                _codex_approval_policy(config.approval_policy),
            ]
        )

    if config.resume is not None:
        command.extend(["exec", "resume", "--model", config.model])
        if config.json_output:
            command.append("--json")
        if config.output_last_message_path is not None:
            command.extend(["--output-last-message", str(config.output_last_message_path)])
        if config.output_schema_path is not None:
            command.extend(["--output-schema", str(config.output_schema_path)])
        for image_path in config.image_paths:
            command.extend(["--image", str(image_path)])
        if config.resume == "last":
            command.append("--last")
        else:
            command.append(config.resume)
        command.append("-")
        return tuple(command)

    command.extend(
        [
            "exec",
            "--cd",
            str(config.cwd),
            "--model",
            config.model,
            "--sandbox",
            config.sandbox,
        ]
    )
    if config.ephemeral:
        command.append("--ephemeral")
    if config.json_output:
        command.append("--json")
    if config.output_last_message_path is not None:
        command.extend(["--output-last-message", str(config.output_last_message_path)])
    if config.output_schema_path is not None:
        command.extend(["--output-schema", str(config.output_schema_path)])
    for image_path in config.image_paths:
        command.extend(["--image", str(image_path)])
    command.append("-")
    return tuple(command)


def _codex_approval_policy(approval_policy: str) -> str:
    """Map repo-assistant approval presets to Codex CLI approval policies."""

    if approval_policy == "interactive":
        return "on-request"
    return "never"


def _run_external_agent(prompt: str, config: ExternalAgentConfig) -> ExternalAgentResult:
    """Run an external coding-agent process with the prompt on stdin."""

    command = _build_external_agent_command(config)
    if config.output_last_message_path is not None:
        config.output_last_message_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        command,
        input=prompt,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=config.timeout_seconds,
        cwd=config.cwd,
    )
    stdout = completed.stdout or ""
    events = parse_external_agent_jsonl(stdout) if config.json_output and stdout else None
    last_message = None
    if config.output_last_message_path is not None and config.output_last_message_path.exists():
        last_message = config.output_last_message_path.read_text(encoding="utf-8", errors="replace")
    return ExternalAgentResult(
        command=command,
        returncode=completed.returncode,
        stdout=stdout,
        stderr=completed.stderr or "",
        last_message=last_message,
        events=events,
    )


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


def build_response_scrutiny_prompt(original_prompt: str, response: str) -> str:
    """Build a bounded second-pass prompt for evaluating one assistant response."""

    return (
        "Original repository-analysis request:\n"
        f"{original_prompt}\n\n"
        "Candidate assistant response:\n"
        f"{response}\n\n"
        "Scrutinize the candidate response using the required report format."
    )


def parse_response_scrutiny_report(text: str) -> ResponseScrutinyReport:
    """Parse and validate the structured response-scrutiny report."""

    sections = _parse_response_scrutiny_heading_sections(text)
    if sections is None:
        sections = _parse_response_scrutiny_json_sections(text)

    missing = [heading for heading in _RESPONSE_SCRUTINY_HEADINGS if heading not in sections]
    if missing:
        raise ValueError("missing scrutiny heading(s): " + ", ".join(missing))

    verdict = sections["VERDICT"].strip().lower()
    if verdict not in _RESPONSE_SCRUTINY_VERDICTS:
        raise ValueError(f"invalid scrutiny verdict: {sections['VERDICT']!r}")

    try:
        score = int(sections["SCORE"].strip())
    except ValueError as exc:
        raise ValueError(f"invalid scrutiny score: {sections['SCORE']!r}") from exc
    if not 0 <= score <= 10:
        raise ValueError(f"scrutiny score out of range: {score}")

    return ResponseScrutinyReport(
        verdict=verdict,
        score=score,
        strengths=sections["STRENGTHS"],
        issues=sections["ISSUES"],
        recommended_next_action=sections["RECOMMENDED_NEXT_ACTION"],
        revised_response=sections["REVISED_RESPONSE"],
        raw_text=text,
    )


def _parse_response_scrutiny_heading_sections(text: str) -> dict[str, str] | None:
    """Parse report sections from canonical heading lines."""

    matches = list(
        re.finditer(
            _RESPONSE_SCRUTINY_HEADING_PATTERN,
            text,
        )
    )
    if not matches:
        return None

    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        heading = match.group(1).upper().replace(" ", "_")
        if heading in sections:
            raise ValueError(f"duplicate scrutiny heading: {heading}")
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        first_line = match.group(2).strip()
        continuation = text[match.end() : section_end].strip()
        sections[heading] = f"{first_line}\n{continuation}".strip() if continuation else first_line

    return sections


def _parse_response_scrutiny_json_sections(text: str) -> dict[str, str]:
    """Parse report sections from a JSON object with canonical keys."""

    candidate = text.strip()
    match = _FENCED_JSON_PATTERN.search(candidate)
    if match:
        candidate = match.group(1)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        heading: _stringify_scrutiny_section(parsed[heading])
        for heading in _RESPONSE_SCRUTINY_HEADINGS
        if heading in parsed
    }


def _stringify_scrutiny_section(value: Any) -> str:
    """Convert JSON scrutiny values to stable transcript text."""

    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, indent=2)


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
    progress_callback: Callable[[str], None] | None = None,
) -> tuple[str | None, str]:
    """Extract source-grounded context locally for injection into a primary prompt."""

    if progress_callback is not None:
        progress_callback("delegated_agent_activity: started - context_extraction")
    decision = assess_delegation(
        task_type=primary_profile.task_type,
        delegation_kind=DelegationKind.CONTEXT_EXTRACTION,
    )
    if not decision.allowed:
        if progress_callback is not None:
            progress_callback(
                f"delegated_agent_activity: rejected - {_activity_preview(decision.reason)}"
            )
        return None, f"rejected: {decision.reason}"
    delegation_context, sources = build_delegation_context(
        context_files,
        max_chars=max_chars,
    )
    if not sources:
        if progress_callback is not None:
            progress_callback("delegated_agent_activity: skipped - no repository context")
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
    if progress_callback is not None:
        progress_callback(
            "delegated_agent_activity: model_request - "
            f"route={plan.execution_plan.target.route_id} sources={len(sources)}"
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
        if progress_callback is not None:
            progress_callback(
                "delegated_agent_activity: rejected - local summary contained no "
                "verifiable source citation"
            )
        return None, "rejected: local summary contained no verifiable source citation"
    if progress_callback is not None:
        progress_callback(f"delegated_agent_activity: completed - {_activity_preview(summary)}")
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
    authorize_action: Callable[[AssistantAction], bool] | None = None,
    input_func: Callable[[str], str] = input,
    allow_outside_files: bool = False,
    command_timeout_seconds: float = 60.0,
) -> tuple[AssistantActionResult, ...]:
    """Execute approved local actions proposed by the assistant."""

    return tuple(
        _execute_action(
            action,
            repo_root,
            authorize_action=authorize_action,
            input_func=input_func,
            allow_outside_files=allow_outside_files,
            command_timeout_seconds=command_timeout_seconds,
        )
        for action in actions
    )


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
    if not _argv_has_option(argv, _TIMEOUT_OPTION_NAMES):
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


def _print_orchestrated_stage_plan(
    *,
    args: argparse.Namespace,
    orchestration: OrchestrationResult,
) -> None:
    """Print the foreground unattended workflow plan without running stages."""

    print("\n=== Orchestrated away-work plan ===")
    print("away_orchestrated: enabled")
    print(f"away_plan_mode: {args.mode}")
    print(f"away_plan_budget_minutes: {args.away_minutes:g}")
    print(f"away_plan_budget_seconds: {args.away_minutes * 60:g}")
    if args.mode == "plan":
        print("away_plan_execution: not_started")
        print("away_plan_skip_reason: plan mode never contacts a provider")
    else:
        print("away_plan_execution: foreground_run")
    if orchestration.execution_plan is not None:
        target = orchestration.execution_plan.target
        print(f"away_plan_primary_route_id: {target.route_id}")
        print(f"away_plan_primary_provider: {target.provider}")
        print(f"away_plan_primary_model: {target.model}")
        print(f"away_plan_primary_access_method: {target.access_method.value}")
        print(f"away_plan_primary_cost_policy_tier: {target.cost_policy_tier.value}")
    else:
        print("away_plan_primary_route_id: unavailable")
    print("away_plan_auxiliary_route_policy: derived_local_cheap")
    print("away_plan_external_writes: disabled")
    print(f"away_plan_approval_policy: {args.approval_policy}")
    for name, route, purpose in _ORCHESTRATED_STAGE_PLAN:
        print(f"away_stage: {name} route={route} status=planned purpose={purpose}")


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
        "--codex-login",
        action="store_true",
        help=(
            "Run `codex login` so Codex can refresh its local ChatGPT/OAuth session. "
            "This mutates local Codex auth state and cannot be combined with a prompt."
        ),
    )
    parser.add_argument(
        "--codex-login-device",
        action="store_true",
        help=(
            "Run `codex login --device-auth` for device-code authentication. "
            "This mutates local Codex auth state and cannot be combined with a prompt."
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
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=180.0,
        help=(
            "Provider timeout. For external-agent routes, this is an inactivity "
            "timeout and model output resets the timer."
        ),
    )
    parser.add_argument(
        "--away-minutes",
        type=float,
        help=(
            "Visible foreground work budget for unattended runs. If --timeout-seconds "
            "is not supplied, provider and external-agent timeouts are set to this "
            "many minutes."
        ),
    )
    parser.add_argument(
        "--orchestrated",
        action="store_true",
        help=(
            "Plan or run the staged foreground unattended workflow. Requires "
            "--away-minutes and currently exposes a dry-run stage plan in plan mode."
        ),
    )
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
            "Use provider-native tool calling with the ai-agent loop. This is the "
            "default for executed implement-mode provider routes; the flag is kept "
            "for explicitness and compatibility."
        ),
    )
    parser.add_argument(
        "--no-native-tools",
        action="store_true",
        help=(
            "Disable the default provider-native tool loop and use the older "
            "single-response provider execution path."
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
    if args.codex_login or args.codex_login_device:
        return _run_codex_login(args=args, repo_root=repo_root, parser=parser)
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
    _configure_away_mode(args, argv, parser)
    if args.orchestrated and args.away_minutes is None:
        parser.error("--orchestrated requires --away-minutes")
    if args.native_tools and args.no_native_tools:
        parser.error("--native-tools cannot be combined with --no-native-tools")
    use_native_tools = args.native_tools or (
        args.mode == "implement" and args.execute and not args.no_native_tools
    )
    args.native_tools = use_native_tools
    if args.mode in {"ask", "review"} and (args.apply_actions or args.native_tools):
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
    delegation_status = "disabled"
    if args.delegate_context and args.execute:
        delegated_summary, delegation_status = run_local_context_delegation(
            context_files,
            profile,
            catalog,
            max_chars=args.delegation_context_budget_chars,
            progress_callback=print,
        )
        if delegated_summary is not None:
            prompt = f"{prompt}\n\n## Verified local context extraction\n{delegated_summary}"
    elif args.delegate_context:
        delegation_status = "planned: requires --execute"
    primary_system_prompt = build_default_system_prompt(args.system)
    if args.away_minutes is not None:
        primary_system_prompt = _system_prompt_with_away_budget(
            primary_system_prompt,
            away_minutes=args.away_minutes,
        )
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
        if (
            external_orchestration.execution_plan.target.access_method is AccessMethod.CODEX_CLI
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
    print(
        f"context_chars: {sum(len(item.content) for item in context_files)}"
        + (f"/{args.context_budget_chars}" if context_budget_chars is not None else "/unlimited")
    )
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
            delegation_enabled=args.mode == "implement" and not args.no_native_tools,
        )
    if args.orchestrated:
        _print_orchestrated_stage_plan(args=args, orchestration=result.orchestration)
    print("\n=== Assistant response ===")
    assistant_response_text = None
    if args.native_tools and args.execute and result.config is not None:
        try:
            native_result = _run_native_agent(
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
            print(f"status: {final_status}")
            print(f"delegation: {delegation_status}")
            print(f"execution_status: {execution_status}")
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
        print(assistant_response_text)
        delegation_status = _delegation_status_after_native_tools(
            delegation_status,
            native_result.tool_results,
        )
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
        final_status = "failed"
        execution_status = "failed"
    scrutiny_result = None
    scrutiny_elapsed_seconds = None
    if args.scrutinize_response and assistant_response_text is not None:
        print("\n=== Response scrutiny ===")
        scrutiny_failed = False
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
    print(f"status: {final_status}")
    print(f"delegation: {delegation_status}")
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
    command = _external_agent_command(AccessMethod.CODEX_CLI)
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
    before = _run_diagnostic_command(command, "plugin", "list", timeout_seconds=10.0)
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

    after = _run_diagnostic_command(command, "plugin", "list", timeout_seconds=10.0)
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
    command = _external_agent_command(AccessMethod.CODEX_CLI)
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

    status = _run_diagnostic_command(command, "login", "status", timeout_seconds=10.0)
    print(f"codex_login_returncode: {result.returncode}")
    print(f"codex_login_status_ok: {status['ok']}")
    if status["stdout"]:
        print(f"codex_login_status_stdout: {status['stdout']}")
    if status["stderr"]:
        print(f"codex_login_status_stderr: {status['stderr']}")
    execution_status = "completed" if result.returncode == 0 and status["ok"] else "failed"
    print(f"execution_status: {execution_status}")
    return 0 if execution_status == "completed" else result.returncode or 1


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
    if args.away_minutes is not None:
        print(f"away_budget_minutes: {args.away_minutes:g}")
        print(f"away_budget_seconds: {args.away_minutes * 60:g}")
        print(f"away_timeout_seconds: {args.timeout_seconds:g}")
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
    response_header_printed = False
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
        print("external_agent_timeout_mode: inactivity")
        print(f"external_agent_inactivity_timeout_seconds: {config.timeout_seconds:g}")
        if config.image_paths:
            print(
                "external_agent_images_json: "
                + json.dumps([str(path) for path in config.image_paths])
            )
        if args.orchestrated:
            _print_orchestrated_stage_plan(args=args, orchestration=orchestration)
        print("\n=== Assistant response ===")
        response_header_printed = True
        if args.execute and args.mode != "plan":
            external_prompt = _external_agent_prompt_with_execution_metadata(
                prompt,
                approval_policy=args.approval_policy,
                sandbox=config.sandbox,
                mode=args.mode,
            )
            primary_started = time.perf_counter()
            external_result = _run_external_agent(external_prompt, config)
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
                full_stderr_path = _write_external_agent_stderr(
                    external_result.stderr,
                    args.log_file,
                )
                if full_stderr_path is not None:
                    print(f"external_agent_stderr_file: {full_stderr_path}")
                stderr_text = _format_external_agent_stderr(external_result.stderr)
                if stderr_text:
                    print(stderr_text, end="")
                    if not stderr_text.endswith("\n"):
                        print()
                else:
                    print(
                        "external_agent_stderr_summary: only known noisy Codex model refresh output"
                    )
            parsed_failure = (
                external_result.events.failure_reason
                if external_result.events is not None
                else None
            )
            if external_result.returncode != 0 and parsed_failure is None:
                print(
                    "external_agent_failure_reason: "
                    f"process exited with code {external_result.returncode}"
                )
                if external_result.stderr:
                    print("external_agent_failure_hint: inspect external_agent_stderr_file")
            execution_status = (
                "completed"
                if external_result.returncode == 0 and parsed_failure is None
                else "failed"
            )
            exit_code = 0 if execution_status == "completed" else external_result.returncode or 1
        else:
            print("execution: skipped")
    except (FileNotFoundError, NotImplementedError, subprocess.TimeoutExpired) as exc:
        if not response_header_printed:
            print("\n=== Assistant response ===")
        print(f"failure_reason: {exc}")
        if isinstance(exc, subprocess.TimeoutExpired):
            _print_external_agent_timeout_output(exc)
        hint = _external_agent_exception_hint(exc)
        if hint is not None:
            print(f"failure_hint: {hint}")
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


def _external_agent_prompt_with_execution_metadata(
    prompt: str,
    *,
    approval_policy: str,
    sandbox: str,
    mode: str,
) -> str:
    """Add execution metadata so external agents do not infer the wrong sandbox."""

    return (
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
        hint = _external_agent_failure_hint(events.failure_reason)
        if hint is not None:
            print(f"external_agent_failure_hint: {hint}")
    if events.parse_errors:
        print("external_agent_jsonl_parse_errors_json: " + json.dumps(list(events.parse_errors)))


def _external_agent_exception_hint(exc: Exception) -> str | None:
    """Return an actionable hint for known external-agent process failures."""

    if isinstance(exc, subprocess.TimeoutExpired):
        command_text = " ".join(str(part) for part in exc.cmd) if exc.cmd else ""
        if "codex" in command_text.lower():
            return (
                "Codex CLI did not finish before the repo assistant timeout. If an auth box "
                "or device-code link was expected, run `.\\scripts\\repo-assistant.ps1 "
                "--codex-login-device` first. If Codex is simply slow, rerun with a larger "
                "`--timeout-seconds` value."
            )
        return "The external process timed out. Rerun with a larger `--timeout-seconds` value."
    return None


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


def _timeout_output_to_text(value: str | bytes | None) -> str:
    """Normalize subprocess timeout output to text for transcripts."""

    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _external_agent_failure_hint(failure_reason: str) -> str | None:
    """Return an actionable hint for known external-agent failure modes."""

    normalized = failure_reason.lower()
    if "401" in normalized and "unauthorized" in normalized and "api.openai.com" in normalized:
        return (
            "Codex CLI reached OpenAI but its local ChatGPT/API session was rejected. "
            "Run `codex login status`, then refresh the local Codex login if needed. "
            "If using the PyCharm-bundled Codex CLI, re-authenticate through PyCharm/Codex "
            "or set CODEX_COMMAND to a separately authenticated Codex CLI."
        )
    if "missing bearer or basic authentication" in normalized:
        return (
            "The external agent did not send usable authentication. Refresh that agent's "
            "local login/session or configure the intended command override."
        )
    return None


def _write_external_agent_raw_jsonl(raw_jsonl: str) -> None:
    """Preserve raw external-agent JSONL in transcript logs without console noise."""

    if not raw_jsonl:
        return
    _write_transcript_only("\n=== External agent raw JSONL ===\n")
    _write_transcript_only(raw_jsonl)
    if not raw_jsonl.endswith("\n"):
        _write_transcript_only("\n")


def _format_external_agent_stderr(stderr: str, *, limit: int = 2000) -> str:
    """Bound noisy external-agent stderr while pointing to the complete log."""

    filtered = _filter_external_agent_stderr(stderr)
    if len(filtered) <= limit:
        return filtered
    omitted = len(filtered) - limit
    return (
        "external_agent_stderr_preview: "
        "truncated non-JSON stderr; see external_agent_stderr_file for complete output\n"
        + filtered[:limit].rstrip()
        + f"\n[stderr preview truncated: {omitted} characters omitted; "
        "see external_agent_stderr_file for full stderr]\n"
    )


def _filter_external_agent_stderr(stderr: str) -> str:
    """Remove repeated non-actionable Codex stderr lines from the main transcript."""

    lines = [line for line in stderr.splitlines() if not _is_noisy_codex_model_refresh_stderr(line)]
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _write_external_agent_stderr(stderr: str, log_file: Path | None) -> Path | None:
    """Persist complete external-agent stderr beside the transcript when available."""

    if log_file is None:
        return None
    stderr_path = log_file.with_suffix(log_file.suffix + ".stderr.log")
    stderr_path.write_text(stderr, encoding="utf-8", errors="replace")
    return stderr_path


def _is_noisy_codex_model_refresh_stderr(line: str) -> bool:
    """Return whether a Codex stderr line is known noisy model metadata refresh output."""

    return (
        "codex_models_manager::manager" in line
        and "failed to refresh available models" in line
        and "unknown variant `max`" in line
    )


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
                quality_threshold=QualityThreshold.STANDARD,
                latency_target=LatencyTarget.BACKGROUND,
                cost_policy_tier=CostPolicyTier.LOCAL_ONLY,
                privacy_class=OrchestratorPrivacyClass.LOCAL_ONLY,
            )
            child_orchestration = prepare_execution(
                task,
                child_profile,
                load_model_catalog(
                    getattr(
                        args,
                        "catalog",
                        Path("packages/ai_orchestrator/examples/model_catalog.toml"),
                    )
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
    result = agent.run(
        prompt,
        system_prompt=build_default_system_prompt(args.system),
        model=config.model,
        privacy_class=PrivacyClass(profile.privacy_class.value),
    )
    if progress_callback is not None:
        progress_callback(
            f"local_agent_activity: completed - iterations={result.iterations} "
            f"tool_results={len(result.tool_results)}"
        )
        for tool_result in result.tool_results:
            status = "error" if tool_result.is_error else "ok"
            progress_callback(
                f"local_tool_activity: {status} - {tool_result.name}: "
                f"{_activity_preview(tool_result.output)}"
            )
    return result


def _activity_preview(value: str, *, limit: int = 160) -> str:
    """Return a bounded single-line activity detail."""

    preview = " ".join(value.strip().split())
    if len(preview) <= limit:
        return preview
    return preview[: max(0, limit - 15)].rstrip() + " ...[truncated]"


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
            system_prompt=build_default_system_prompt(args.system),
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


def _codex_sandbox_for_approval_policy(approval_policy: str) -> str:
    """Map model-neutral approval presets to supported Codex CLI sandbox modes."""

    preset = ApprovalPolicyPreset(approval_policy)
    if preset is ApprovalPolicyPreset.READ_ONLY:
        return "read-only"
    if preset is ApprovalPolicyPreset.TRUSTED_LOCAL:
        return "danger-full-access"
    return "workspace-write"


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
    authorize_action: Callable[[AssistantAction], bool] | None,
    input_func: Callable[[str], str],
    allow_outside_files: bool,
    command_timeout_seconds: float,
) -> AssistantActionResult:
    if authorize_action is not None and not authorize_action(action):
        return AssistantActionResult(
            action.action_type,
            False,
            f"Skipped by approval policy: {action.action_type}",
        )
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
