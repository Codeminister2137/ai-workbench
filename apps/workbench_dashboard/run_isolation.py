"""Per-run scratch worktrees: agent edits never touch shared checkouts.

Each isolated run gets ``run/<id8>`` branched from the integration branch
(``develop``) in ``.tmp/run-worktrees/<id8>/``. ``user-config.toml`` is
copied in (Mai requires it); ``.env`` is never copied (secrets stay out of
scratch; Mai inherits the parent environment). Worktrees are retained after
the run for owner review and manual pruning — never auto-merged or deleted.
Fail-closed: anything unexpected raises instead of silently running elsewhere.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ISOLATION_BASE_BRANCH = "develop"
WORKTREE_DIRNAME = ".tmp/run-worktrees"
CONFIG_FILENAME = "user-config.toml"


class IsolationError(RuntimeError):
    """Scratch worktree setup failed; the run must not execute elsewhere."""


@dataclass(slots=True, frozen=True)
class IsolatedRun:
    """Scratch checkout for one run; retained for review."""

    path: Path
    branch: str


def _git(repo: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except OSError as exc:
        raise IsolationError(f"git unavailable: {exc}") from exc
    if proc.returncode != 0:
        raise IsolationError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def create_run_worktree(
    repo_root: Path | str,
    run_id: str,
    *,
    base_branch: str = ISOLATION_BASE_BRANCH,
) -> IsolatedRun:
    """Create the scratch worktree + branch for one run (fail-closed)."""
    repo = Path(repo_root).resolve()
    if not (repo / ".git").exists():
        raise IsolationError(f"not a git checkout: {repo}")
    short = "".join(ch for ch in str(run_id) if ch.isalnum())[:12]
    if not short:
        raise IsolationError("run id has no usable characters")
    branch = f"run/{short}"
    target = repo / WORKTREE_DIRNAME / short
    if target.exists():
        raise IsolationError(f"scratch worktree already exists: {target}")
    existing = _git(repo, "branch", "--list", branch)
    if existing:
        raise IsolationError(f"scratch branch already exists: {branch}")
    target.parent.mkdir(parents=True, exist_ok=True)
    _git(repo, "worktree", "add", "-b", branch, str(target), base_branch)
    config_src = repo / CONFIG_FILENAME
    if not config_src.is_file():
        for args in (("worktree", "remove", "--force", str(target)), ("branch", "-D", branch)):
            try:
                _git(repo, *args)
            except IsolationError:
                pass
        raise IsolationError(f"{CONFIG_FILENAME} missing in {repo}; cannot isolate run")
    shutil.copy2(config_src, target / CONFIG_FILENAME)
    return IsolatedRun(path=target, branch=branch)
