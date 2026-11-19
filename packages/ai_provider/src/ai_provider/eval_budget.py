"""Observed-stop eval budgeting: snapshot allowance use, stop past threshold.

Cycle pattern (explicit, between tasks; overshoot accepted per owner
decision): snapshot windows before the cycle, run one eval task, check
the snapshot again, stop when any bucket's observed consumption passes
the threshold. Unknown readings never count as spend.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_provider.allowance_windows import AllowanceWindow

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
