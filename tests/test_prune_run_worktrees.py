"""Tests for scripts/prune-run-worktrees.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prune-run-worktrees.py"


def _load():
    spec = importlib.util.spec_from_file_location("prune_run_worktrees", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True)
    subprocess.run(["git", "branch", "-M", "develop"], cwd=tmp_path, check=True)
    for ident, age_days, status in (
        ("old-done", 9, "completed"),
        ("old-failed", 9, "failed"),
        ("old-run", 9, "running"),
        ("fresh", 1, "completed"),
    ):
        subprocess.run(
            ["git", "worktree", "add", f".tmp/run-worktrees/{ident}", "-b", f"run/{ident}"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        stamp = (datetime.now(UTC) - timedelta(days=age_days)).isoformat()
        runs = tmp_path / "runs"
        runs.mkdir(exist_ok=True)
        (runs / f"{ident}.json").write_text(
            json.dumps({"id": ident, "status": status, "updated_at_utc": stamp}),
            encoding="utf-8",
        )
    (tmp_path / ".tmp" / "run-worktrees" / "orphan").mkdir(parents=True)
    return tmp_path


def test_collect_keeps_active_fresh_and_orphans(repo: Path) -> None:
    mod = _load()
    prunable, skipped = mod.collect_candidates(repo, repo / "runs", older_than_days=7.0)
    assert {entry["id"] for entry in prunable} == {"old-done", "old-failed"}
    joined = "\n".join(skipped)
    assert "old-run" in joined and "fresh" in joined and "orphan" in joined


def test_prune_removes_worktree_and_branch(repo: Path) -> None:
    mod = _load()
    prunable, _ = mod.collect_candidates(repo, repo / "runs", older_than_days=7.0)
    entry = next(item for item in prunable if item["id"] == "old-done")
    mod.prune(repo, entry)
    assert not (repo / ".tmp" / "run-worktrees" / "old-done").exists()
    branches = subprocess.run(
        ["git", "branch", "--list", "run/old-done"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "run/old-done" not in branches
    with pytest.raises(RuntimeError, match="refusing"):
        mod.prune(repo, {"branch": "develop", "path": str(repo)})
