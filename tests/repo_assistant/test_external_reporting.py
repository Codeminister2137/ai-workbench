"""External diagnostics reflect structured failure evidence without unbounded output."""

import json
import subprocess

import pytest
from ai_agent.external_reporting import (
    MAX_DIAGNOSTIC_LINE_CHARS,
    delegation_status_after_external_agent_events,
    event_mentions_codex_collab_delegation,
    external_agent_exception_hint,
    format_external_agent_stderr,
    note_external_usage,
    print_external_agent_event_summary,
    print_session_usage_summary,
    reset_session_usage,
    session_usage_summary,
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


@pytest.fixture
def clean_usage():
    reset_session_usage()
    yield
    reset_session_usage()


def test_session_usage_aggregates_aliases_with_complete_coverage(clean_usage):
    note_external_usage({"input_tokens": 100, "output_tokens": 50})
    note_external_usage({"inputTokens": 200, "completionTokens": 70, "cost_usd": 0.5})
    summary = session_usage_summary()
    assert summary["calls"] == 2
    assert summary["with_usage"] == 2
    assert summary["unmapped"] == 0
    assert summary["input_tokens"] == {
        "known_sum": 300,
        "observed_calls": 2,
        "coverage": "complete",
    }
    assert summary["output_tokens"]["known_sum"] == 120
    assert summary["output_tokens"]["coverage"] == "complete"
    assert summary["reported_cost_usd"]["known_sum"] == pytest.approx(0.5)
    assert summary["reported_cost_usd"]["coverage"] == "partial"
    assert summary["total_tokens"]["coverage"] == "unknown"


def test_session_usage_counts_missing_and_unmapped_honestly(clean_usage):
    note_external_usage(None)
    note_external_usage({"metering_usage": {"x": 1}})
    note_external_usage({"prompt_tokens": 10})
    summary = session_usage_summary()
    assert summary["calls"] == 3
    assert summary["with_usage"] == 2
    assert summary["unmapped"] == 1
    assert summary["input_tokens"]["coverage"] == "partial"
    assert summary["input_tokens"]["known_sum"] == 10
    assert summary["output_tokens"] == {
        "known_sum": None,
        "observed_calls": 0,
        "coverage": "unknown",
    }


def test_session_usage_ignores_invalid_values(clean_usage):
    note_external_usage(
        {"input_tokens": -5, "output_tokens": 1.5, "reported_cost_usd": float("nan")}
    )
    summary = session_usage_summary()
    assert summary["input_tokens"]["coverage"] == "unknown"
    assert summary["output_tokens"]["coverage"] == "unknown"
    assert summary["reported_cost_usd"]["coverage"] == "unknown"


def test_event_summary_feeds_session_accumulator(clean_usage, capsys):
    summary = ExternalAgentEventSummary(
        None, (), (), (), (), {"input_tokens": 7, "output_tokens": 3}, None, ()
    )
    print_external_agent_event_summary(summary)
    capsys.readouterr()
    print_session_usage_summary()
    line = capsys.readouterr().out.strip()
    assert line.startswith("session_usage: ")
    payload = json.loads(line.partition(": ")[2])
    assert payload["calls"] == 1
    assert payload["input_tokens"]["known_sum"] == 7
    assert payload["output_tokens"]["known_sum"] == 3
