"""Prune old per-run scratch worktrees (owner answer A on inbox 8d79ac88).

Policy: worktree checkouts under ``.tmp/run-worktrees/<id12>/`` are removed
once their run has been terminal for at least ``--days`` (default 30).
Run JSON records and ``run-progress/*.jsonl`` transcripts are NEVER touched:
text evidence is the durable archive; only the GB-heavy file state goes.

Safety rails:
- dry-run by default; deletion only with ``--apply``;
- only registered worktrees are removed (``git worktree remove --force``);
  unregistered leftovers are reported as strays, never deleted;
- the main checkout is never a removal target;
- locked worktrees are skipped;
- nested worktrees are removed deepest-first;
- orphan checkouts (no run record) are reported, never deleted.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "merged", "closed"})
WORKTREE_DIRNAME = ".tmp/run-worktrees"
RUNS_DIRNAME = "runs"
TRANSCRIPTS_DIRNAME = "run-progress"


class PrunerError(RuntimeError):
    """Pruner cannot proceed safely."""


def _run_git(repo: Path, *args: str) -> str:
    try:
        proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=120)
    except OSError as exc:
        raise PrunerError(f"git unavailable: {exc}") from exc
    if proc.returncode != 0:
        raise PrunerError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _short_id(run_id: str) -> str:
    return "".join(ch for ch in run_id if ch.isalnum())[:12]


def _dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda _e: None):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


@dataclass(slots=True)
class WorktreeInventory:
    """Registered worktrees from ``git worktree list --porcelain``."""

    main: Path | None
    registered: set[Path] = field(default_factory=set)
    locked: set[Path] = field(default_factory=set)


def list_worktrees(repo: Path, runner: Callable[..., str] | None = None) -> WorktreeInventory:
    """Parse registered worktrees; paths resolved for reliable comparison."""
    run = runner or _run_git
    raw = run(repo, "worktree", "list", "--porcelain")
    inventory = WorktreeInventory(main=None)
    current: Path | None = None
    for line in raw.splitlines():
        if line.startswith("worktree "):
            try:
                current = Path(line[len("worktree ") :].strip()).resolve()
            except OSError:
                current = None
            if inventory.main is None and current is not None:
                inventory.main = current
            if current is not None:
                inventory.registered.add(current)
        elif line.startswith("locked") and current is not None:
            inventory.locked.add(current)
    return inventory


@dataclass(slots=True)
class Candidate:
    """One checkout eligible for removal."""

    run_id: str
    status: str
    terminal_at: str
    path: Path
    size_bytes: int


@dataclass(slots=True)
class CollectionResult:
    """Selection outcome plus every skipped/edge item with its reason."""

    candidates: list[Candidate] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)


def collect_candidates(
    repo: Path,
    data_dir: Path,
    days: int,
    now: datetime,
    runner: Callable[..., str] | None = None,
) -> CollectionResult:
    """Select registered checkouts of runs terminal for at least ``days``."""
    if days < 0:
        raise PrunerError("--days must be non-negative")
    repo = repo.resolve()
    cutoff = now.astimezone(UTC) - timedelta(days=days)
    inventory = list_worktrees(repo, runner)
    base = repo / WORKTREE_DIRNAME
    result = CollectionResult()
    seen_shorts: set[str] = set()
    runs_dir = data_dir / RUNS_DIRNAME
    if not runs_dir.is_dir():
        raise PrunerError(f"run store missing: {runs_dir}")
    for record_path in sorted(runs_dir.glob("*.json")):
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError, OSError):
            result.skipped.append({"run": record_path.stem, "reason": "unreadable record"})
            continue
        if not isinstance(record, dict):
            result.skipped.append({"run": record_path.stem, "reason": "record not an object"})
            continue
        run_id = str(record.get("id", record_path.stem))
        status = str(record.get("status", ""))
        terminal_at = _parse_dt(record.get("finished_at_utc")) or _parse_dt(
            record.get("updated_at_utc")
        )
        short = _short_id(run_id)
        seen_shorts.add(short)
        target = base / short
        if status not in TERMINAL_STATUSES:
            result.skipped.append({"run": run_id, "reason": f"live status {status!r}"})
            continue
        if terminal_at is None:
            result.skipped.append({"run": run_id, "reason": "no terminal date"})
            continue
        if terminal_at > cutoff:
            result.skipped.append({"run": run_id, "reason": "terminal too recently"})
            continue
        if not target.is_dir():
            result.skipped.append({"run": run_id, "reason": "no checkout"})
            continue
        resolved = target.resolve()
        if inventory.main is not None and resolved == inventory.main:
            result.skipped.append({"run": run_id, "reason": "is the main checkout"})
            continue
        if resolved not in inventory.registered:
            result.skipped.append({"run": run_id, "reason": "stray: not a registered worktree"})
            continue
        if resolved in inventory.locked:
            result.skipped.append({"run": run_id, "reason": "locked worktree"})
            continue
        result.candidates.append(
            Candidate(
                run_id=run_id,
                status=status,
                terminal_at=terminal_at.isoformat(),
                path=target,
                size_bytes=_dir_size(target),
            )
        )
    if base.is_dir():
        for entry in sorted(base.iterdir()):
            if entry.is_dir() and entry.name not in seen_shorts:
                result.skipped.append({"run": entry.name, "reason": "orphan: no run record"})
    # Deepest first so nested worktrees go before their parents.
    result.candidates.sort(key=lambda c: (len(c.path.parts), str(c.path)), reverse=True)
    return result


def prune_candidates(
    repo: Path,
    candidates: Sequence[Candidate],
    *,
    apply: bool,
    runner: Callable[..., str] | None = None,
) -> dict[str, object]:
    """Remove candidate checkouts (or report them in dry-run).

    Registered worktrees nested inside a candidate go first (deepest
    first); otherwise the parent removal fails on the nested registration.
    """
    run = runner or _run_git
    removed: list[str] = []
    nested_removed: list[str] = []
    errors: list[dict[str, str]] = []
    reclaimed = 0
    inventory = list_worktrees(repo, runner) if apply and candidates else None
    for candidate in candidates:
        if not apply:
            continue
        assert inventory is not None
        try:
            resolved = candidate.path.resolve()
        except OSError:
            resolved = candidate.path
        nested = sorted(
            (p for p in inventory.registered if p != resolved and resolved in p.parents),
            key=lambda p: (len(p.parts), str(p)),
            reverse=True,
        )
        try:
            for path in nested:
                run(repo, "worktree", "remove", "--force", str(path))
                nested_removed.append(str(path))
            run(repo, "worktree", "remove", "--force", str(candidate.path))
        except PrunerError as exc:
            errors.append({"run": candidate.run_id, "reason": str(exc)})
            continue
        removed.append(candidate.run_id)
        reclaimed += candidate.size_bytes
    return {
        "apply": apply,
        "candidates": len(candidates),
        "removed": removed,
        "nested_removed": nested_removed,
        "errors": errors,
        "bytes_reclaimed": reclaimed if apply else 0,
        "bytes_eligible": sum(c.size_bytes for c in candidates),
    }


def format_human(result: CollectionResult, report: dict[str, object]) -> str:
    """One-page dry-run/apply report for the operator."""
    lines = [
        f"candidates: {len(result.candidates)} "
        f"({int(report['bytes_eligible']) / 1e9:.2f} GB eligible)",
    ]
    for candidate in result.candidates:
        lines.append(
            f"  PRUNE {candidate.run_id} [{candidate.status}] "
            f"terminal {candidate.terminal_at} "
            f"{candidate.size_bytes / 1e6:.1f} MB {candidate.path}"
        )
    lines.append(f"skipped: {len(result.skipped)}")
    for item in result.skipped:
        lines.append(f"  SKIP {item['run']}: {item['reason']}")
    if report["apply"]:
        lines.append(
            f"removed: {len(report['removed'])} "
            f"({int(report['bytes_reclaimed']) / 1e9:.2f} GB reclaimed)"
        )
        nested = report.get("nested_removed", [])
        assert isinstance(nested, list)
        for path in nested:
            lines.append(f"  NESTED {path}")
        for error in report["errors"]:
            lines.append(f"  ERROR {error['run']}: {error['reason']}")
    else:
        lines.append("dry-run: nothing deleted (re-run with --apply)")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; dry-run unless ``--apply`` is given."""
    parser = argparse.ArgumentParser(description="Prune old run worktree checkouts.")
    parser.add_argument("--days", type=int, default=30, help="terminal age threshold")
    parser.add_argument("--apply", action="store_true", help="delete; default is dry-run")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--format", choices=("human", "json"), default="human")
    args = parser.parse_args(argv)
    repo = args.repo_root.resolve()
    data_dir = args.data_dir or (repo / "apps" / "workbench_dashboard" / "data")
    try:
        result = collect_candidates(repo, data_dir, args.days, datetime.now(UTC))
        report = prune_candidates(repo, result.candidates, apply=args.apply)
    except PrunerError as exc:
        print(f"prune-worktrees: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        payload = {
            "candidates": [
                {
                    "run_id": c.run_id,
                    "status": c.status,
                    "terminal_at": c.terminal_at,
                    "path": str(c.path),
                    "size_bytes": c.size_bytes,
                }
                for c in result.candidates
            ],
            "skipped": result.skipped,
            "report": report,
        }
        print(json.dumps(payload, indent=2))
    else:
        print(format_human(result, report), end="")
    errors = report["errors"]
    assert isinstance(errors, list)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
