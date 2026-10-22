"""External diagnostics reflect structured failure evidence without unbounded output."""

import subprocess

import pytest
from ai_agent.external_reporting import (
    MAX_DIAGNOSTIC_LINE_CHARS,
    delegation_status_after_external_agent_events,
    event_mentions_codex_collab_delegation,
    external_agent_exception_hint,
    format_external_agent_stderr,
    print_external_agent_event_summary,
    write_external_agent_stderr,
)
from ai_provider.external_agents import ExternalAgentEventSummary


@pytest.mark.parametrize(
    "event",
    [
        {"type": "tool.failed", "name": "delegate_task"},
        {"name": "delegate_task", "isError": True},
        {"item": {"name": "delegate_task", "status": "failure"}},
        {"content": [{"name": "delegate_task", "status": "failed"}]},
    ],
)
def test_nested_or_typed_failure_never_reports_completed_delegation(event):
    summary = ExternalAgentEventSummary(None, (), (event,), (), (), None, None, ())
    status = delegation_status_after_external_agent_events("disabled", summary)
    assert status == "failed: external Codex MCP delegate_task"


def test_completed_delegation_preserves_prior_status():
    event = {"name": "delegate_task", "status": "completed"}
    summary = ExternalAgentEventSummary(None, (), (event,), (), (), None, None, ())
    status = delegation_status_after_external_agent_events("accepted: local context", summary)
    assert status == "accepted: local context; completed: external Codex MCP delegate_task"


def test_unresolved_mcp_recovery_is_printed_as_a_visible_warning(capsys):
    # ADR-064: the unresolved failure stays visible beside a completed run.
    summary = ExternalAgentEventSummary(
        "Done.",
        (),
        (),
        (),
        (),
        None,
        None,
        (),
        ("unresolved failure", "second unresolved failure"),
    )
    print_external_agent_event_summary(summary)
    output = capsys.readouterr().out
    assert "external_agent_mcp_warning: unresolved failure" in output
    assert "external_agent_mcp_warning: second unresolved failure" in output
    assert "external_agent_failure_reason" not in output


def test_a_failed_run_still_reports_its_failure_reason(capsys):
    summary = ExternalAgentEventSummary(None, (), (), (), (), None, "sandbox denied", ())
    print_external_agent_event_summary(summary)
    output = capsys.readouterr().out
    assert "external_agent_failure_reason: sandbox denied" in output
    assert "external_agent_mcp_warning" not in output


@pytest.mark.parametrize("tool", [None, [], {}, 3, False])
def test_malformed_collaboration_tool_is_ignored_without_crash(tool):
    assert not event_mentions_codex_collab_delegation({"type": "collab_tool_call", "tool": tool})


@pytest.mark.parametrize("command", ["codex exec", ["codex", "exec"]])
def test_timeout_hint_accepts_string_or_argument_vector(command):
    hint = external_agent_exception_hint(subprocess.TimeoutExpired(command, 2))
    assert hint is not None and "--codex-login-device" in hint


def test_console_lines_are_bounded_while_sidecar_retains_evidence(tmp_path):
    stderr = "diagnostic " + "x" * 5000 + "\nFAILED tests/file.py::" + "y" * 5000
    text = format_external_agent_stderr(stderr)
    for line in text.splitlines():
        value = line.partition(": ")[2]
        assert len(value) <= MAX_DIAGNOSTIC_LINE_CHARS
    assert "[truncated]" in text
    path = write_external_agent_stderr(stderr, tmp_path / "run.log")
    assert path is not None and path.read_text() == stderr + "\n"


def test_zero_failure_limit_reports_count_without_failure_rows():
    text = format_external_agent_stderr("FAILED a.py::test_one\nFAILED b.py::test_two", limit=0)
    assert "pytest_failures_detected: 2" in text
    assert "pytest_failures_omitted: 2" in text
    assert "\npytest_failure:" not in text


def test_negative_failure_limit_is_rejected():
    with pytest.raises(ValueError, match="nonnegative"):
        format_external_agent_stderr("details", limit=-1)
