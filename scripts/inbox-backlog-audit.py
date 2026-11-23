"""Inbox backlog audit: stock health, not flow.

Sweeps review NEW completions; this audits the OPEN STOCK so stale,
failed-holder, and followup-visible items cannot rot unnoticed (owner
finding, 2026-11-23: 64 open agent items, 20 visible followups, zero
sweep coverage of any of it).

Buckets:
- stale-failed: agent task whose linked run is failed/cancelled and old
  (needs retry-plan or owner-brief, never silence).
- unbridged-old: agent task never bridged and older than 24h (needs
  triage: queue, close stale, or route to owner).
- followup-visible: any non-archived item flagged needs-follow-up
  (each needs an actionable next step or final archival).
- owner-waiting: open owner items (informational; owner clears).
- active: everything else (in flight or fresh).

Exit 0 always; prints buckets. Proposed cadence: daily + on demand.
Owner rule enforced by protocol, not code: 'agent failed' alone is
never a conclusion - every item ends in continuation or a human call.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def audit(data_dir: Path, stale_hours: float = 12.0, old_hours: float = 24.0) -> dict:
    now = time.time()
    runs: dict[str, str] = {}
    for path in (data_dir / "runs").glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        runs[path.stem[:8]] = str(record.get("status", "?"))
    buckets: dict[str, list[str]] = {
        "stale-failed": [],
        "unbridged-old": [],
        "followup-visible": [],
        "owner-waiting": [],
        "active": [],
    }
    for path in sorted((data_dir / "inbox").glob("*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        short = path.stem[:8]
        status = item.get("status")
        if (item.get("resolution_kind") or "final") != "final" and status != "archived":
            buckets["followup-visible"].append(short)
            continue
        if status != "open":
            continue
        if item.get("assignee") != "agent":
            buckets["owner-waiting"].append(short)
            continue
        age_h = (now - path.stat().st_mtime) / 3600
        bridge = (item.get("metadata") or {}).get("bridge_run_id") or ""
        if not bridge:
            buckets["unbridged-old" if age_h > old_hours else "active"].append(short)
            continue
        run_status = runs.get(bridge[:8], "NOREC")
        if run_status in ("failed", "cancelled") and age_h > stale_hours:
            buckets["stale-failed"].append(short)
        else:
            buckets["active"].append(f"{short}:{run_status}")
    return buckets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("apps/workbench_dashboard/data"))
    parser.add_argument("--stale-hours", type=float, default=12.0)
    parser.add_argument("--old-hours", type=float, default=24.0)
    args = parser.parse_args()
    buckets = audit(args.data_dir, args.stale_hours, args.old_hours)
    total_open = 0
    for name, members in buckets.items():
        print(f"{name} {len(members)}")
        for member in members[:20]:
            print(f"  {member}")
        if name != "followup-visible":
            total_open += len(members) if name != "active" else 0
    print(
        f"open-agent-needing-attention: {len(buckets['stale-failed']) + len(buckets['unbridged-old'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
