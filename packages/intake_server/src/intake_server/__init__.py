"""Transport-agnostic intake core: validate, forward, log.

Pure logic for the server-side company-site intake (owner B on
6b3153f7). No vendor SDK, no sockets, no filesystem: the hosting
binding (B3) injects ``forward`` (mailbox) and ``log`` (lead store)
callables plus rate-limit state. Validation mirrors form.js exactly
(same required fields, same budget sets, same E.164 phone rule) so
browser and server never disagree.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable, MutableMapping
from datetime import UTC, datetime
from typing import Any

MAX_BODY_BYTES = 32 * 1024
RATE_LIMIT_PER_HOUR = 5
RATE_WINDOW_SECONDS = 3600.0

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")
BUDGETS_PL = frozenset({"<10k", "10–30k", "30–80k", "80k+", "undisclosed"})
BUDGETS_EN = frozenset({"<2k", "2-5k", "5-15k", "15k+", "undisclosed"})
BUDGETS = BUDGETS_PL | BUDGETS_EN


class LeadError(ValueError):
    """Lead rejected; message names the field, safe to show the visitor."""


def _str(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def validate_lead(payload: object) -> dict[str, Any]:
    """Validate a raw POST body; return the cleaned lead or raise."""
    if not isinstance(payload, dict):
        raise LeadError("request must be a JSON object")
    if payload.get("website"):
        # Honeypot: bots fill it. Generic message gives no oracle.
        raise LeadError("request rejected")
    title = _str(payload.get("title"))
    name = _str(payload.get("name"))
    email = _str(payload.get("email"))
    goal = _str(payload.get("goal"))
    budget = _str(payload.get("budget"))
    phone = _str(payload.get("phone"))
    company = _str(payload.get("company"))
    problem = _str(payload.get("problem"))
    language = _str(payload.get("language")) or "pl"
    if not title:
        raise LeadError("title: required")
    if not name:
        raise LeadError("name: required")
    if not EMAIL_RE.match(email):
        raise LeadError("email: invalid")
    if not goal:
        raise LeadError("goal: required")
    if budget not in BUDGETS:
        raise LeadError("budget: pick a listed range")
    if phone and not PHONE_RE.match(phone):
        raise LeadError("phone: use international format (+48...)")
    if language not in ("pl", "en"):
        raise LeadError("language: pl or en")
    return {
        "title": title[:200],
        "name": name[:200],
        "email": email[:254],
        "company": company[:200],
        "phone": phone,
        "goal": goal[:2000],
        "problem": problem[:2000],
        "budget": budget,
        "language": language,
    }


def check_rate_limit(counters: MutableMapping[str, list[float]], key: str, now: float) -> bool:
    """Sliding-window gate; True means admit (and record the hit)."""
    hits = [hit for hit in counters.get(key, []) if now - hit < RATE_WINDOW_SECONDS]
    if len(hits) >= RATE_LIMIT_PER_HOUR:
        counters[key] = hits
        return False
    hits.append(now)
    counters[key] = hits
    return True


def build_lead_id(now: datetime) -> str:
    """Reference number: BL-YYYYMMDD-xxxx (unguessable suffix)."""
    return f"BL-{now.strftime('%Y%m%d')}-{secrets.token_hex(2).upper()}"


def render_notification(record: dict[str, Any]) -> tuple[str, str]:
    """Mailbox subject + plain-text body for one lead record."""
    subject = f"[BeskidLogic] Zapytanie {record['lead_id']}: {record['title']}"
    lines = [
        f"Lead: {record['lead_id']} ({record['received_at']})",
        f"Od: {record['name']} <{record['email']}>",
        f"Firma: {record.get('company') or '-'}",
        f"Telefon: {record.get('phone') or '-'}",
        f"Budzet: {record['budget']} (jezyk: {record['language']})",
        "",
        "Cel:",
        str(record.get("goal") or ""),
        "",
        "Problem:",
        str(record.get("problem") or "-"),
    ]
    return subject, "\n".join(lines)


def submit_lead(
    payload: object,
    *,
    forward: Callable[[dict[str, Any], str, str], None],
    log: Callable[[dict[str, Any]], None],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate, forward to mailbox, append to log; return the receipt.

    Forward runs before log; a transport failure raises (the visitor
    retries or falls back to download-JSON) — leads are never silently
    dropped. Returns ``{"lead_id", "received_at"}`` only (no PII echo).
    """
    cleaned = validate_lead(payload)
    moment = now or datetime.now(UTC)
    record = {
        **cleaned,
        "lead_id": build_lead_id(moment),
        "received_at": moment.isoformat(timespec="seconds"),
    }
    subject, body = render_notification(record)
    forward(record, subject, body)
    log(record)
    return {"lead_id": record["lead_id"], "received_at": record["received_at"]}
