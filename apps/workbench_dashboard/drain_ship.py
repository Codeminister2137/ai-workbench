"""Auto-ship completed drain runs: commit the run branch, schedule the merge.

Owner policy (2026-11-20): a completed run must never leave its work
uncommitted. The drain calls :func:`ship_completed_run` for every
completed run; failures escalate the run to needs-attention instead of
reading completed.

What this does, in order: commit the run worktree on its own branch
(run branches are never shared, so no approval is needed), then file a
merge DECISION for the owner (merges touch shared develop plus serve,
so they keep human approval). The merge close-out run does the
merge, gated push, redeploy, and end-to-end smoke. Nothing here pushes,
merges, or redeploys by itself.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

MERGE_DECISION_TYPE = "decision"
MERGE_OPTIONS = ("Merge now", "Hold")


def _run_git(worktree: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(worktree), *args],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _receipt_worktree(run: dict) -> tuple[Path | None, str | None]:
    receipts = run.get("receipts")
    if isinstance(receipts, list):
        for entry in reversed(receipts):
            if not isinstance(entry, dict):
                continue
            worktree = entry.get("worktree")
            branch = entry.get("branch")
            if worktree and branch:
                return Path(str(worktree)), str(branch)
    return None, None


def _ruff_ok(worktree: Path, changed_py: list[str]) -> tuple[bool, str]:
    if not changed_py:
        return True, "no python changes"
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", *changed_py],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(worktree),
        check=False,
    )
    if proc.returncode != 0:
        return False, (proc.stdout + proc.stderr)[-500:]
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--check", *changed_py],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(worktree),
        check=False,
    )
    if proc.returncode != 0:
        return False, "ruff format --check failed: run ruff format on: " + ", ".join(changed_py)
    return True, "ruff clean"


def ship_completed_run(run: dict, *, repo_root: Path, stores: Any) -> dict[str, Any]:
    """Commit a completed run's worktree and file its merge decision.

    Returns a shipment record with ``committed`` (bool), ``commit``,
    ``branch``, ``merge_item`` (or None), and ``action`` notes. Raises
    on git/ruff failures so the drain escalates instead of shipping
    half-done work.
    """
    run_id = str(run.get("id", "?"))
    worktree, branch = _receipt_worktree(run)
    if worktree is None or branch is None:
        return {"committed": True, "action": "no-worktree", "run_id": run_id}
    if not worktree.is_dir():
        raise RuntimeError(f"run worktree gone: {worktree}")
    status = _run_git(worktree, "status", "--porcelain")
    if status.returncode != 0:
        raise RuntimeError(f"git status failed: {status.stderr.strip()[:200]}")
    if not status.stdout.strip():
        return {
            "committed": True,
            "action": "clean",
            "branch": branch,
            "run_id": run_id,
        }
    _run_git(worktree, "add", "-A")
    staged = _run_git(worktree, "diff", "--cached", "--name-only")
    changed_py = [
        line.strip() for line in staged.stdout.splitlines() if line.strip().endswith(".py")
    ]
    ok, detail = _ruff_ok(worktree, changed_py)
    if not ok:
        raise RuntimeError(f"ruff refused auto-commit: {detail}")
    title = str(run.get("title") or run_id)
    # --no-verify: repo hooks resolve .venv relative to cwd, which does
    # not exist inside linked worktrees; ruff already ran above.
    commit = _run_git(worktree, "commit", "--no-verify", "-m", f"{title} (drain run {run_id})")
    if commit.returncode != 0:
        raise RuntimeError(f"git commit failed: {(commit.stdout + commit.stderr).strip()[:300]}")
    rev = _run_git(worktree, "rev-parse", "--short", "HEAD")
    commit_hash = rev.stdout.strip() if rev.returncode == 0 else "?"
    diffstat = _run_git(worktree, "show", "--stat", "--oneline", "HEAD")
    stat_line = ""
    if diffstat.returncode == 0:
        lines = diffstat.stdout.strip().splitlines()
        stat_line = lines[-1].strip() if lines else ""
    merge_item = None
    merge_error = None
    try:
        item = stores.create_inbox_task(
            title=f"Merge run branch {branch}?",
            body=(
                f"Drain run {run_id} ({title}) committed {commit_hash} on {branch} "
                f"({stat_line}). Merge into develop, push through the gate, redeploy "
                "on green, then health-check and smoke the feature end to end."
            ),
            task_type=MERGE_DECISION_TYPE,
            options=list(MERGE_OPTIONS),
            created_by="supervisor",
            assignee="owner",
            project_id=str(stores.default_project_id()),
            metadata={
                "merge_for_branch": branch,
                "merge_for_run": run_id,
                "followup": {
                    "owner": "Pick Merge now or Hold.",
                    "ai": (
                        "On Merge now: merge, gated push, redeploy, "
                        "health-check, smoke, report. On Hold: leave "
                        "the branch; release on request."
                    ),
                },
            },
            context_refs=[f"run:{run_id}"],
        )
        merge_item = item.get("id")
    except Exception as exc:  # noqa: BLE001 - commit preserved; merge retries later
        merge_error = f"{type(exc).__name__}: {exc}"
    return {
        "committed": True,
        "action": "shipped",
        "branch": branch,
        "commit": commit_hash,
        "merge_item": merge_item,
        "merge_error": merge_error,
        "run_id": run_id,
    }
