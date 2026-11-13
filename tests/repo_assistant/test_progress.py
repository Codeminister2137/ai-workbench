"""Human progress narration over agent telemetry (P4 R1)."""

from __future__ import annotations

import threading
import time

import pytest
from ai_agent.progress import heartbeat, narrate, reporter


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "local_agent_activity: model_request - provider=ollama model=qwen3:14b",
            "Asking qwen3:14b (ollama)…",
        ),
        ("local_agent_activity: ollama_start - base_url=http://x", "Starting local Ollama…"),
        (
            "local_agent_activity: failed - earlier receipts follow",
            "Agent run failed — earlier receipts follow",
        ),
        (
            "local_agent_activity: completed - iterations=3 tool_results=5 usage=1.2k",
            "Finished (completed): 3 iterations, 5 tool results (1.2k)",
        ),
        (
            "local_tool_activity: recorded - read_file: src.py ok",
            "Tool read_file: src.py ok",
        ),
        (
            "local_tool_activity: ok - write_file: done",
            "Tool write_file (ok): done",
        ),
        (
            "delegated_agent_activity: started - coding_subtask xyz",
            "Delegating subtask: coding_subtask xyz",
        ),
        (
            "delegated_agent_activity: started - context_extraction",
            "Delegating subtask: context_extraction",
        ),
        (
            "delegated_agent_activity: model_request - route=codex model=gpt-x",
            "Subagent asking gpt-x (codex)…",
        ),
        (
            "delegated_agent_activity: completed - iterations=2 tool_results=1",
            "Subagent done: 2 iterations, 1 tool results",
        ),
        (
            "delegated_agent_activity: failed - kind=timeout detail=slow",
            "Subagent failed (timeout): slow",
        ),
        ("model_output_errors: 2", "Model output errors so far: 2"),
        ("completion_failures: 1", "Completion failures so far: 1"),
        (
            "delegation_fanout: n=3 workers=a,b,c",
            "Fanning out to 3 workers (a,b,c)…",
        ),
        (
            "loop_compaction: n=2 summarized=10 tail=4",
            "Compacting transcript…",
        ),
        (
            "model_output_error: provider=x category=y cause_kind=z",
            "Model output error — attempting recovery",
        ),
        (
            "completion_recovery: errors=1 action=feedback",
            "Recovery (1 errors): feedback",
        ),
        (
            "completion_check: missing=tests",
            "Completion check: still missing tests",
        ),
        (
            "groundedness_check: unsupported=claims",
            "Groundedness check: unsupported claims",
        ),
        ("fallback_history: full; kept 3", "Fallback: full; kept 3"),
        (
            "context_budget_omitted: big.md",
            "Context: omitted big.md (over budget)",
        ),
        (
            "context_file_truncated: big.md original_chars=99 budget_chars=5",
            "Context: truncated big.md",
        ),
        (
            "scrutiny_activity: failed - bad",
            "Scrutiny failed: bad",
        ),
        (
            "repair_activity: started - fix it",
            "Repair started: fix it",
        ),
    ],
)
def test_narrate_known_events(raw: str, expected: str) -> None:
    assert narrate(raw) == expected


def test_narrate_passes_unknown_lines_through() -> None:
    assert narrate("something entirely new: x=1") == "something entirely new: x=1"
    assert narrate("") == ""


def test_narrate_never_drops_failure_details() -> None:
    line = "local_agent_activity: failed - boom happened here"
    assert "boom happened here" in narrate(line)


def test_reporter_verbose_prints_raw(capsys: pytest.CaptureFixture) -> None:
    reporter(verbose=True)("local_agent_activity: model_request - provider=a model=b")
    assert capsys.readouterr().out.strip() == (
        "local_agent_activity: model_request - provider=a model=b"
    )


def test_reporter_default_narrates(capsys: pytest.CaptureFixture) -> None:
    reporter(verbose=False)("local_agent_activity: model_request - provider=a model=b")
    assert capsys.readouterr().out.strip() == "Asking b (a)…"


def test_narrate_heartbeat_line() -> None:
    assert narrate("heartbeat: model turn 2 (31s elapsed, still working)") == (
        "Still working: model turn 2 (31s)…"
    )


def test_heartbeat_beats_during_slow_call() -> None:
    events: list[str] = []
    with heartbeat("model turn 1", events.append, interval_seconds=0.05):
        time.sleep(0.22)
    assert len(events) >= 2
    assert all(e.startswith("heartbeat: model turn 1 (") for e in events)
    assert narrate(events[0]).startswith("Still working: model turn 1 (")


def test_heartbeat_silent_when_quick() -> None:
    events: list[str] = []
    with heartbeat("model turn 1", events.append, interval_seconds=60):
        pass
    assert events == []


def test_heartbeat_without_sink_is_noop() -> None:
    before = threading.active_count()
    with heartbeat("model turn 1", None, interval_seconds=0.01):
        time.sleep(0.05)
    assert threading.active_count() <= before


def test_heartbeat_joins_thread_on_error() -> None:
    events: list[str] = []
    before = threading.active_count()
    with pytest.raises(RuntimeError, match="boom"):
        with heartbeat("model turn 1", events.append, interval_seconds=0.01):
            raise RuntimeError("boom")
    assert threading.active_count() <= before
