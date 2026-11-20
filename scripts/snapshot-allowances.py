"""Snapshot live subscription-allowance windows to JSON.

Reads every allowance-bearing catalog route through the existing native
readers (``ai_provider.allowance_windows``) and writes one JSON list for
``eval_planner`` / ``eval_budget``. Observation only: no inference runs,
no quota is consumed. Targets without a readable allowance are skipped
with a stderr note; the planner then proposes nothing for that bucket,
which is the conservative correct behavior.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "ai_orchestrator" / "src"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "ai_provider" / "src"))

from ai_orchestrator import (  # noqa: E402
    AccessMethod,
    AuthMethod,
    BillingSource,
    CostPolicyTier,
    ExecutionTarget,
)
from ai_provider.allowance_windows import read_allowance_windows  # noqa: E402


def snapshot_catalog(catalog: Path) -> list[dict]:
    """Observe allowance windows for every allowance route in one catalog."""
    rows = tomllib.loads(catalog.read_text(encoding="utf-8"))["models"]
    collected: list[dict] = []
    for row in rows:
        try:
            target = ExecutionTarget(
                route_id=row["route_id"],
                provider=row["provider"],
                product=row.get("product", row["provider"]),
                model=row["model"],
                access_method=AccessMethod(row["access_method"]),
                auth_method=AuthMethod(row["auth_method"]),
                billing_source=BillingSource(row["billing_source"]),
                cost_policy_tier=CostPolicyTier(row["cost_policy_tier"]),
                base_url=row.get("base_url"),
            )
        except (KeyError, ValueError) as exc:
            print(f"skip {row.get('route_id', '?')}: bad catalog row ({exc})", file=sys.stderr)
            continue
        try:
            windows = read_allowance_windows(target)
        except Exception as exc:  # noqa: BLE001 - one unreadable target skips, never aborts
            print(f"skip {target.route_id}: unreadable ({type(exc).__name__})", file=sys.stderr)
            continue
        if windows is None:
            print(f"skip {target.route_id}: no allowance report", file=sys.stderr)
            continue
        collected.extend(asdict(window) for window in windows)
    return collected


def _dedupe(entries: list[dict]) -> list[dict]:
    """One row per bucket; several catalog routes can share one allowance."""
    seen: set[tuple[str, str, str]] = set()
    unique = []
    for entry in entries:
        key = (entry["provider"], entry["bucket_id"], entry["window"])
        if key not in seen:
            seen.add(key)
            unique.append(entry)
    return unique


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output already exists; preserve consumed snapshots")
    snapshots: list[dict] = []
    for catalog in args.catalog:
        snapshots.extend(snapshot_catalog(catalog))
    snapshots = _dedupe(snapshots)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshots, indent=1), encoding="utf-8")
    print(f"snapshotted {len(snapshots)} windows from {len(args.catalog)} catalog(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
