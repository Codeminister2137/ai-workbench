"""Auto-ship completed drain runs: commit branches, schedule merges."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from dashboard_stores import DashboardStores
from drain_ship import ship_completed_run
from inbox_bridge import bridge_agent_queue


@pytest.fixture
def stores(tmp_path):
    return DashboardStores(tmp_path / "data")


def _git(worktree: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(worktree), *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


@pytest.fixture
def worktree(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "develop")
    _git(root, "config", "user.email", "test@local")
    _git(root, "config", "user.name", "test")
    (root / "note.txt").write_text("base\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "base")
    _git(root, "switch", "-c", "run/abc123")
    return root


def _run(worktree: Path, branch: str = "run/abc123") -> dict:
    return {
        "id": "abc123",
        "title": "Do the thing",
        "status": "completed",
        "receipts": [{"status": "completed", "worktree": str(worktree), "branch": branch}],
    }


def test_ship_commits_and_queues_integration_review(stores, worktree, tmp_path) -> None:
    (worktree / "note.txt").write_text("base\nrun edit\n", encoding="utf-8")
    shipment = ship_completed_run(_run(worktree), repo_root=tmp_path, stores=stores)
    assert shipment["committed"] is True
    assert shipment["action"] == "shipped"
    assert shipment["branch"] == "run/abc123"
    assert _git(worktree, "status", "--porcelain") == ""
    assert shipment["merge_item"]
    item = stores.inbox.get(shipment["merge_item"])
    assert item is not None
    assert item["type"] == "task"
    assert item["assignee"] == "agent"
    assert item["options"] == ["Done"]
    assert (item.get("metadata") or {}).get("merge_for_branch") == "run/abc123"


@pytest.mark.parametrize("path", ["note.txt", "auth.txt", "billing.txt", "migration.sql"])
def test_routine_and_sensitive_changes_require_review_before_integration(
    stores, worktree, tmp_path, path
):
    (worktree / path).write_text("change\n", encoding="utf-8")
    develop_before = _git(worktree, "rev-parse", "develop")
    shipment = ship_completed_run(_run(worktree), repo_root=tmp_path, stores=stores)
    item = stores.inbox.get(shipment["merge_item"])
    assert item["type"] == "task" and item["assignee"] == "agent"
    body = item["body"]
    assert "complete branch diff" in body
    assert "Wait for explicit approval" in body
    assert "Tier 1/2: no routine owner merge approval" in body
    assert "tests, lint, formatting and configured typecheck" in body
    assert "Never target master" in body
    assert "Owner per-behavior E2E" in body
    (receipt,) = bridge_agent_queue(stores)
    queued = stores.runs.get(receipt["run_id"])
    assert queued["approval_mode"] == "agent-queue"
    assert body.strip() in queued["body"]
    assert bridge_agent_queue(stores) == []
    assert _git(worktree, "rev-parse", "develop") == develop_before
    items, _ = stores.inbox.list(limit=100)
    assert not any(item["type"] == "decision" for item in items)


def test_ship_queue_failure_escalates_with_preserved_commit(
    stores, worktree, tmp_path, monkeypatch
):
    (worktree / "note.txt").write_text("change\n", encoding="utf-8")

    def fail(**kwargs):
        raise RuntimeError("inbox unavailable")

    monkeypatch.setattr(stores, "create_inbox_task", fail)
    with pytest.raises(RuntimeError, match="preserved; integration review not queued"):
        ship_completed_run(_run(worktree), repo_root=tmp_path, stores=stores)
    assert _git(worktree, "status", "--porcelain") == ""


def test_ship_names_current_branch_not_stale_receipt(stores, worktree, tmp_path) -> None:
    _git(worktree, "switch", "-c", "feature/worker-moved-on")
    (worktree / "note.txt").write_text("base\nrun edit\n", encoding="utf-8")
    shipment = ship_completed_run(_run(worktree), repo_root=tmp_path, stores=stores)
    assert shipment["branch"] == "feature/worker-moved-on"
    item = stores.inbox.get(shipment["merge_item"])
    assert item is not None
    assert (item.get("metadata") or {}).get("merge_for_branch") == "feature/worker-moved-on"
    assert "feature/worker-moved-on" in item["title"]


def test_ship_clean_tree_files_no_merge(stores, worktree, tmp_path) -> None:
    shipment = ship_completed_run(_run(worktree), repo_root=tmp_path, stores=stores)
    assert shipment == {
        "committed": True,
        "action": "clean",
        "branch": "run/abc123",
        "run_id": "abc123",
    }
    items, _total = stores.inbox.list(limit=100)
    assert items == []


def test_ship_without_worktree_is_noop(stores, tmp_path) -> None:
    run = {"id": "r1", "title": "t", "status": "completed", "receipts": [{"status": "done"}]}
    shipment = ship_completed_run(run, repo_root=tmp_path, stores=stores)
    assert shipment["committed"] is True
    assert shipment["action"] == "no-worktree"


def test_ship_missing_worktree_raises(stores, tmp_path) -> None:
    run = _run(tmp_path / "gone")
    with pytest.raises(RuntimeError, match="worktree gone"):
        ship_completed_run(run, repo_root=tmp_path, stores=stores)


def test_ship_ruff_failure_raises(stores, worktree, tmp_path) -> None:
    (worktree / "broken.py").write_text("import os\n\nprint( undefined )\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="ruff refused"):
        ship_completed_run(_run(worktree), repo_root=tmp_path, stores=stores)
    assert _git(worktree, "status", "--porcelain") != ""
