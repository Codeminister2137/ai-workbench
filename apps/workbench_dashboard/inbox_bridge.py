"""Inbox-to-run bridge: owner->agent tasks become approval-gated runs.

Mai reads its backlog through this bridge instead of polling the inbox UI.
Only open items with ``assignee == "agent"`` and ``type == "task"`` are
bridged; decisions, clarifications, and orders always need the owner first.
Every bridged run is queued behind a fresh Approve/Reject decision, so the
existing approval gate keeps working unchanged. Bridged items are marked
(``metadata.bridge_run_id``) and never proposed twice.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from dashboard_stores import StoreError

MAX_BRIDGE_PER_CALL = 10


def bridge_agent_queue(stores, *, fanout_policy: str = "restricted") -> list[dict[str, Any]]:
    """Propose one queued run per unbridged open agent task.

    Returns per-item receipts ``{inbox_id, run_id, approval_id, status}``.
    Stops early (without failing) when the inbox is full.
    """
    receipts: list[dict[str, Any]] = []
    queued = stores.agent_queue(limit=MAX_BRIDGE_PER_CALL * 2)
    for item in queued:
        if len(receipts) >= MAX_BRIDGE_PER_CALL:
            break
        if not isinstance(item, dict):
            continue
        if item.get("type") != "task":
            continue
        metadata = item.get("metadata") or {}
        if not isinstance(metadata, dict):
            continue
        if metadata.get("bridge_run_id"):
            continue
        title = str(item.get("title") or "").strip()
        body = str(item.get("body") or "").strip()
        if not title:
            continue
        run_id = uuid.uuid4().hex
        now = datetime.now(UTC).isoformat()
        run_title = title[:60]
        try:
            approval = stores.create_inbox_task(
                title=f"Approve agent run: {run_title}",
                body=(
                    f"Inbox task {item['id']} was filed for the agent "
                    f"(fan-out: {fanout_policy}).\n\nTask:\n{title}\n\n{body}\n\n"
                    "Approve to let a run worker execute it; "
                    "Reject leaves it parked (never executed)."
                ),
                task_type="decision",
                task_id=run_id,
                context_refs=[f"run:{run_id}", f"inbox:{item['id']}"],
                options=["Approve", "Reject"],
            )
        except StoreError:
            break
        stores.runs.put(
            run_id,
            {
                "id": run_id,
                "title": run_title,
                "status": "queued",
                "body": f"{title}\n\n{body}",
                "origin": "inbox",
                "inbox_id": approval["id"],
                "bridged_from": item["id"],
                "fanout_policy": fanout_policy,
                "fanout_effective": fanout_policy,
                "created_at_utc": now,
                "updated_at_utc": now,
            },
        )
        updated = dict(item)
        updated["metadata"] = {**metadata, "bridge_run_id": run_id}
        refs = list(updated.get("context_refs") or [])
        if f"run:{run_id}" not in refs:
            refs.append(f"run:{run_id}")
        updated["context_refs"] = refs
        stores.inbox.put(item["id"], updated)
        receipts.append(
            {
                "inbox_id": item["id"],
                "run_id": run_id,
                "approval_id": approval["id"],
                "status": "proposed",
            }
        )
    return receipts
