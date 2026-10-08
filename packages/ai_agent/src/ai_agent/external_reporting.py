"""External-client event diagnostics and bounded transcript summaries."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ai_provider.external_agents import (
    ExternalAgentEventSummary,
    _is_noisy_codex_model_refresh_stderr,
)

MAX_DIAGNOSTIC_LINE_CHARS = 1_500


def _diagnostic_line(text: str) -> str:
    if len(text) <= MAX_DIAGNOSTIC_LINE_CHARS:
        return text
    suffix = " ...[truncated]"
    return text[: MAX_DIAGNOSTIC_LINE_CHARS - len(suffix)].rstrip() + suffix


def print_external_agent_event_summary(events: ExternalAgentEventSummary) -> None:
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
        hint = external_agent_failure_hint(events.failure_reason)
        if hint is not None:
            print(f"external_agent_failure_hint: {hint}")
    if events.parse_errors:
        print("external_agent_jsonl_parse_errors_json: " + json.dumps(list(events.parse_errors)))


def delegation_status_after_external_agent_events(
    current_status: str,
    events: ExternalAgentEventSummary,
) -> str:
    """Reflect external Codex MCP delegate_task activity in final delegation status."""

    delegated_events = [
        event for event in events.tool_events if event_mentions_tool(event, "delegate_task")
    ]
    if delegated_events:
        failed = any(event_has_failed_status(event) for event in delegated_events)
        external_status = (
            "failed: external Codex MCP delegate_task"
            if failed
            else "completed: external Codex MCP delegate_task"
        )
    else:
        collab_events = [
            event for event in events.tool_events if event_mentions_codex_collab_delegation(event)
        ]
        if not collab_events:
            return current_status
        failed = any(event_has_failed_status(event) for event in collab_events)
        external_status = (
            "failed: external Codex collab delegation"
            if failed
            else "completed: external Codex collab delegation"
        )
    if current_status == "disabled":
        return external_status
    return f"{current_status}; {external_status}"


def event_mentions_codex_collab_delegation(event: dict[str, Any]) -> bool:
    """Return whether a Codex JSONL event references its internal sidecar agents."""

    tool = event.get("tool")
    if (
        event.get("type") == "collab_tool_call"
        and isinstance(tool, str)
        and tool in {"spawn_agent", "wait"}
    ):
        return True
    nested = event.get("item")
    if isinstance(nested, dict):
        return event_mentions_codex_collab_delegation(nested)
    return False


def event_mentions_tool(event: dict[str, Any], tool_name: str) -> bool:
    """Return whether a parsed external-agent event references one tool name."""

    if any(event.get(key) == tool_name for key in ("name", "tool", "tool_name")):
        return True
    nested = event.get("item")
    if isinstance(nested, dict):
        return event_mentions_tool(nested, tool_name)
    content = event.get("content")
    if isinstance(content, list):
        return any(
            isinstance(item, dict) and event_mentions_tool(item, tool_name) for item in content
        )
    return False


def event_has_failed_status(event: dict[str, Any]) -> bool:
    """Return whether a parsed external-agent event reports a failed tool call."""

    for key in ("type", "event", "kind"):
        value = event.get(key)
        if isinstance(value, str) and value.lower().endswith(
            (".failed", "_failed", ".error", "_error")
        ):
            return True
    if event.get("isError") is True:
        return True
    for key in ("status", "outcome"):
        value = event.get(key)
        if isinstance(value, str) and value.lower() in {"error", "failed", "failure"}:
            return True
    for key in ("error", "failure", "failure_reason", "reason"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, dict):
            return True
    nested = event.get("item")
    if isinstance(nested, dict) and event_has_failed_status(nested):
        return True
    content = event.get("content")
    if isinstance(content, list):
        return any(isinstance(item, dict) and event_has_failed_status(item) for item in content)
    return False


def external_agent_exception_hint(exc: Exception) -> str | None:
    """Return an actionable hint for known external-agent process failures."""

    if isinstance(exc, subprocess.TimeoutExpired):
        command_text = (
            exc.cmd
            if isinstance(exc.cmd, str)
            else " ".join(str(part) for part in exc.cmd)
            if exc.cmd
            else ""
        )
        if "codex" in command_text.lower():
            return (
                "Codex CLI did not finish before the repo assistant timeout. If an auth box "
                "or device-code link was expected, run `.\\scripts\\repo-assistant.ps1 "
                "--codex-login-device` first. If Codex is simply slow, rerun with a larger "
                "`--timeout-seconds` value."
            )
        return "The external process timed out. Rerun with a larger `--timeout-seconds` value."
    return None


def timeout_output_to_text(value: str | bytes | None) -> str:
    """Normalize subprocess timeout output to text for transcripts."""

    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def external_agent_failure_hint(failure_reason: str) -> str | None:
    """Return an actionable hint for known external-agent failure modes."""

    normalized = failure_reason.lower()
    from ai_provider.execution_fallback import explicit_model_overload

    if explicit_model_overload(failure_reason):
        return (
            "The hosted model is temporarily overloaded; this is not an account allowance "
            "exhaustion receipt. Preserve partial work and inspect effects before continuing "
            "with a compatible route. This CLI cannot control the hosted PyCharm assistant."
        )
    if "collab_tool_call" in normalized:
        return (
            "The external Codex CLI failed while using its own multi-agent/collab tool. "
            "This is separate from repo-assistant provider-native delegation; rerun the "
            "task without relying on Codex internal sidecar agents, or use a native "
            "provider route when the repo-assistant delegate_task tool is required."
        )
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


def format_external_agent_stderr(stderr: str, *, limit: int = 5) -> str:
    """Summarize external-agent stderr while leaving full detail in the sidecar."""

    if limit < 0:
        raise ValueError("Diagnostic failure limit must be nonnegative")
    filtered, _ = filter_external_agent_stderr(stderr)
    if not filtered:
        return "external_agent_stderr_summary: only known noisy Codex model refresh output\n"

    lines = [line.strip() for line in filtered.splitlines() if line.strip()]
    summary = [
        "external_agent_stderr_summary: filtered stderr captured; "
        "see external_agent_stderr_file for full output"
    ]
    first_line = first_actionable_stderr_line(lines)
    if first_line is not None:
        summary.append(f"external_agent_stderr_first_line: {_diagnostic_line(first_line)}")

    pytest_failures = extract_pytest_failure_names(lines)
    if pytest_failures:
        summary.append(f"pytest_failures_detected: {len(pytest_failures)}")
        for failure in pytest_failures[:limit]:
            summary.append(f"pytest_failure: {_diagnostic_line(failure)}")
        if len(pytest_failures) > limit:
            summary.append(
                f"pytest_failures_omitted: {len(pytest_failures) - limit}; "
                "see external_agent_stderr_file"
            )
    return "\n".join(summary) + "\n"


def first_actionable_stderr_line(lines: Sequence[str]) -> str | None:
    """Return the first concise stderr line worth showing in the main transcript."""

    for line in lines:
        if (
            line in {"Output:", "FAILURES"}
            or set(line) <= {"=", "_", "-", " "}
            or re.match(r"^[=\s]+[A-Z ]+[=\s]+$", line)
        ):
            continue
        if line.startswith("202") and " ERROR " in line:
            continue
        heading_match = re.match(r"^_+\s+(.+?)\s+_+$", line)
        if heading_match:
            return heading_match.group(1)
        return line
    return None


def extract_pytest_failure_names(lines: Sequence[str]) -> list[str]:
    """Extract failed pytest node IDs or failure headings from captured stderr."""

    failures: list[str] = []
    for line in lines:
        if line.startswith("FAILED "):
            parts = line.split(maxsplit=2)
            if len(parts) >= 2:
                failures.append(parts[1])
    if failures:
        return dedupe_preserving_order(failures)

    heading_pattern = re.compile(r"^_+\s+(.+?)\s+_+$")
    for line in lines:
        match = heading_pattern.match(line)
        if match:
            failures.append(match.group(1))
    return dedupe_preserving_order(failures)


def dedupe_preserving_order(values: Sequence[str]) -> list[str]:
    """Return unique strings in their original order."""

    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def filter_external_agent_stderr(stderr: str) -> tuple[str, int]:
    """Remove repeated non-actionable Codex stderr lines from transcript output."""

    filtered_lines = []
    omitted_noisy_lines = 0
    for line in stderr.splitlines():
        if _is_noisy_codex_model_refresh_stderr(line):
            omitted_noisy_lines += 1
            continue
        filtered_lines.append(line)
    lines = filtered_lines
    if not lines:
        return "", omitted_noisy_lines
    return "\n".join(lines) + "\n", omitted_noisy_lines


def write_external_agent_stderr(stderr: str, log_file: Path | None) -> Path | None:
    """Persist filtered external-agent stderr beside the transcript when available."""

    if log_file is None:
        return None
    stderr_path = log_file.with_suffix(log_file.suffix + ".stderr.log")
    filtered, omitted_noisy_lines = filter_external_agent_stderr(stderr)
    parts: list[str] = []
    if omitted_noisy_lines:
        parts.append(
            f"[omitted {omitted_noisy_lines} known noisy Codex model-refresh stderr line(s)]\n"
        )
    if filtered:
        parts.append(filtered)
    stderr_path.write_text("".join(parts), encoding="utf-8", errors="replace")
    return stderr_path
