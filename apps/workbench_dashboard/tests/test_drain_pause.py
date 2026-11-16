"""Drain pause gate: allowance/config failures pause the queue with one owner alert."""

from __future__ import annotations

from dashboard_stores import DashboardStores
from dashboard_web_app import drain_pause_state


def _run(run_id: str, status: str, stamp: str, failure_class: str = "") -> dict:
    record: dict = {"id": run_id, "title": run_id, "status": status, "finished_at_utc": stamp}
    if failure_class:
        record["receipts"] = [{"status": "failed", "failure_class": failure_class}]
        record["error"] = f"{failure_class} broke it"
    return record


def test_clean_queue_proceeds_without_alert(tmp_path) -> None:
    stores = DashboardStores(tmp_path)
    assert drain_pause_state(stores) is None
    inbox, _ = stores.inbox.list(limit=10)
    assert inbox == []


def test_allowance_failure_pauses_and_files_one_alert(tmp_path) -> None:
    stores = DashboardStores(tmp_path)
    stores.runs.put("r1", _run("r1", "failed", "2026-11-16T10:00:00+00:00", "allowance"))
    paused = drain_pause_state(stores)
    assert paused is not None and paused["paused"] is True
    assert "r1" in paused["reason"]
    inbox, _ = stores.inbox.list(limit=10)
    assert len(inbox) == 1
    assert inbox[0]["assignee"] == "owner"
    assert inbox[0]["metadata"]["kind"] == "drain-pause"
    again = drain_pause_state(stores)
    assert again is not None and again["alert_id"] == paused["alert_id"]
    inbox, _ = stores.inbox.list(limit=10)
    assert len(inbox) == 1  # deduped, never one per tick


def test_later_success_recovers_and_closes_alert(tmp_path) -> None:
    stores = DashboardStores(tmp_path)
    stores.runs.put("r1", _run("r1", "failed", "2026-11-16T10:00:00+00:00", "config"))
    assert drain_pause_state(stores) is not None
    stores.runs.put("r2", _run("r2", "completed", "2026-11-16T11:00:00+00:00"))
    assert drain_pause_state(stores) is None
    inbox, _ = stores.inbox.list(limit=10)
    assert inbox[0]["status"] == "closed"


def test_owner_close_acknowledges_until_next_failure(tmp_path) -> None:
    from datetime import UTC, datetime, timedelta

    stores = DashboardStores(tmp_path)
    stores.runs.put("r1", _run("r1", "failed", "2026-11-16T10:00:00+00:00", "allowance"))
    paused = drain_pause_state(stores)
    assert paused is not None
    stores.close_inbox_task(paused["alert_id"], resolution="grants refilled")
    assert drain_pause_state(stores) is None  # acknowledged: resume
    later = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    stores.runs.put("r2", _run("r2", "failed", later, "allowance"))
    resumed_pause = drain_pause_state(stores)
    assert resumed_pause is not None  # later failure re-files
    assert resumed_pause["alert_id"] != paused["alert_id"]


def test_other_failures_do_not_pause(tmp_path) -> None:
    stores = DashboardStores(tmp_path)
    stores.runs.put("r1", _run("r1", "failed", "2026-11-16T10:00:00+00:00", "provider"))
    assert drain_pause_state(stores) is None
    inbox, _ = stores.inbox.list(limit=10)
    assert inbox == []
