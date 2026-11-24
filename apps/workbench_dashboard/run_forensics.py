"""Best-effort forensics for failed drain runs (starvation triage aid).

A starved Mai session leaves its evidence in its scratch worktree:
``.tmp/run-worktrees/<id8>/`` — the git status (what, if anything, it
produced) and the coding-receipt operation profile (where its iterations
went). Triage tasks used to re-discover all of this with shell recon;
several burned their full 25-iteration budget doing so. This module
gathers that evidence once, at report time, so the triage body carries
it inline.

Every public helper is fail-soft: missing worktrees, absent databases,
and git failures come back as notes, never exceptions.
"""

from __future__ import annotations

import sqlite3
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

WORKTREE_DIRNAME = ".tmp/run-worktrees"
SESSION_DB = Path("data") / "repo-assistant-chats.sqlite3"
MAX_STATUS_LINES = 20
GIT_TIMEOUT_SECONDS = 15


def worktree_for(repo_root: Path, run_id: str) -> Path:
    """Scratch worktree path for a run (may not exist).

    Mirrors run_isolation.create_run_worktree's short-id rule (alnum,
    12 chars); that function is the authority if they ever disagree.
    """
    short = "".join(ch for ch in str(run_id) if ch.isalnum())[:12]
    return Path(repo_root) / WORKTREE_DIRNAME / short


def _git_status_lines(worktree: Path) -> tuple[list[str], bool, str | None]:
    """Porcelain status lines; returns (lines, truncated, note)."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(worktree), "status", "--short"],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, ValueError) as exc:
        return [], False, f"git status unavailable: {exc}"
    except subprocess.TimeoutExpired:
        return [], False, "git status timed out"
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        reason = detail[0][:120] if detail else f"exit {proc.returncode}"
        return [], False, f"git status failed: {reason}"
    lines = [line for line in (proc.stdout or "").splitlines() if line.strip()]
    if len(lines) > MAX_STATUS_LINES:
        return lines[:MAX_STATUS_LINES], True, None
    return lines, False, None


def _op_profile(worktree: Path) -> tuple[dict[str, int], int, str | None]:
    """Tool-operation counts from the worktree coding receipts."""
    db_path = worktree / SESSION_DB
    if not db_path.is_file():
        return {}, 0, "no session database in worktree"
    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error as exc:
        return {}, 0, f"session database unreadable: {exc}"
    try:
        tables = {
            row[0]
            for row in connection.execute("select name from sqlite_master where type='table'")
        }
        if "coding_receipts" not in tables:
            return {}, 0, "session database has no coding receipts"
        counts: Counter[str] = Counter()
        total = 0
        for (operation,) in connection.execute("select operation from coding_receipts"):
            counts[str(operation)] += 1
            total += 1
        return dict(sorted(counts.items())), total, None
    except sqlite3.Error as exc:
        return {}, 0, f"receipt query failed: {exc}"
    finally:
        connection.close()


def summarize_failed_run(repo_root: Path, run_id: str) -> dict[str, Any]:
    """Gather worktree + iteration evidence for a failed run; never raises."""
    notes: list[str] = []
    try:
        worktree = worktree_for(repo_root, run_id)
    except Exception as exc:  # noqa: BLE001 - forensics never breaks reporting
        return {
            "worktree": None,
            "git_status": None,
            "git_truncated": False,
            "op_profile": {},
            "receipts_total": 0,
            "notes": [f"worktree path unresolvable: {exc}"],
        }
    if not worktree.is_dir():
        return {
            "worktree": worktree.as_posix(),
            "git_status": None,
            "git_truncated": False,
            "op_profile": {},
            "receipts_total": 0,
            "notes": ["worktree already pruned or never created"],
        }
    try:
        status_lines, truncated, git_note = _git_status_lines(worktree)
    except Exception as exc:  # noqa: BLE001 - belt and suspenders
        status_lines, truncated, git_note = [], False, f"git status error: {exc}"
    if git_note:
        notes.append(git_note)
    try:
        profile, total, op_note = _op_profile(worktree)
    except Exception as exc:  # noqa: BLE001 - belt and suspenders
        profile, total, op_note = {}, 0, f"profile error: {exc}"
    if op_note:
        notes.append(op_note)
    return {
        "worktree": worktree.as_posix(),
        # None = git failed (unknown); [] = clean tree. Never conflate them.
        "git_status": None if git_note else status_lines,
        "git_truncated": truncated,
        "op_profile": profile,
        "receipts_total": total,
        "notes": notes,
    }


def render_forensics_block(summary: dict[str, Any]) -> str:
    """Render the summary as triage-body markdown (no recon needed)."""
    lines = ["Forensics (collected at report time; do not re-gather):"]
    worktree = summary.get("worktree")
    lines.append(f"- Worktree: {worktree if worktree else '(unknown)'}")
    status = summary.get("git_status")
    if status is None:
        lines.append("- Produced in worktree: unknown (git status failed; see notes)")
    elif status:
        lines.append("- Produced in worktree (git status):")
        lines.extend(f"  - {entry}" for entry in status)
        if summary.get("git_truncated"):
            lines.append(f"  - ... truncated to {MAX_STATUS_LINES} lines")
    else:
        lines.append("- Produced in worktree: nothing (clean tree)")
    profile = summary.get("op_profile") or {}
    total = summary.get("receipts_total") or 0
    if profile:
        ranked = ", ".join(
            f"{op} x{count}"
            for op, count in sorted(profile.items(), key=lambda kv: (-kv[1], kv[0]))
        )
        lines.append(f"- Iteration profile ({total} tool receipts): {ranked}")
    else:
        lines.append("- Iteration profile: unavailable")
    for note in summary.get("notes") or []:
        lines.append(f"- Note: {note}")
    return "\n".join(lines)
