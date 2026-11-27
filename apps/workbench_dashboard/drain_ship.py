"""Auto-ship completed drain runs: commit the run branch, schedule the merge.

Owner policy (2026-11-20): a completed run must never leave its work
uncommitted. The drain calls :func:`ship_completed_run` for every
completed run; failures escalate the run to needs-attention instead of
reading completed.

Commit on the run branch, then queue an agent integration review under
ADR-087. Scheduling review is not merge authorization: the reviewer must
classify the complete branch diff, preserve Tier 3 owner approval, and
integrate Tier 1/2 only after green gates. Nothing here merges or pushes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

INTEGRATION_REVIEW = """Read docs/decisions/ADR-087-tiered-merge-gates-e2e-promotion.md.
Review the complete branch diff against current develop (not just the last
commit or run summary), including existing committed work. Record the reviewed
commit, tier, rationale and scoped agent review findings; never merge unreviewed
work. Re-review if the branch changes. Do not infer tier from file count or a
completed run status.
Tier 3: auth, secrets, credentials, money/billing, data deletion/migration,
architecture changes, external data routing. Before merging any Tier 3 change,
file an owner-assigned decision with the concrete diff, risks, options and
recommendation, linked to this run and branch. Wait for explicit approval of
that reviewed scope. If classification or approved feature-plan scope is
unclear, stop and surface a clarification in the inbox; do not assume Tier 1/2.
Tier 1/2: no routine owner merge approval. Integrate into develop only after
scoped agent review, tests, lint, formatting and configured typecheck are green.
Red/missing gates or unresolved review findings block integration; record the
blocker rather than asking the owner to rubber-stamp it. Preserve existing
push gates, redeploy on green, then health-check and smoke the behavior.
Never target master. Owner per-behavior E2E and explicit develop-to-master
promotion remain required; surface those actions on their existing dashboard
surfaces. Record tier, review, gate evidence and integration result on this
item (no separate merge report).
"""


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
    """Commit a completed run's worktree and queue its integration review.

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
    current = _run_git(worktree, "branch", "--show-current")
    current_branch = current.stdout.strip() if current.returncode == 0 else ""
    if current_branch and current_branch != "HEAD":
        # Workers routinely move to feature branches mid-run; the merge
        # item must name the branch holding the commit, not the stale
        # run/* ref from the receipt.
        branch = current_branch
    diffstat = _run_git(worktree, "show", "--stat", "--oneline", "HEAD")
    stat_line = ""
    if diffstat.returncode == 0:
        lines = diffstat.stdout.strip().splitlines()
        stat_line = lines[-1].strip() if lines else ""
    merge_item = None
    merge_error = None
    try:
        item = stores.create_inbox_task(
            title=f"Review and integrate run branch {branch}",
            body=(
                f"Drain run {run_id} ({title}) committed {commit_hash} on {branch} "
                f"({stat_line}).\n\n{INTEGRATION_REVIEW}"
            ),
            task_type="task",
            created_by="supervisor",
            assignee="agent",
            project_id=str(stores.default_project_id()),
            metadata={
                "author_source": "rule",
                "merge_for_branch": branch,
                "merge_for_run": run_id,
            },
            context_refs=[f"run:{run_id}"],
        )
        merge_item = item.get("id")
    except Exception as exc:  # noqa: BLE001 - commit preserved; merge retries later
        merge_error = f"{type(exc).__name__}: {exc}"
    if merge_error:
        raise RuntimeError(
            f"commit {commit_hash} preserved; integration review not queued: {merge_error}"
        )
    return {
        "committed": True,
        "action": "shipped",
        "branch": branch,
        "commit": commit_hash,
        "merge_item": merge_item,
        "merge_error": merge_error,
        "run_id": run_id,
    }
