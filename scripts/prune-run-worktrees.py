#!/usr/bin/env python3
"""Prune retained per-run scratch worktrees (manual, explicit only).

Lists (default dry-run) or removes (`--apply`) `.tmp/run-worktrees/<id>/`
checkouts whose runs finished (completed/failed/cancelled) and are older
than `--older-than` days. Never touches queued/running/paused runs,
non-run branches, or the main checkout. Branch `run/<id>` goes with its
worktree; review before pruning.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
ACTIVE_STATUSES = frozenset({"queued", "running", "paused"})


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _run_age_days(record: dict, worktree: Path, now: float) -> float | None:
    updated = record.get("updated_at_utc")
    if isinstance(updated, str):
        try:
            stamp = datetime.fromisoformat(updated.replace("Z", "+00:00")).timestamp()
            return max(0.0, (now - stamp) / 86400)
        except ValueError:
            pass
    try:
        return max(0.0, (now - worktree.stat().st_mtime) / 86400)
    except OSError:
        return None


def collect_candidates(
    repo_root: Path, runs_dir: Path, *, older_than_days: float, now: float | None = None
) -> tuple[list[dict], list[str]]:
    """Return (prunable, skipped-reasons) without changing anything."""
    now = time.time() if now is None else now
    prunable: list[dict] = []
    skipped: list[str] = []
    worktrees = repo_root / ".tmp" / "run-worktrees"
    if not worktrees.is_dir():
        return prunable, skipped
    records: dict[str, dict] = {}
    if runs_dir.is_dir():
        for path in runs_dir.glob("*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(record, dict) and record.get("id"):
                records[str(record["id"])] = record
    for target in sorted(worktrees.iterdir()):
        if not target.is_dir():
            continue
        short = target.name
        matches = [rid for rid in records if rid.startswith(short) or short.startswith(rid[:12])]
        if not matches:
            skipped.append(f"{short}: no run record found")
            continue
        record = records[matches[0]]
        status = record.get("status")
        if status in ACTIVE_STATUSES:
            skipped.append(f"{short}: run {status}")
            continue
        if status not in TERMINAL_STATUSES:
            skipped.append(f"{short}: unexpected run status {status!r}")
            continue
        age = _run_age_days(record, target, now)
        if age is None or age < older_than_days:
            skipped.append(f"{short}: too fresh")
            continue
        prunable.append(
            {"id": short, "branch": f"run/{short}", "path": str(target), "status": status}
        )
    return prunable, skipped


def prune(repo_root: Path, candidate: dict) -> None:
    """Remove one worktree and its run/* branch (caller verified eligibility)."""
    branch = candidate["branch"]
    if not branch.startswith("run/"):
        raise RuntimeError(f"refusing non-run branch: {branch}")
    _git(repo_root, "worktree", "remove", "--force", candidate["path"])
    _git(repo_root, "branch", "-D", branch)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prune finished run worktrees.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--runs-dir", type=Path, default=None)
    parser.add_argument("--older-than", type=float, default=7.0)
    parser.add_argument("--apply", action="store_true", help="Remove (default dry-run).")
    args = parser.parse_args(argv)
    repo = args.repo_root.resolve()
    runs_dir = args.runs_dir or repo / "apps" / "workbench_dashboard" / "data" / "runs"
    prunable, skipped = collect_candidates(repo, runs_dir, older_than_days=args.older_than)
    for entry in prunable:
        print(
            f"{'REMOVE' if args.apply else 'would remove'}: {entry['path']} ({entry['branch']}, {entry['status']})"
        )
    for reason in skipped:
        print(f"skip: {reason}")
    if not args.apply:
        print(f"{len(prunable)} candidate(s), 0 removed (dry run; pass --apply)")
        return 0
    for entry in prunable:
        prune(repo, entry)
    print(f"removed {len(prunable)} worktree(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
