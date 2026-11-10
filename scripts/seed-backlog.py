"""Seed the dashboard backlog with the known groomed items.

Idempotent by exact title: re-running skips titles already present.
Writes directly to the data dir (no running server needed).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SEEDS: tuple[tuple[str, str, str, str], ...] = (
    (
        "Conformance Groups 2-4 (owner call first)",
        "Deferred §1 leftover: Group 1 provider adapters done; orchestration/agents, "
        "council/job-search, repo tooling remain if the owner wants them.",
        "agent",
        "docs/plans/deferred-baseline-work-20261022.md §1",
    ),
    (
        "Replicate bounded fixture onto Go harness",
        "Deferred §3 leftover: controller mechanics shipped; the OpenCode Go harness "
        "still embeds its own fixture inline.",
        "agent",
        "docs/plans/deferred-baseline-work-20261022.md §3",
    ),
    (
        "Review P4 agent-UX proposal",
        "Supervised research proposal for commercial-standard agent UX. Decide: "
        "implement, reshape, or park.",
        "agent",
        "docs/plans/p4-agent-ux-proposal.md",
    ),
    (
        "Review P5 spend-policy proposal",
        "Supervised draft for owner review. May be partly consumed by the shipped "
        "spend ledger — confirm what remains.",
        "agent",
        "docs/plans/p5-spend-policy-proposal.md",
    ),
    (
        "Review branch consolidation checklist",
        "Nov-3 classification (DO NOT EXECUTE gate). Confirm or revise before any "
        "remote-ai-operator branch moves; develop-local prune done 2026-11-09.",
        "agent",
        "docs/plans/branch-consolidation-checklist.md",
    ),
    (
        "Verify edge round-1 fixes",
        "E research produced (operator + workbench sides, read-only). Verify which "
        "findings got fixed and file the rest.",
        "agent",
        "docs/plans/edge-round1-workbench.md",
    ),
    (
        "Documentation-conformance follow-ups",
        "Conformance plan in progress (first Ollama fix shipped). Work the bounded "
        "recorded findings route by route.",
        "agent",
        "docs/documentation-conformance-plan.md",
    ),
    (
        "Job-search execution plan: pick first slice",
        "Execution-ready plan exists; implementation starts when nothing else is "
        "pending. Pick the first slice or keep parked.",
        "agent",
        "docs/plans/job-search-execution-plan.md",
    ),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", default="apps/workbench_dashboard/data", help="Dashboard data directory"
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    dash_pkg = root / "apps" / "workbench_dashboard"
    sys.path.insert(0, str(dash_pkg))
    from dashboard_stores import DashboardStores

    stores = DashboardStores(Path(args.data_dir))
    items, _total = stores.backlog.list(limit=1000)
    existing = {item.get("title") for item in items}
    created = 0
    for title, body, source, ref in SEEDS:
        if title in existing:
            continue
        stores.create_backlog_item(title=title, body=body, source=source, ref=ref)
        existing.add(title)
        created += 1
    print(f"backlog seeds: {created} created, {len(SEEDS) - created} already present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
