"""Derive remaining unattended-loop work from the plan ledger and inbox.

Completion claims must quote this output instead of model prose: it lists
every ledger row that is not COMPLETE plus open inbox items, so "nothing
left" is a machine-checked statement. Read-only; exit 0 always.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parents[1]

STATUS_KEYWORDS = (
    "COMPLETE",
    "BLOCKED",
    "READY",
    "NEEDS_INVESTIGATION",
    "IN_PROGRESS",
    "REVERTED",
)
TERMINAL = ("COMPLETE", "REVERTED")


def parse_ledger(plan_path: Path) -> tuple[list[dict], str | None]:
    """Return ledger rows plus an error note when the plan is unreadable."""
    try:
        text = plan_path.read_text(encoding="utf-8")
    except OSError:
        return [], f"plan not readable: {plan_path}"
    rows: list[dict] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 7 or cells[0].lower() == "order" or cells[0].startswith("---"):
            continue
        status_text = cells[6]
        keyword = status_text.split(" ", 1)[0] if status_text else ""
        rows.append(
            {
                "order": cells[0],
                "action": cells[1],
                "status": keyword if keyword in STATUS_KEYWORDS else "UNMARKED",
                "detail": status_text,
            }
        )
    if not rows:
        return [], f"no ledger rows found in {plan_path}"
    return rows, None


def open_inbox_items(data_dir: Path) -> tuple[list[dict] | None, str | None]:
    """Return open inbox items, or (None, reason) when the store is absent."""
    if not data_dir.is_dir():
        return None, f"data dir missing: {data_dir}"
    sys.path.insert(0, str(REPO_ROOT / "apps" / "workbench_dashboard"))
    try:
        from dashboard_stores import DashboardStores  # noqa: PLC0415 - optional surface
    except ImportError as exc:
        return None, f"dashboard stores unavailable: {exc}"
    try:
        stores = DashboardStores(data_dir)
        items, _total = stores.inbox.list(limit=50)
    except Exception as exc:  # noqa: BLE001 - probe reports, never raises
        return None, f"inbox unreadable: {type(exc).__name__}"
    return [item for item in items if item.get("status") == "open"], None


def render(plan_path: Path, data_dir: Path) -> str:
    """Render the remaining-work summary as plain text."""
    lines = [f"plan: {plan_path}"]
    rows, error = parse_ledger(plan_path)
    if error is not None:
        lines.append(error)
        rows = []
    remaining = [row for row in rows if row["status"] not in TERMINAL]
    blocked = [row for row in rows if row["status"] == "BLOCKED"]
    complete = [row for row in rows if row["status"] in TERMINAL]
    lines.append(
        f"ledger: {len(complete)} complete, {len(blocked)} blocked, "
        f"{len(remaining) - len(blocked)} remaining, {len(rows)} rows"
    )
    actionable = [row for row in remaining if row["status"] != "BLOCKED"]
    if actionable:
        lines.append("remaining:")
        for row in actionable:
            lines.append(f"- [{row['order']}] {row['action']} ({row['status']})")
    if blocked:
        lines.append("blocked-pending:")
        for row in blocked:
            lines.append(f"- [{row['order']}] {row['action']} — {row['detail']}")
    if not remaining:
        lines.append("remaining: none (ledger fully complete)")
    items, inbox_error = open_inbox_items(data_dir)
    if inbox_error is not None:
        lines.append(f"open inbox: unknown ({inbox_error})")
    else:
        assert items is not None
        lines.append(f"open inbox: {len(items)}")
        for item in items[:10]:
            lines.append(
                f"- {item.get('title', '?')} [{item.get('task_type', item.get('type', '?'))}]"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Print remaining work; always exit 0 (read-only probe)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan",
        type=Path,
        default=REPO_ROOT / "docs" / "plans" / "unattended-work-plan.md",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=REPO_ROOT / "apps" / "workbench_dashboard" / "data",
    )
    args = parser.parse_args(argv)
    print(render(args.plan, args.data_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
