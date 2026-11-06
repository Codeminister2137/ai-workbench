"""Publish loop slices, runs, and owner decisions into dashboard stores.

Loop/edge work lives in markdown plans that the dashboard never sees, so
status labels like "W4 finished" are opaque to the owner. These helpers sync
plan files, run records, and decision prompts into the plans/runs/inbox
collections the dashboard UI already renders (no serve restart needed).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from dashboard_stores import DashboardStores, StoreError


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def sync_plan(
    stores: DashboardStores,
    *,
    plan_id: str,
    title: str,
    source_file: Path,
    status: str,
) -> dict:
    """Store one markdown plan file as a dashboard plan (upsert by id)."""
    try:
        body = source_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise StoreError(f"Cannot read plan file: {source_file}") from exc
    record = {
        "id": plan_id,
        "title": title,
        "status": status,
        "body": body,
        "source": str(source_file),
        "updated_at_utc": _utc_now(),
    }
    stores.plans.put(plan_id, record)
    return record


def sync_run(
    stores: DashboardStores,
    *,
    run_id: str,
    title: str,
    status: str,
    body: str = "",
    branch: str | None = None,
    commit: str | None = None,
    validation: str | None = None,
    report: str | None = None,
) -> dict:
    """Store one work-slice run record (upsert by id)."""
    record = {
        "id": run_id,
        "title": title,
        "status": status,
        "body": body,
        "branch": branch,
        "commit": commit,
        "validation": validation,
        "report": report,
        "updated_at_utc": _utc_now(),
    }
    stores.runs.put(run_id, record)
    return record


def sync_decision(
    stores: DashboardStores,
    *,
    title: str,
    body: str,
    options: list[str],
    task_type: str = "decision",
    plan_id: str | None = None,
    context_refs: list[str] | None = None,
    dedupe_open: bool = True,
) -> dict:
    """Create one owner decision task; skip when the same title is open.

    Returns the existing open record when deduped (with ``deduped: True``
    marker in the returned copy only — the stored record is untouched).
    """
    if dedupe_open:
        items, _total = stores.inbox.list(limit=100)
        for item in items:
            if (
                item.get("status") == "open"
                and (item.get("title") or "").strip().casefold() == title.strip().casefold()
            ):
                return {**item, "deduped": True}
    return stores.create_inbox_task(
        title=title,
        body=body,
        task_type=task_type,
        plan_id=plan_id,
        context_refs=context_refs,
        options=options,
    )
