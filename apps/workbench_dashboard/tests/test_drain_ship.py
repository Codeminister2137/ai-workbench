"""Auto-ship completed drain runs: commit branches, schedule merges."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from dashboard_stores import DashboardStores
from drain_ship import ship_completed_run


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


def test_ship_commits_and_files_merge_decision(stores, worktree, tmp_path) -> None:
    (worktree / "note.txt").write_text("base\nrun edit\n", encoding="utf-8")
    shipment = ship_completed_run(_run(worktree), repo_root=tmp_path, stores=stores)
    assert shipment["committed"] is True
    assert shipment["action"] == "shipped"
    assert shipment["branch"] == "run/abc123"
    assert _git(worktree, "status", "--porcelain") == ""
    assert shipment["merge_item"]
    item = stores.inbox.get(shipment["merge_item"])
    assert item is not None
    assert item["type"] == "decision"
    assert item["options"] == ["Merge now", "Hold"]
    assert (item.get("metadata") or {}).get("merge_for_branch") == "run/abc123"


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
