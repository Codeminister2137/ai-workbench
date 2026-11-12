"""Dashboard invoice drafts: store + review flow over company billing rules.

Drafts are validated by company-site billing (NIP, VAT, numbering) and
reviewed through its hash-chained founder approval; any edit clears the
approval. Sending, KSeF submission, and payment tracking are out of
scope until the accountant-verified template exists.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _billing():
    """Import company billing (lazy: company-site is not a package)."""
    root = Path(__file__).resolve().parent.parent.parent / "company-site"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import billing

    return billing


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _record_to_draft(record: dict, billing) -> Any:
    return billing.draft_from_dict(record["draft"])


def create_draft(stores, payload: dict, *, seller_defaults: dict | None = None) -> dict[str, Any]:
    """Validate and store one draft; numbers must be unique."""
    billing = _billing()
    if not isinstance(payload, dict):
        raise ValueError("draft input must be an object")
    merged = dict(payload)
    if seller_defaults:
        seller = dict(seller_defaults)
        if isinstance(merged.get("seller"), dict):
            seller.update(merged["seller"])
        merged["seller"] = seller
    try:
        draft = billing.draft_from_dict(merged)
    except ValueError as exc:
        raise ValueError(str(exc)) from None
    items, _total = stores.invoices.list(limit=1000)
    if any(item.get("number") == draft.number for item in items if isinstance(item, dict)):
        raise ValueError(f"duplicate invoice number: {draft.number}")
    now = _utc_now()
    record = {
        "id": uuid.uuid4().hex,
        "number": draft.number,
        "draft": json.loads(billing.canonical_json(draft)),
        "approval": None,
        "created_at_utc": now,
        "updated_at_utc": now,
    }
    stores.invoices.put(record["id"], record)
    return _present(record, billing)


def get_invoice(stores, invoice_id: str) -> dict[str, Any] | None:
    """Load one draft with derived totals, text, and approval state."""
    billing = _billing()
    record = stores.invoices.get(invoice_id)
    if record is None:
        return None
    return _present(record, billing)


def list_invoices(stores, *, limit: int = 100) -> list[dict[str, Any]]:
    """Newest-first draft summaries."""
    billing = _billing()
    items, _total = stores.invoices.list(limit=limit)
    rows = []
    for record in items:
        if not isinstance(record, dict):
            continue
        try:
            draft = _record_to_draft(record, billing)
            totals = billing.draft_totals(draft)
        except (ValueError, KeyError):
            continue
        approval = record.get("approval")
        rows.append(
            {
                "id": record.get("id"),
                "number": record.get("number"),
                "buyer": record.get("draft", {}).get("buyer", {}).get("name", "?"),
                "gross": str(totals["gross"]),
                "approved": _approval_valid(record, billing),
                "updated_at_utc": record.get("updated_at_utc"),
                "approval": approval,
            }
        )
    return rows


def _approval_valid(record: dict, billing) -> bool:
    approval = record.get("approval")
    if not isinstance(approval, dict) or not approval.get("draft_hash"):
        return False
    try:
        draft = _record_to_draft(record, billing)
    except (ValueError, KeyError):
        return False
    try:
        expected = billing.DraftApproval(
            draft_hash=str(approval["draft_hash"]),
            reviewer=str(approval.get("reviewer", "")),
            reviewed_at=str(approval.get("reviewed_at", "")),
        )
    except (ValueError, TypeError):
        return False
    return bool(billing.approval_valid(draft, expected))


def review_draft(stores, invoice_id: str, reviewer: str) -> dict[str, Any]:
    """Founder review: approve this exact draft content only."""
    billing = _billing()
    record = stores.invoices.get(invoice_id)
    if record is None:
        raise KeyError(invoice_id)
    draft = _record_to_draft(record, billing)
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("reviewer is required")
    approval = billing.review_draft(draft, reviewer.strip(), _utc_now())
    record["approval"] = {
        "draft_hash": approval.draft_hash,
        "reviewer": approval.reviewer,
        "reviewed_at": approval.reviewed_at,
    }
    record["updated_at_utc"] = _utc_now()
    stores.invoices.put(invoice_id, record)
    return _present(record, billing)


def update_draft(stores, invoice_id: str, payload: dict) -> dict[str, Any]:
    """Replace draft content; clears any approval (mutation invalidates)."""
    billing = _billing()
    record = stores.invoices.get(invoice_id)
    if record is None:
        raise KeyError(invoice_id)
    if not isinstance(payload, dict):
        raise ValueError("draft input must be an object")
    draft = billing.draft_from_dict(payload)
    if draft.number != record.get("number"):
        items, _total = stores.invoices.list(limit=1000)
        if any(
            item.get("number") == draft.number and item.get("id") != invoice_id
            for item in items
            if isinstance(item, dict)
        ):
            raise ValueError(f"duplicate invoice number: {draft.number}")
    record["number"] = draft.number
    record["draft"] = json.loads(billing.canonical_json(draft))
    record["approval"] = None
    record["updated_at_utc"] = _utc_now()
    stores.invoices.put(invoice_id, record)
    return _present(record, billing)


def _present(record: dict, billing) -> dict[str, Any]:
    draft = _record_to_draft(record, billing)
    totals = billing.draft_totals(draft)
    return {
        "id": record.get("id"),
        "number": record.get("number"),
        "draft": record.get("draft"),
        "totals": {key: str(value) for key, value in totals.items()},
        "text": billing.render_text(draft),
        "ksef": billing.ksef_ready_dict(draft),
        "approval": record.get("approval"),
        "approval_valid": _approval_valid(record, billing),
        "created_at_utc": record.get("created_at_utc"),
        "updated_at_utc": record.get("updated_at_utc"),
    }
