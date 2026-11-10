#!/usr/bin/env python3
"""Close or reopen an inbox task."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Close or reopen an inbox task")
    parser.add_argument("--id", required=True, dest="item_id", help="Inbox task id")
    parser.add_argument("--resolution", default=None, help="Resolution note")
    parser.add_argument("--resolution-file", default=None, help="File containing resolution note")
    parser.add_argument(
        "--kind",
        default="final",
        choices=("final", "followup"),
        help="final archives; followup marks no-final-answer and stays out of the archive",
    )
    parser.add_argument("--reopen", action="store_true", help="Reopen a closed task")
    parser.add_argument(
        "--data-dir", default="apps/workbench_dashboard/data", help="Dashboard data directory"
    )
    args = parser.parse_args()

    # Insert apps/workbench_dashboard so `import dashboard_stores` works.
    dash_pkg = Path(__file__).resolve().parent.parent / "apps" / "workbench_dashboard"
    sys.path.insert(0, str(dash_pkg))
    from dashboard_stores import DashboardStores, StoreError

    data_dir = Path(args.data_dir)
    stores = DashboardStores(data_dir)

    try:
        if args.reopen:
            record = stores.reopen_inbox_task(args.item_id)
        else:
            resolution = args.resolution
            if args.resolution_file:
                resolution = Path(args.resolution_file).read_text(encoding="utf-8")
            # If neither provided, let store raise the required error
            if resolution is None:
                # Trigger StoreError path for missing resolution
                record = stores.close_inbox_task(args.item_id, resolution=None)
            else:
                record = stores.close_inbox_task(
                    args.item_id, resolution=resolution, resolution_kind=args.kind
                )
        print(f"{record.get('id')} {record.get('status')}")
    except StoreError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
