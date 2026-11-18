"""Seed one Roadmap per product project (idempotent upsert).

Roadmap structure per owner spec: spawning context, initial plan,
evolutions, current state. Closeouts append evolutions via
DashboardStores.append_plan_evolution. Usage:

    python scripts/seed-roadmaps.py [--dry-run] [--data-dir DIR]
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "apps" / "workbench_dashboard"))

from dashboard_projects import load_registry  # noqa: E402
from dashboard_stores import DashboardStores  # noqa: E402

WORKBENCH_EVOLUTIONS = """- 2026-11-18: work-tabs unification batch (relations, attention, roadmaps, projects).
- 2026-11-17: report-or-escalate invariant, E2E quality bars, inbox badge-gap banner, notes readability (96c867b..7451303).
- 2026-11-17: D2c usage-to-ledger, E2E package A, zero pyright, coverage ratchet 89.
- 2026-11-16: agent-first E2E pointers, prepaid spend model, allowance windows + refresh audit.
- 2026-11-14..16: window-vanish v2 auto-restore, forgotten sweep + weekly task, agent-queue delegation C."""

ROADMAPS: tuple[tuple[str, str, str], ...] = (
    (
        "ai-workbench",
        "ai-workbench Roadmap",
        """## Spawning context

Owner 2026-11-17/18: unify the work tabs through project relations, make
Plans the live dev-state surface, separate the products with explainer
files. Full brief: docs/plans/work-tabs-unification-20261117.md.

## Initial plan

Relations layer, attention unification + AI close-out, Roadmaps, project
separation, gate/push/verify, push-transfer investigation.

## Evolutions

"""
        + WORKBENCH_EVOLUTIONS
        + """

## State

Executing work-tabs unification. Assessment: docs/plans/repo-gap-assessment-20261117.md.
""",
    ),
    (
        "Mai agent",
        "Mai agent Roadmap",
        """## Spawning context

Owner goal: switch daily driving from Muse CLI to Mai with no capability
loss, then let Mai run the workbench unattended.

## Initial plan

Mai-as-service batch resume first (unattended drain driver + boot
reconciliation), then interactive agentic dashboard chat, then switch
readiness sign-off.

## Evolutions

- 2026-11-17: interactive Mai chat surface live (scoped), Mai budget 96k.
- 2026-11-14..16: Mai slices A-C, agent-queue delegation C, drain auto-pause.
- 2026-11-18: pointer runs route through Mai with decline re-queue.

## State

Surface shipped; robustness (stuck detection, empty-completion guard,
instruction budget) open. Blocked: supervision placement/authority/paging
owner decision.
""",
    ),
    (
        "job search",
        "job search Roadmap",
        """## Spawning context

Owner goal: automate finding and applying to fitting offers (CV variants,
match scoring, tailored applications).

## Initial plan

Adopt the Openings service (reuse-first); personalize scoring with owner
answers; then execution-plan M2-M4.

## Evolutions

- 2026-11-17: Openings Q7 profile applied; Q6/Q7 finalized in job-preferences.toml.
- 2026-11-16: Openings adopted + personalized scoring.

## State

M1 done. Open: M2/M3/M4, Prospeo+Apollo accounts, Polish-board adapters,
bridge/API wiring.
""",
    ),
    (
        "company site",
        "company site Roadmap",
        """## Spawning context

P7 decision: sell software via an impressive public site (offer, intake,
chatbot) with decision-traced content.

## Initial plan

Shell + intake first; offering details, naming, and pricing follow P7
deliberation answers.

## Evolutions

- 2026-11-13..17: dark mode, auto-serve, intake flow live.
- 2026-11-17: E2E company-site checks strengthened (package A).

## State

Launch-blocked on P7 answers: naming (R6), offering details, HU/HUF purge,
nine placeholders.
""",
    ),
    (
        "knowme-bank",
        "knowme-bank Roadmap",
        """## Spawning context

Owner goal: a local-first personal knowledge bank feeding the trainer,
matching, and the dashboard.

## Initial plan

SQLite + interview importer first, then atomic ingest with provenance,
then grouped display, then AI trainer slice.

## Evolutions

- 2026-11-17: KnowMe answer A shipped (atomic ingest, schema v2,
  provenance); tag-grouped layout live and tested.
- 2026-11-16: bank-first trainer slice scoped.

## State

Storage + ingest + display done. Open: AI trainer first slice (needs
owner go); personal bank still thin (10 entries).
""",
    ),
    (
        "dashboard",
        "dashboard Roadmap",
        """## Spawning context

Owner rule: everything dashboard-operable; the dashboard is the single
surface for inbox, runs, plans, E2E, spend, and fleet.

## Initial plan

P6 slices, then tiered merges + E2E promotion, then work-tabs unification.

## Evolutions

- 2026-11-18: relations layer, attention unification, roadmaps, projects.
- 2026-11-17: badge parity, divergence banner, notes readability, spend
  card, restrictions/schedule/fleet slices.
- 2026-11-14..16: agent chat visibility, window watchdog, weekly digest.

## State

Serving current code on :8766. Open: dynamic orchestrator queries,
Trainer activation.
""",
    ),
    (
        "AI council",
        "AI council Roadmap",
        """## Spawning context

Owner goal: multi-model deliberation integrated with the orchestrator.

## Initial plan

Parallel-ask prototype first, then synthesis slice 2, then orchestrator
integration and eval phases.

## Evolutions

- 2026-11-13: slice-1 protocol settled; parallel-ask over Ollama.

## State

Prototype stage; least-evolved module. Open: synthesis slice 2,
orchestrator integration, evals.
""",
    ),
)


def seed_roadmaps(data_dir: Path, *, dry_run: bool) -> list[str]:
    """Upsert the seven Roadmaps; returns seeded ids."""
    stores = DashboardStores(data_dir)
    registry = load_registry(data_dir)
    by_name = {str(record.get("name")): record for record in registry.values()}
    seeded: list[str] = []
    for name, title, body in ROADMAPS:
        record = by_name.get(name)
        if record is None:
            print(f"  SKIP {title}: project '{name}' not registered")
            continue
        plan_id = f"roadmap-{name.lower().replace(' ', '-')}"
        if not dry_run:
            now = datetime.now(UTC).isoformat()
            existing = stores.plans.get(plan_id)
            stores.plans.put(
                plan_id,
                {
                    "id": plan_id,
                    "title": title,
                    "status": "active",
                    "kind": "roadmap",
                    "parent_plan_id": None,
                    "body": body,
                    "project_id": record["id"],
                    "source": "seed-roadmaps.py",
                    "created_at_utc": (existing or {}).get("created_at_utc") or now,
                    "updated_at_utc": now,
                },
            )
        seeded.append(plan_id)
        print(f"  + {title} ({record['id'][:8]})")
    return seeded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed one Roadmap per product project.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--data-dir", default=str(REPO / "apps" / "workbench_dashboard" / "data"))
    args = parser.parse_args(argv)
    seeded = seed_roadmaps(Path(args.data_dir), dry_run=args.dry_run)
    print(f"seeded: {len(seeded)}")
    return 0 if len(seeded) == len(ROADMAPS) else 2


if __name__ == "__main__":
    raise SystemExit(main())
