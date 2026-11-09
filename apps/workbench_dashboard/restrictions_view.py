"""Live restriction feeders for the dashboard Restrictions tab.

Slice 1: subprocess execution counts from persisted run requests and
their linked inbox approvals. Every other dimension stays honestly
"not yet evaluated" until its own feeder exists (see
docs/restrictions-feeders-note.md).
"""

from __future__ import annotations

from collections import Counter
from typing import Any

RUN_APPROVAL_TITLE_PREFIX = "Approve agent run: "
_LIST_LIMIT = 10000


def restrictions_status(stores) -> dict[str, Any]:
    """Count chat-originated runs and their approval outcomes."""
    runs, _ = stores.runs.list(limit=_LIST_LIMIT)
    chat_runs = [r for r in runs if isinstance(r, dict) and r.get("origin") == "chat"]
    by_status = dict(Counter(str(r.get("status") or "unknown") for r in chat_runs))
    inbox, _ = stores.inbox.list(limit=_LIST_LIMIT)
    approvals = [
        i
        for i in inbox
        if isinstance(i, dict) and str(i.get("title") or "").startswith(RUN_APPROVAL_TITLE_PREFIX)
    ]
    approved = sum(1 for i in approvals if i.get("answer") == "Approve")
    rejected = sum(1 for i in approvals if i.get("answer") == "Reject")
    pending = sum(1 for i in approvals if i.get("status") == "open")
    return {
        "ok": True,
        "subprocess": {
            "run_requests": len(chat_runs),
            "by_status": by_status,
            "approvals": len(approvals),
            "approved": approved,
            "rejected": rejected,
            "pending": pending,
        },
    }
