"""File-backed run events and the run cancel-race guard (pure record helpers)."""

import json

import pytest
from ai_agent.run_tracking import (
    TERMINAL_RUN_STATUSES,
    append_run_event,
    ensure_run_not_cancelled,
    request_run_cancel,
    run_cancelled,
    run_events,
)


def test_terminal_statuses_never_replay() -> None:
    assert TERMINAL_RUN_STATUSES == frozenset({"completed", "failed", "cancelled"})


def test_append_assigns_host_owned_sequence() -> None:
    record: dict = {"id": "r1", "status": "queued"}
    append_run_event(record, "run_started", {"attempt": 1}, at_utc="2026-11-05T00:00:00+00:00")
    append_run_event(record, "run_finished", {"status": "completed"})
    assert [entry["seq"] for entry in record["events"]] == [1, 2]
    assert [entry["kind"] for entry in record["events"]] == ["run_started", "run_finished"]
    assert record["events"][0]["payload"] == {"attempt": 1}


def test_append_ignores_forged_sequence_gaps() -> None:
    record: dict = {"id": "r1", "events": [{"seq": 7, "kind": "old", "payload": {}}]}
    append_run_event(record, "run_started", {})
    assert record["events"][-1]["seq"] == 8


def test_append_survives_json_round_trip() -> None:
    record: dict = {"id": "r1", "status": "running"}
    append_run_event(record, "run_started", {"attempt": 1})
    revived = json.loads(json.dumps(record))
    assert run_events(revived) == record["events"]


def test_append_validates_inputs() -> None:
    with pytest.raises(TypeError):
        append_run_event([], "run_started", {})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="kind"):
        append_run_event({}, "  ")
    with pytest.raises(ValueError, match="kind"):
        append_run_event({}, "k" * 65)
    with pytest.raises(TypeError, match="payload"):
        append_run_event({}, "run_started", [])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="must be a list"):
        append_run_event({"events": {}}, "run_started", {})


def test_events_filter_after_sequence() -> None:
    record: dict = {"id": "r1"}
    for kind in ("a", "b", "c"):
        append_run_event(record, kind, {})
    assert [entry["kind"] for entry in run_events(record)] == ["a", "b", "c"]
    assert [entry["kind"] for entry in run_events(record, after=2)] == ["c"]
    assert run_events(record, after=3) == []
    assert run_events({"id": "empty"}) == []
    with pytest.raises(ValueError, match="after"):
        run_events(record, after=-1)


def test_request_cancel_flags_queued_and_paused() -> None:
    for status in ("queued", "paused"):
        record: dict = {"id": "r1", "status": status}
        assert run_cancelled(record) is False
        request_run_cancel(record, at_utc="2026-11-05T00:00:00+00:00")
        assert run_cancelled(record) is True
        assert record["status"] == status
        assert record["events"][-1]["kind"] == "cancellation_requested"


def test_request_cancel_refuses_terminal_and_running() -> None:
    for status in ("completed", "failed", "cancelled"):
        with pytest.raises(ValueError, match="terminal"):
            request_run_cancel({"id": "r1", "status": status})
    with pytest.raises(ValueError, match="executing"):
        request_run_cancel({"id": "r1", "status": "running"})


def test_cancel_guard_raises_only_when_flagged() -> None:
    ensure_run_not_cancelled({"id": "r1", "status": "queued"})
    with pytest.raises(ValueError, match="invalidated"):
        ensure_run_not_cancelled({"id": "r1", "status": "queued", "cancel_requested": True})
