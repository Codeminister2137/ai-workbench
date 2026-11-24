"""Failed-run triage filing on terminal report-back (real stores, no mocks)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

DASHBOARD_DIR = Path(__file__).resolve().parent.parent
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from dashboard_stores import MAX_OPEN_TASKS, DashboardStores  # noqa: E402
from dashboard_web_app import report_run_terminal  # noqa: E402
from run_forensics import render_forensics_block, summarize_failed_run  # noqa: E402


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


def _repo_layout(tmp_path: Path) -> tuple[Path, DashboardStores]:
    """Fake <repo>/apps/workbench_dashboard/data layout for forensics tests."""
    repo = tmp_path / "repo"
    data_dir = repo / "apps" / "workbench_dashboard" / "data"
    data_dir.mkdir(parents=True)
    return repo, DashboardStores(data_dir)


def _seed_receipts(worktree: Path, operations: list[str]) -> None:
    db_dir = worktree / "data"
    db_dir.mkdir(parents=True)
    connection = sqlite3.connect(db_dir / "repo-assistant-chats.sqlite3")
    try:
        connection.execute(
            "CREATE TABLE coding_receipts "
            "(receipt_id TEXT, session_id TEXT, operation TEXT, status TEXT, "
            "output_sha256 TEXT, created_at_utc TEXT, completed_at_utc TEXT)"
        )
        connection.executemany(
            "INSERT INTO coding_receipts VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (f"r{n}", "s1", op, "ok", "0" * 64, "2026-11-24T10:00:00Z", None)
                for n, op in enumerate(operations)
            ],
        )
        connection.commit()
    finally:
        connection.close()


def test_triage_body_carries_forensics_block(tmp_path: Path) -> None:
    """Starvation evidence rides inline; triage needs no recon spin."""
    repo, repo_stores = _repo_layout(tmp_path)
    run_id = "starved000112233445566778899aabb"
    worktree = repo / ".tmp" / "run-worktrees" / run_id[:12]
    worktree.mkdir(parents=True)
    _seed_receipts(worktree, ["read_file"] * 13 + ["grep_search"] * 8 + ["run_command"] * 3)
    _source_and_run(repo_stores, run_id)
    report_run_terminal(
        repo_stores,
        {
            "run_id": run_id,
            "status": "failed",
            "error": "Agent loop exceeded max_iterations=25",
            "failure_class": "provider",
        },
    )
    found = _triage_tasks(repo_stores, run_id)
    assert len(found) == 1
    body = found[0]["body"]
    assert "Forensics (collected at report time; do not re-gather)" in body
    assert "read_file x13" in body
    assert "grep_search x8" in body
    assert "run_command x3" in body
    assert "24 tool receipts" in body
    assert run_id[:12] in body  # worktree path pointer


def test_forensics_missing_worktree_is_fail_soft(tmp_path: Path) -> None:
    """Pruned worktree still files triage, with an honest note."""
    repo, repo_stores = _repo_layout(tmp_path)
    run_id = "pruned0000112233445566778899001122"
    _source_and_run(repo_stores, run_id)
    report_run_terminal(repo_stores, {"run_id": run_id, "status": "failed", "error": "boom"})
    found = _triage_tasks(repo_stores, run_id)
    assert len(found) == 1
    assert "pruned or never created" in found[0]["body"]
    summary = summarize_failed_run(repo, run_id)
    assert summary["git_status"] is None
    assert summary["op_profile"] == {}


def test_forensics_survives_garbage_database(tmp_path: Path) -> None:
    """Corrupt session DB degrades to notes, never raises."""
    repo = tmp_path / "repo"
    run_id = "garbage00011223344556677889900112"
    worktree = repo / ".tmp" / "run-worktrees" / run_id[:12]
    (worktree / "data").mkdir(parents=True)
    (worktree / "data" / "repo-assistant-chats.sqlite3").write_bytes(b"not a database")
    summary = summarize_failed_run(repo, run_id)
    assert summary["receipts_total"] == 0
    assert summary["notes"], "expected degradation notes"
    block = render_forensics_block(summary)
    assert "Iteration profile: unavailable" in block
    assert "unknown (git status failed" in block


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
