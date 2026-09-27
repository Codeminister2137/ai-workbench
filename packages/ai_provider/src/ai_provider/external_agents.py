from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_orchestrator import AccessMethod, OrchestrationResult


@dataclass(frozen=True)
class ExternalAgentConfig:
    """Runtime configuration for an external coding-agent CLI."""

    access_method: AccessMethod
    command: str
    model: str
    cwd: Path
    timeout_seconds: float
    sandbox: str = "workspace-write"
    ephemeral: bool = True
    json_output: bool = True
    resume: str | None = None
    output_last_message_path: Path | None = None
    output_schema_path: Path | None = None
    web_search: bool = False


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


def is_external_agent_access_method(access_method: AccessMethod) -> bool:
    """Return whether an access method uses an external coding-agent client."""

    return access_method in {
        AccessMethod.CODEX_CLI,
        AccessMethod.ANTIGRAVITY_CLI,
        AccessMethod.COPILOT_CLI,
        AccessMethod.KIRO_CLI,
    }


def default_codex_command() -> str | None:
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


def external_agent_command(access_method: AccessMethod) -> str | None:
    """Return the configured command for a supported external coding-agent route."""

    if access_method is AccessMethod.CODEX_CLI:
        return default_codex_command()
    if access_method is AccessMethod.ANTIGRAVITY_CLI:
        return os.environ.get("ANTIGRAVITY_COMMAND") or shutil.which("antigravity")
    if access_method is AccessMethod.COPILOT_CLI:
        return os.environ.get("GITHUB_COPILOT_COMMAND") or shutil.which("copilot")
    if access_method is AccessMethod.KIRO_CLI:
        return os.environ.get("KIRO_COMMAND") or shutil.which("kiro")
    return None


def external_agent_status() -> dict[str, Any]:
    """Return local discovery status for configured external coding-agent clients."""

    codex_command = external_agent_command(AccessMethod.CODEX_CLI)
    return {
        "codex_available": codex_command is not None,
        "codex_command": codex_command,
        "codex": codex_capability_status(codex_command),
        "antigravity_available": external_agent_command(AccessMethod.ANTIGRAVITY_CLI) is not None,
        "antigravity_command": external_agent_command(AccessMethod.ANTIGRAVITY_CLI),
        "copilot_available": external_agent_command(AccessMethod.COPILOT_CLI) is not None,
        "copilot_command": external_agent_command(AccessMethod.COPILOT_CLI),
        "kiro_available": external_agent_command(AccessMethod.KIRO_CLI) is not None,
        "kiro_command": external_agent_command(AccessMethod.KIRO_CLI),
    }


def run_diagnostic_command(
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


def codex_config_path(command: str | None = None) -> str:
    """Return the Codex config path without reading config contents."""

    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return str(Path(codex_home) / "config.toml")
    if command:
        command_path = Path(command)
        if command_path.parent.name == "bin":
            return str(command_path.parent.parent / "config.toml")
    return str(Path.home() / ".codex" / "config.toml")


def codex_capability_status(command: str | None) -> dict[str, Any]:
    """Return best-effort Codex CLI diagnostics without exposing secrets."""

    if command is None:
        return {
            "available": False,
            "command": None,
            "version": None,
            "login_status": "unavailable",
            "exec_json_supported": False,
            "config_path": codex_config_path(command),
            "mcp_list": None,
            "plugin_list": None,
        }

    version = run_diagnostic_command(command, "--version")
    login = run_diagnostic_command(command, "login", "status")
    exec_help = run_diagnostic_command(command, "exec", "--help")
    mcp_list = run_diagnostic_command(command, "mcp", "list")
    plugin_list = run_diagnostic_command(command, "plugin", "list")
    return {
        "available": True,
        "command": command,
        "version": version["stdout"] or version["stderr"] or None,
        "login_status": login["stdout"] or login["stderr"] or None,
        "exec_json_supported": "--json" in str(exec_help["stdout"]),
        "config_path": codex_config_path(command),
        "mcp_list": diagnostic_text_result(mcp_list),
        "plugin_list": diagnostic_text_result(plugin_list),
    }


def diagnostic_text_result(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize a diagnostic command result for JSON reporting."""

    return {
        "ok": result["ok"],
        "returncode": result["returncode"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
    }


def external_agent_config_from_orchestration(
    orchestration: OrchestrationResult,
    *,
    repo_root: Path,
    timeout_seconds: float,
    codex_persist_session: bool = False,
    codex_resume: str | None = None,
    output_last_message_path: Path | None = None,
    output_schema_path: Path | None = None,
    web_search: bool = False,
) -> ExternalAgentConfig:
    """Adapt a ready orchestration result to an external-agent runtime config."""

    assert orchestration.execution_plan is not None
    target = orchestration.execution_plan.target
    if target.access_method is not AccessMethod.CODEX_CLI:
        raise NotImplementedError(
            f"{target.access_method.value} execution is not implemented yet. "
            "Configure the official command first, then add an executor adapter."
        )
    command = external_agent_command(target.access_method)
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
        ephemeral=not codex_persist_session and codex_resume is None,
        resume=codex_resume,
        output_last_message_path=output_last_message_path,
        output_schema_path=output_schema_path,
        web_search=web_search,
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
        if event_failure is not None and (failure_reason is None or event_failure != event_type):
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


def build_external_agent_command(config: ExternalAgentConfig) -> tuple[str, ...]:
    """Build the noninteractive command for an external coding-agent client."""

    if config.access_method is not AccessMethod.CODEX_CLI:
        raise NotImplementedError(f"{config.access_method.value} execution is not implemented.")

    command = [config.command]
    if config.web_search:
        command.append("--search")

    if config.resume is not None:
        command.extend(["exec", "resume", "--model", config.model])
        if config.json_output:
            command.append("--json")
        if config.output_last_message_path is not None:
            command.extend(["--output-last-message", str(config.output_last_message_path)])
        if config.output_schema_path is not None:
            command.extend(["--output-schema", str(config.output_schema_path)])
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
    command.append("-")
    return tuple(command)


def run_external_agent(
    prompt: str,
    config: ExternalAgentConfig,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> ExternalAgentResult:
    """Run an external coding-agent process with the prompt on stdin."""

    command = build_external_agent_command(config)
    if config.output_last_message_path is not None:
        config.output_last_message_path.parent.mkdir(parents=True, exist_ok=True)
    completed = runner(
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

    haystack = _event_haystack(event, event_type)
    if not any(token in haystack for token in ("error", "failed", "failure")):
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
    return event_type or "external agent reported failure"


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
