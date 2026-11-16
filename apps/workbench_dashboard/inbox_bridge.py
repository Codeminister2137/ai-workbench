"""Inbox-to-run bridge: agent tasks become runs, owner filings pre-approved.

Mai reads its backlog through this bridge instead of polling the inbox UI.
Only open items with ``assignee == "agent"`` and ``type == "task"`` are
bridged; decisions, clarifications, and orders always need the owner first.
Tasks filed by the owner are pre-approved (filing is approval) and queued
without a self-approval decision, as are E2E follow-up tasks (owner
decision 2026-11-16: the agent acts, the owner re-tests the behavior).
Other supervisor/agent-filed tasks keep the Approve/Reject gate. Bridged
items are marked (``metadata.bridge_run_id``) and never proposed twice.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from dashboard_stores import StoreError

MAX_BRIDGE_PER_CALL = 10


def resolve_bridge_fanout(raw: object) -> str:
    """Coerce the configured bridge fan-out policy; fail-closed to restricted."""
    from ai_agent.fanout import FanoutPolicy

    try:
        return FanoutPolicy.coerce(str(raw or "restricted")).value
    except ValueError:
        return FanoutPolicy.RESTRICTED.value


def _mai_timeout_override(metadata: dict) -> dict[str, float]:
    """Validated Mai timeout override from task metadata (empty when absent).

    Long agent tasks die on Mai's internal default otherwise; the value
    is clamped below the drain's own subprocess timeout so the override
    can never outlive its supervisor.
    """
    raw = metadata.get("mai_timeout_seconds")
    if raw is None:
        return {}
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        return {}
    if seconds < 60:
        return {}
    return {"mai_timeout_seconds": min(seconds, 1500.0)}


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
        timeout_override = _mai_timeout_override(metadata)
        now = datetime.now(UTC).isoformat()
        run_title = title[:60]
        if str(item.get("created_by") or "") == "owner":
            preapproval = "owner-filed"
        elif metadata.get("kind") == "e2e-followup":
            preapproval = "e2e-followup"
        else:
            preapproval = None
        if preapproval is not None:
            stores.runs.put(
                run_id,
                {
                    "id": run_id,
                    "title": run_title,
                    "status": "queued",
                    "body": f"{title}\n\n{body}",
                    "origin": "inbox",
                    "inbox_id": None,
                    "approval_mode": preapproval,
                    "bridged_from": item["id"],
                    "fanout_policy": fanout_policy,
                    "fanout_effective": fanout_policy,
                    "created_at_utc": now,
                    "updated_at_utc": now,
                    **timeout_override,
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
                    "approval_id": None,
                    "status": "preapproved",
                }
            )
            continue
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
                **timeout_override,
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
