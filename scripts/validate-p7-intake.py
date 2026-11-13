#!/usr/bin/env python3
"""Validate a P7 intake file against schema.json plus semantic rules.

Stdlib only (no jsonschema dependency): structural checks mirror
company-site/intake/schema.json; semantic checks implement proposal
rules 8-13 plus the 30-day expiry. Prints
{"valid": bool, "errors": [...], "warnings": [...]} as JSON.

Exit codes: 0 valid (warnings allowed), 1 invalid, 2 usage/IO error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

MAX_BYTES = 32 * 1024
EXPIRY_DAYS = 30

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")
PROJECT_ID_RE = re.compile(r"^[a-z0-9-]{8,64}$")
CREATED_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SECRET_RES = (
    re.compile(r"(?i)(api[_-]?key|password|secret|token)\s*[:=]"),
    re.compile(r"-----BEGIN.*PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9]{8,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{8,}"),
)
FREE_TEXT_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
FREE_TEXT_PHONE_RE = re.compile(r"\+\d{8,15}")
FILLER_GOALS = frozenset({"i want a website", "i want an app", "i need a website"})
VERBS = frozenset(
    "works working delivers deliver shows show loads load passes pass completes "
    "complete renders render sends send displays display achieves achieve meets "
    "meet supports support includes include runs run opens open saves save "
    "exports export dziala wysyla pokazuje laduje przechodzi zapisuje".split()
)
METRIC_RE = re.compile(r"\d")

REQUIRED = {
    "format_version": str,
    "project_id": str,
    "created_at": str,
    "capture_method": str,
    "goal_summary": str,
    "target_users": list,
    "success_criteria": list,
    "deliverable_type": str,
    "features_in": list,
    "features_out": list,
    "timeline": dict,
    "budget_range": str,
    "client_contact": dict,
}
OPTIONAL = {
    "parent_id": (str, type(None)),
    "problem_statement": str,
    "integrations": list,
    "tech_constraints": list,
    "non_functional": list,
    "billing_model": str,
    "marketing_goals": list,
    "preferred_language": str,
}
ENUMS = {
    "capture_method": {"chatbot", "human", "import"},
    "deliverable_type": {"website", "web_app", "landing_page", "ecommerce", "other"},
    "budget_range": {"<2k", "2-5k", "5-15k", "15k+", "undisclosed"},
    "billing_model": {"fixed", "time_materials", "retainer", "unsure"},
    "preferred_language": {"pl", "en", "other"},
}


def _str_list(
    value: object, *, min_items: int, max_items: int, min_len: int, max_len: int
) -> str | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return "must be a string list"
    if not min_items <= len(value) <= max_items:
        return f"must hold {min_items}-{max_items} items"
    for item in value:
        if not min_len <= len(item) <= max_len:
            return f"item length must be {min_len}-{max_len} chars"
    return None


def _clean_text(value: str) -> bool:
    return value == value.strip() and not any(ord(char) < 32 for char in value)


def _free_text_fields(doc: dict) -> list[str]:
    texts: list[str] = []
    for key in ("goal_summary", "problem_statement"):
        if isinstance(doc.get(key), str):
            texts.append(doc[key])
    for key in (
        "target_users",
        "success_criteria",
        "features_in",
        "features_out",
        "tech_constraints",
        "non_functional",
        "marketing_goals",
    ):
        texts.extend(item for item in doc.get(key, []) if isinstance(item, str))
    for entry in doc.get("integrations", []):
        if isinstance(entry, dict):
            texts.extend(str(entry.get(k, "")) for k in ("name", "purpose"))
    contact = doc.get("client_contact", {})
    if isinstance(contact, dict):
        texts.extend(str(contact.get(k, "")) for k in ("name", "company"))
    return texts


def validate_file(path: Path, *, as_of: datetime | None = None) -> dict:
    """Validate one intake file; returns {valid, errors, warnings}."""
    errors: list[str] = []
    warnings: list[str] = []
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return {"valid": False, "errors": [f"unreadable: {exc}"], "warnings": []}
    if len(raw) > MAX_BYTES:
        errors.append(f"file exceeds {MAX_BYTES} bytes")
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        return {"valid": False, "errors": [f"not UTF-8 JSON: {exc}"], "warnings": []}
    if not isinstance(doc, dict):
        return {"valid": False, "errors": ["top level must be an object"], "warnings": []}
    allowed = set(REQUIRED) | set(OPTIONAL)
    for key in doc:
        if key not in allowed:
            errors.append(f"extra top-level key: {key}")
    for key, kind in REQUIRED.items():
        if key not in doc:
            errors.append(f"missing required field: {key}")
        elif not isinstance(doc[key], kind):
            errors.append(f"{key} must be {kind.__name__}")
    for key, kinds in OPTIONAL.items():
        if key in doc and not isinstance(doc[key], kinds):
            errors.append(f"{key} has wrong type")
    if errors:
        return {"valid": False, "errors": errors, "warnings": warnings}

    if doc["format_version"] != "1.0.0":
        errors.append('format_version must be "1.0.0"')
    if not PROJECT_ID_RE.match(doc["project_id"]):
        errors.append("project_id must match ^[a-z0-9-]{8,64}$")
    created: datetime | None = None
    if not CREATED_RE.match(doc["created_at"]):
        errors.append("created_at must be RFC 3339 UTC (YYYY-MM-DDTHH:MM:SSZ)")
    else:
        try:
            created = datetime.strptime(doc["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        except ValueError:
            errors.append("created_at is not a real UTC timestamp")
    for key, values in ENUMS.items():
        if key in doc and doc[key] not in values:
            errors.append(f"{key} must be one of {sorted(values)}")

    checks = [
        ("target_users", 1, 5, 2, 60),
        ("success_criteria", 1, 5, 10, 120),
        ("features_in", 1, 15, 5, 120),
        ("features_out", 0, 10, 1, 120),
        ("tech_constraints", 0, 5, 1, 120),
        ("non_functional", 0, 5, 1, 120),
        ("marketing_goals", 0, 5, 1, 120),
    ]
    for key, lo_n, hi_n, lo_c, hi_c in checks:
        if key in doc:
            failed = _str_list(doc[key], min_items=lo_n, max_items=hi_n, min_len=lo_c, max_len=hi_c)
            if failed:
                errors.append(f"{key} {failed}")
    for bound, key, lo, hi in (
        ("goal_summary", "goal_summary", 20, 280),
        ("problem_statement", "problem_statement", 0, 600),
    ):
        if key in doc and not lo <= len(doc[key]) <= hi:
            errors.append(f"{bound} length must be {lo}-{hi} chars")

    for entry in doc.get("integrations", []):
        if not isinstance(entry, dict) or set(entry) != {"name", "purpose"}:
            errors.append("integrations entries must be {name, purpose} objects")
            break
        if not isinstance(entry["name"], str) or not isinstance(entry["purpose"], str):
            errors.append("integration name/purpose must be strings")
            break
        if not 2 <= len(entry["name"]) <= 40 or not 5 <= len(entry["purpose"]) <= 100:
            errors.append("integration name 2-40 chars, purpose 5-100 chars")
    timeline = doc["timeline"]
    if set(timeline) != {"deadline", "urgency"}:
        errors.append("timeline must be exactly {deadline, urgency}")
    else:
        deadline_raw = timeline["deadline"]
        if deadline_raw is not None and (
            not isinstance(deadline_raw, str) or not DATE_RE.match(deadline_raw)
        ):
            errors.append("timeline.deadline must be YYYY-MM-DD or null")
        if timeline["urgency"] not in {"flexible", "dated", "urgent"}:
            errors.append("timeline.urgency must be flexible/dated/urgent")
    contact = doc["client_contact"]
    if set(contact) - {"name", "email", "company", "phone"}:
        errors.append("client_contact allows only name/email/company/phone")
    elif not all(
        isinstance(contact.get(key, ""), str) for key in ("name", "email", "company", "phone")
    ):
        errors.append("client_contact fields must be strings")
    elif not 2 <= len(contact.get("name", "")) <= 80:
        errors.append("client_contact.name must be 2-80 chars")
    elif not EMAIL_RE.match(contact.get("email", "")):
        errors.append("client_contact.email is not an email address")
    elif len(contact.get("company", "")) > 80:
        errors.append("client_contact.company must be <= 80 chars")
    elif not PHONE_RE.match(contact.get("phone", "")):
        errors.append("client_contact.phone must be E.164 or empty")
    for text in _free_text_fields(doc):
        if text and not _clean_text(text):
            errors.append("free-text fields must be trimmed, no control chars")
            break

    overlap = set(doc["features_in"]) & set(doc["features_out"])
    if overlap:
        errors.append(f"scope overlap in features_in/out: {sorted(overlap)[:3]}")
    if doc["goal_summary"].strip().lower() in FILLER_GOALS:
        errors.append("goal_summary is generic filler; expand before saving")
    deadline_dt: datetime | None = None
    if isinstance(timeline.get("deadline"), str) and DATE_RE.match(timeline["deadline"]):
        try:
            deadline_dt = datetime.strptime(timeline["deadline"], "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            errors.append("timeline.deadline is not a real date")
    if created is not None and deadline_dt is not None:
        if deadline_dt < created + timedelta(hours=48):
            errors.append("deadline must be >= created_at + 48h")
        if timeline["urgency"] == "urgent" and deadline_dt > created + timedelta(days=90):
            errors.append("urgent with deadline >90 days out is contradictory")
    blob = raw.decode("utf-8", errors="replace")
    if any(pattern.search(blob) for pattern in SECRET_RES):
        errors.append("secret-like content; strip credentials before saving")
    if created is not None:
        now = as_of or datetime.now(UTC)
        if now > created + timedelta(days=EXPIRY_DAYS):
            errors.append(
                f"file expired ({EXPIRY_DAYS}d without approval); re-confirm contact + timeline"
            )

    weak = [
        item
        for item in doc["success_criteria"]
        if not METRIC_RE.search(item)
        and not any(word.strip(".,;:!?") in VERBS for word in item.lower().split())
    ]
    if weak:
        warnings.append(f"success_criteria may be untestable: {weak[:2]}")
    for text in _free_text_fields(doc):
        if FREE_TEXT_EMAIL_RE.search(text or "") or FREE_TEXT_PHONE_RE.search(text or ""):
            warnings.append("free text contains email/phone; flagged for owner review")
            break
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a P7 intake file.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--as-of", default=None, help="YYYY-MM-DD to pin expiry checks")
    args = parser.parse_args(argv)
    as_of = None
    if args.as_of is not None:
        try:
            as_of = datetime.strptime(args.as_of, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            print("error: --as-of must be YYYY-MM-DD", file=sys.stderr)
            return 2
    result = validate_file(args.path, as_of=as_of)
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
