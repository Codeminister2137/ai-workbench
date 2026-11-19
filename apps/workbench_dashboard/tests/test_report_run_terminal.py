"""Failed-run triage filing on terminal report-back (real stores, no mocks)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

DASHBOARD_DIR = Path(__file__).resolve().parent.parent
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from dashboard_stores import MAX_OPEN_TASKS, DashboardStores  # noqa: E402
from dashboard_web_app import report_run_terminal  # noqa: E402


@pytest.fixture
def stores(tmp_path: Path) -> DashboardStores:
    return DashboardStores(tmp_path / "data")


def _source_and_run(stores: DashboardStores, run_id: str = "deadbeefcafe1234567890abcdef") -> str:
    source = stores.create_inbox_task(
        title="source task",
        body="do the thing",
        task_type="task",
        created_by="supervisor",
        assignee="agent",
    )
    stores.runs.put(
        run_id,
        {
            "id": run_id,
            "title": "mai run",
            "status": "failed",
            "bridged_from": source["id"],
            "project_id": source["project_id"],
            "error": "boom exploded",
            "receipts": [{"status": "failed", "failure_class": "provider"}],
        },
    )
    return source["id"]


def _triage_tasks(stores: DashboardStores, run_id: str) -> list[dict]:
    items, _total = stores.inbox.list(limit=1000)
    return [
        item
        for item in items
        if isinstance(item, dict)
        and isinstance(item.get("metadata"), dict)
        and item.get("metadata", {}).get("triage_for") == run_id
    ]


def test_failed_triage_run_files_no_meta_triage(stores: DashboardStores) -> None:
    run_id = "deadbeefcafe1234567890abcdef"
    source_id = _source_and_run(stores, run_id)
    source = stores.inbox.get(source_id)
    assert source is not None
    source["metadata"] = {**source.get("metadata", {}), "triage_for": "parent-run"}
    stores.inbox.put(source_id, source)
    result = report_run_terminal(stores, {"run_id": run_id, "status": "failed", "error": "boom"})
    assert result["action"] == "noted"
    assert _triage_tasks(stores, run_id) == []
    reopened = stores.inbox.get(source_id)
    assert reopened is not None
    assert reopened["status"] == "open"


def test_failed_files_triage_with_correct_fields(stores: DashboardStores) -> None:
    run_id = "deadbeefcafe1234567890abcdef"
    _source_and_run(stores, run_id)
    result = report_run_terminal(
        stores,
        {
            "run_id": run_id,
            "status": "failed",
            "error": "boom exploded",
            "failure_class": "provider",
        },
    )
    assert result["action"] == "noted"
    found = _triage_tasks(stores, run_id)
    assert len(found) == 1
    task = found[0]
    assert task["title"] == f"Triage failed run {run_id[:8]}"
    assert task["assignee"] == "agent"
    assert task["status"] == "open"
    assert task["context_refs"] == [f"run:{run_id}"]
    assert task["metadata"] == {"triage_for": run_id}
    assert "boom exploded" in task["body"]
    assert "provider" in task["body"]
    assert run_id in task["body"]
    assert "run report" in task["body"].lower()


@pytest.mark.parametrize("status", ["completed", "cancelled", "paused", "queued"])
def test_non_failed_statuses_stay_silent(stores: DashboardStores, status: str) -> None:
    run_id = "abc12345def67890abc12345def67890"
    _source_and_run(stores, run_id)
    report_run_terminal(stores, {"run_id": run_id, "status": status})
    assert _triage_tasks(stores, run_id) == []


def test_repeat_failed_call_files_only_once(stores: DashboardStores) -> None:
    run_id = "feedface00112233445566778899aabb"
    _source_and_run(stores, run_id)
    summary = {
        "run_id": run_id,
        "status": "failed",
        "error": "boom exploded",
        "failure_class": "provider",
    }
    report_run_terminal(stores, summary)
    report_run_terminal(stores, summary)
    assert len(_triage_tasks(stores, run_id)) == 1


def test_cap_refusal_sets_pending_without_raise(stores: DashboardStores) -> None:
    run_id = "caprefusal00112233445566778899ccdd"
    source_id = _source_and_run(stores, run_id)
    for n in range(MAX_OPEN_TASKS - 1):
        stores.create_inbox_task(
            title=f"filler {n}",
            body="filler",
            task_type="task",
            created_by="supervisor",
            assignee="agent",
        )
    result = report_run_terminal(
        stores,
        {
            "run_id": run_id,
            "status": "failed",
            "error": "boom exploded",
            "failure_class": "provider",
        },
    )
    assert result["action"] in ("noted", "skipped")
    assert _triage_tasks(stores, run_id) == []
    source = stores.inbox.get(source_id)
    assert source is not None
    assert source.get("triage_pending") is True
