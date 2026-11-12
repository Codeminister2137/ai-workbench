"""Per-run scratch worktrees isolate agent edits from shared checkouts."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from run_isolation import IsolationError, create_run_worktree


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def _repo(tmp_path: Path, *, config: bool = True) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "develop")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "code.py").write_text("v = 1\n", encoding="utf-8")
    if config:
        (repo / "user-config.toml").write_text("[x]\n", encoding="utf-8")
    (repo / ".env").write_text("SECRET=1\n", encoding="utf-8")
    _git(repo, "add", "code.py", "user-config.toml" if config else "code.py")
    _git(repo, "commit", "-m", "base")
    return repo


def test_worktree_branches_from_develop_and_copies_config(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    iso = create_run_worktree(repo, "abc123")
    assert iso.branch == "run/abc123"
    assert iso.path == repo / ".tmp" / "run-worktrees" / "abc123"
    assert (iso.path / "code.py").read_text(encoding="utf-8") == "v = 1\n"
    assert (iso.path / "user-config.toml").read_text(encoding="utf-8") == "[x]\n"
    assert not (iso.path / ".env").exists()
    assert _git(repo, "branch", "--show-current") == "develop"
    branches = _git(repo, "branch", "--list", "run/abc123")
    assert "run/abc123" in branches
    head = _git(repo, "rev-parse", "develop")
    assert _git(iso.path, "rev-parse", "HEAD") == head


def test_scratch_edits_do_not_touch_main_checkout(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    iso = create_run_worktree(repo, "abc123")
    (iso.path / "code.py").write_text("v = 2\n", encoding="utf-8")
    assert (repo / "code.py").read_text(encoding="utf-8") == "v = 1\n"


def test_non_git_root_fails_closed(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(IsolationError, match="not a git checkout"):
        create_run_worktree(plain, "abc123")


def test_missing_config_fails_closed_without_leftovers(tmp_path: Path) -> None:
    repo = _repo(tmp_path, config=False)
    with pytest.raises(IsolationError, match="user-config.toml missing"):
        create_run_worktree(repo, "abc123")
    assert not (repo / ".tmp" / "run-worktrees" / "abc123").exists()
    assert _git(repo, "branch", "--list", "run/abc123") == ""


def test_duplicate_run_id_fails_closed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    create_run_worktree(repo, "abc123")
    with pytest.raises(IsolationError, match="already exists"):
        create_run_worktree(repo, "abc123")


def test_executor_runs_isolated_with_receipt_links(tmp_path: Path) -> None:
    from mai_run import MaiRunOutcome, build_mai_executor

    repo = _repo(tmp_path)
    seen: dict = {}

    def fake_session(argv, runner=None):
        seen["argv"] = list(argv)
        return MaiRunOutcome(exit_code=0, stdout_tail="done", stderr_tail="")

    import mai_run

    real = mai_run.run_mai_session
    try:
        mai_run.run_mai_session = fake_session
        receipt = build_mai_executor(
            repo, repo / "user-config.toml", backend="in-process", isolate=True
        )({"id": "abc123", "title": "T", "body": "B"})
    finally:
        mai_run.run_mai_session = real
    assert receipt["status"] == "completed"
    assert receipt["branch"] == "run/abc123"
    assert receipt["worktree"].endswith("abc123")
    assert seen["argv"][0].startswith("Run abc123")
    assert "--repo-root" in seen["argv"]
    root = seen["argv"][seen["argv"].index("--repo-root") + 1]
    assert root != str(repo)
    assert root == receipt["worktree"]


def test_executor_isolation_failure_fails_run_without_fallback(tmp_path: Path) -> None:
    from mai_run import build_mai_executor

    plain = tmp_path / "plain"
    plain.mkdir()
    receipt = build_mai_executor(
        plain, plain / "user-config.toml", backend="in-process", isolate=True
    )({"id": "abc123", "title": "T", "body": "B"})
    assert receipt["status"] == "failed"
    assert "isolation failed" in receipt["error"]
    assert "worktree" not in receipt
