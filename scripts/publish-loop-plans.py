"""CLI: publish loop slices, runs, and decisions into the dashboard stores.

Examples:
  publish-loop-plans.py plan --id loop-20261102 --title "Evening loop" \\
      --file docs/plans/loop-20261102-evening.md --status complete
  publish-loop-plans.py run --id stream-a-d4 --title "D4 dashboard batch" \\
      --status merged --branch fix/dashboard-ui-batch-20261102 --commit 73ff918
  publish-loop-plans.py decision --title "H1: full drain or planning-only?" \\
      --body-file /tmp/h1.md --option "Ship planning-only" --option "Build full drain"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "workbench_dashboard"))

from dashboard_stores import DashboardStores  # noqa: E402
from plan_publisher import sync_decision, sync_plan, sync_run  # noqa: E402

DEFAULT_DATA_DIR = ROOT / "apps" / "workbench_dashboard" / "data"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Sync one markdown plan file")
    plan.add_argument("--id", required=True)
    plan.add_argument("--title", required=True)
    plan.add_argument("--file", type=Path, required=True)
    plan.add_argument("--status", required=True)

    run = sub.add_parser("run", help="Sync one work-slice run record")
    run.add_argument("--id", required=True)
    run.add_argument("--title", required=True)
    run.add_argument("--status", required=True)
    run.add_argument("--body", default="")
    run.add_argument("--branch", default=None)
    run.add_argument("--commit", default=None)
    run.add_argument("--validation", default=None)
    run.add_argument("--report", default=None)

    decision = sub.add_parser("decision", help="Create one owner decision task")
    decision.add_argument("--title", required=True)
    group = decision.add_mutually_exclusive_group(required=True)
    group.add_argument("--body", default=None)
    group.add_argument("--body-file", type=Path, default=None)
    decision.add_argument("--option", dest="options", action="append", default=[])
    decision.add_argument("--type", default="decision", choices=("decision", "clarification"))
    decision.add_argument("--plan-id", default=None)
    decision.add_argument("--context-ref", dest="context_refs", action="append", default=[])
    decision.add_argument("--no-dedupe", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    stores = DashboardStores(args.data_dir)
    if args.command == "plan":
        record = sync_plan(
            stores,
            plan_id=args.id,
            title=args.title,
            source_file=args.file,
            status=args.status,
        )
    elif args.command == "run":
        record = sync_run(
            stores,
            run_id=args.id,
            title=args.title,
            status=args.status,
            body=args.body,
            branch=args.branch,
            commit=args.commit,
            validation=args.validation,
            report=args.report,
        )
    else:
        body = args.body if args.body is not None else args.body_file.read_text(encoding="utf-8")
        record = sync_decision(
            stores,
            title=args.title,
            body=body,
            options=args.options,
            task_type=args.type,
            plan_id=args.plan_id,
            context_refs=args.context_refs or None,
            dedupe_open=not args.no_dedupe,
        )
    print(("deduped " if record.get("deduped") else "wrote ") + record["id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
