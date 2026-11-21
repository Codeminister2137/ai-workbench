"""Observed-stop eval budgeting: snapshot allowance use, stop past threshold.

Cycle pattern (explicit, between tasks; overshoot accepted per owner
decision): snapshot windows before the cycle, run one eval task, check
the snapshot again, stop when any bucket's observed consumption passes
the threshold. Unknown readings never count as spend.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import TypeVar

from ai_provider.allowance_windows import AllowanceWindow
from ai_provider.eval_threshold import ObservedEvalThreshold

T = TypeVar("T")


class AllowanceTaskBudget:
    """One explicitly started cycle's finite task allowance and observed guard.

    Percentage readings cannot predict a request's cost. The tier set supplies
    the finite maximum; the ten percentage-point guard may stop it earlier.
    Retain this object across candidates/jobs in the same account cycle. Readers
    must enforce product headroom and return fresh, complete native windows.
    Restart recovery is caller-owned; never reconstruct a consumed cycle here.
    """

    def __init__(
        self,
        read: Callable[[], Sequence[AllowanceWindow]],
        *,
        clock: Callable[[], datetime],
        max_read_age: timedelta,
        max_tasks: int = 0,
        seed: int = 0,
        guard: ObservedEvalThreshold | None = None,
    ) -> None:
        from ai_provider.eval_task_sets import sample_tasks, tasks_for_tier

        if max_tasks < 0:
            raise ValueError("max_tasks must be nonnegative")
        if max_read_age <= timedelta(0):
            raise ValueError("max_read_age must be positive")
        self.tasks = sample_tasks(tasks_for_tier("allowance"), max_tasks, seed=seed)
        self.max_tasks = len(self.tasks)
        self.calls = 0
        self.stop_reason: str | None = None
        self.guard = guard if guard is not None else ObservedEvalThreshold()
        self.read = read
        self.clock = clock
        self.max_read_age = max_read_age

    def run(self, operation: Callable[[], T]) -> T | None:
        """Admit one call, retaining its result even if postflight stops us."""
        if self.stop_reason is not None:
            return None
        if self.calls >= self.max_tasks:
            self.stop_reason = "task allowance exhausted"
            return None
        completed: list[T] = []
        operation_errors: list[Exception] = []

        def invoke() -> T:
            self.calls += 1
            try:
                result = operation()
            except Exception as exc:
                operation_errors.append(exc)
                raise
            completed.append(result)
            return result

        try:
            return self.guard.run(
                invoke, self.read, clock=self.clock, max_read_age=self.max_read_age
            )
        except Exception as exc:
            self.stop_reason = f"{type(exc).__name__}: {exc}"
            if completed:
                return completed[0]
            if operation_errors:
                # Operation failures must not be mistaken for missing readings.
                if operation_errors[0] is exc:
                    raise
                raise operation_errors[0] from exc
            return None


WINDOW_KEY_FIELDS = ("provider", "bucket_id", "window")


def snapshot(windows: list[AllowanceWindow]) -> dict[str, float | None]:
    """Record per-bucket used percent (None when unreported)."""
    taken: dict[str, float | None] = {}
    for window in windows:
        taken["/".join(getattr(window, field) for field in WINDOW_KEY_FIELDS)] = window.used_percent
    return taken


def observed_spend(
    before: dict[str, float | None], now: dict[str, float | None]
) -> dict[str, float]:
    """Percentage-point consumption per bucket across two snapshots."""
    spend: dict[str, float] = {}
    for key, old in before.items():
        current = now.get(key)
        if old is None or current is None:
            continue
        spend[key] = round(max(0.0, current - old), 6)
    return spend


def over_threshold(spend: dict[str, float], threshold_pp: float) -> list[str]:
    """Buckets whose observed spend passed the threshold (sorted)."""
    if not threshold_pp > 0:
        raise ValueError("threshold must be positive")
    return sorted(key for key, used in spend.items() if used > threshold_pp)


def _load_windows(path: Path) -> list[AllowanceWindow]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("windows snapshot must be a JSON list")
    return [AllowanceWindow(**entry) for entry in raw]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    snap = sub.add_parser("snapshot", help="Record current per-bucket use")
    snap.add_argument("--windows", type=Path, required=True)
    snap.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("check", help="Compare spend; exit 1 when over threshold")
    check.add_argument("--before", type=Path, required=True)
    check.add_argument("--windows", type=Path, required=True)
    check.add_argument("--threshold-pp", type=float, required=True)
    args = parser.parse_args(argv)
    if args.action == "snapshot":
        if args.output.exists():
            parser.error("output already exists; preserve consumed snapshots")
        taken = snapshot(_load_windows(args.windows))
        args.output.write_text(json.dumps(taken, indent=1, sort_keys=True), encoding="utf-8")
        return 0
    before = json.loads(args.before.read_text(encoding="utf-8"))
    if not isinstance(before, dict):
        parser.error("before snapshot must be a JSON object")
    spend = observed_spend(before, snapshot(_load_windows(args.windows)))
    breached = over_threshold(spend, args.threshold_pp)
    print(json.dumps({"spend_pp": spend, "over_threshold": breached}, indent=1))
    return 1 if breached else 0


if __name__ == "__main__":
    raise SystemExit(main())
