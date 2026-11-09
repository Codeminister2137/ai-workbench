"""P7 client-intake: validate chatbot briefs, approve into draft plans.

Implements ``docs/plans/p7-project-file-format-proposal.md`` v1.0.0: intake
files live in ``p7-projects/`` (gitignored: client PII), validate against
the closed schema plus semantic actionability rules, and the owner
approves valid files into ``proposed`` dashboard plans. Approval moves
the file to ``p7-projects/approved/`` (immutability); nothing
auto-executes and no credits are spent. Expiry is 30 days.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

INTAKE_DIRNAME = "p7-projects"
APPROVED_DIRNAME = "approved"
MAX_FILE_BYTES = 32 * 1024
EXPIRY_DAYS = 30

FORMAT_VERSION = "1.0.0"
DELIVERABLE_TYPES = {"website", "web_app", "landing_page", "ecommerce", "other"}
CAPTURE_METHODS = {"chatbot", "human", "import"}
URGENCIES = {"flexible", "dated", "urgent"}
BUDGET_RANGES = {"<2k", "2-5k", "5-15k", "15k+", "undisclosed"}
BILLING_MODELS = {"fixed", "time_materials", "retainer", "unsure"}
LANGUAGES = {"pl", "en", "other"}

REQUIRED_TOP = {
    "format_version",
    "project_id",
    "created_at",
    "capture_method",
    "goal_summary",
    "target_users",
    "success_criteria",
    "deliverable_type",
    "features_in",
    "features_out",
    "timeline",
    "budget_range",
    "client_contact",
}
OPTIONAL_TOP = {
    "parent_id",
    "problem_statement",
    "integrations",
    "tech_constraints",
    "non_functional",
    "billing_model",
    "preferred_language",
    "marketing_goals",
}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
SECRET_RES = (
    re.compile(r"(?i)(api[_-]?key|password|secret|token)\s*[:=]"),
    re.compile(r"-----BEGIN.*PRIVATE KEY-----"),
    re.compile(r"\b(sk-|ghp_)[A-Za-z0-9]{8,}"),
)
PII_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+|\+[1-9]\d{7,14}")
VERB_STEMS = (
    "add",
    "build",
    "creat",
    "deliver",
    "deploy",
    "edit",
    "embed",
    "enabl",
    "fix",
    "implement",
    "improv",
    "includ",
    "integrat",
    "launch",
    "migrat",
    "provid",
    "publish",
    "redesign",
    "render",
    "send",
    "ship",
    "show",
    "submit",
    "support",
    "updat",
    "work",
)
GENERIC_GOALS = {"i want a website", "i need a website", "i want an app", "i need an app"}


def _is_str(value: object, lo: int, hi: int) -> bool:
    return (
        isinstance(value, str)
        and lo <= len(value) <= hi
        and value == value.strip()
        and all(ord(char) >= 32 or char in "\n\t" for char in value)
    )


def _is_str_list(value: object, items_lo: int, items_hi: int, lo: int, hi: int) -> bool:
    return (
        isinstance(value, list)
        and items_lo <= len(value) <= items_hi
        and all(_is_str(item, lo, hi) for item in value)
    )


def _secret_hit(payload: dict) -> bool:
    blob = json.dumps(payload, ensure_ascii=False)
    return any(pattern.search(blob) for pattern in SECRET_RES)


def _pii_hit(text: str) -> bool:
    return bool(PII_RE.search(text))


def validate_p7(payload: object, *, raw_bytes: int = 0) -> dict[str, Any]:
    """Validate one P7 brief; returns {valid, errors, warnings}."""
    errors: list[str] = []
    warnings: list[str] = []
    if raw_bytes > MAX_FILE_BYTES:
        errors.append("File exceeds 32 KB")
    if not isinstance(payload, dict):
        return {
            "valid": False,
            "errors": errors + ["File must be a JSON object"],
            "warnings": warnings,
        }
    keys = set(payload)
    missing = REQUIRED_TOP - keys
    if missing:
        errors.append("Missing required fields: " + ", ".join(sorted(missing)))
    extra = keys - REQUIRED_TOP - OPTIONAL_TOP
    if extra:
        errors.append("Unknown top-level keys: " + ", ".join(sorted(extra)))
    if payload.get("format_version") != FORMAT_VERSION:
        errors.append('format_version must be "1.0.0"')
    project_id = payload.get("project_id", "")
    if not isinstance(project_id, str) or not re.fullmatch(r"[a-z0-9-]{8,64}", project_id):
        errors.append("project_id must match ^[a-z0-9-]{8,64}$")
    created_at = payload.get("created_at", "")
    created: datetime | None = None
    try:
        created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if created.tzinfo is None:
            raise ValueError("naive")
    except ValueError:
        errors.append("created_at must be an RFC 3339 UTC timestamp")
        created = None
    if payload.get("capture_method") not in CAPTURE_METHODS:
        errors.append("capture_method must be one of chatbot/human/import")
    parent_id = payload.get("parent_id")
    if parent_id is not None and not isinstance(parent_id, str):
        errors.append("parent_id must be a string or null")
    goal = payload.get("goal_summary", "")
    if not _is_str(goal, 20, 280):
        errors.append("goal_summary requires 20-280 trimmed characters")
    elif goal.strip().lower() in GENERIC_GOALS:
        errors.append("goal_summary is generic filler; expand before saving")
    if not _is_str_list(payload.get("target_users"), 1, 5, 2, 60):
        errors.append("target_users requires 1-5 items of 2-60 chars")
    criteria = payload.get("success_criteria")
    if not _is_str_list(criteria, 1, 5, 10, 120):
        errors.append("success_criteria requires 1-5 items of 10-120 chars")
    elif isinstance(criteria, list):
        for item in criteria:
            words = str(item).lower().split()
            actionable = any(char.isdigit() for char in str(item)) or any(
                word.startswith(stem) for word in words for stem in VERB_STEMS
            )
            if not actionable:
                warnings.append(f"success_criteria may be untestable: {item!r}")
                break
    if payload.get("deliverable_type") not in DELIVERABLE_TYPES:
        errors.append("deliverable_type is not a known type")
    features_in = payload.get("features_in")
    features_out = payload.get("features_out")
    if not _is_str_list(features_in, 1, 15, 5, 120):
        errors.append("features_in requires 1-15 items of 5-120 chars")
    if (
        not isinstance(features_out, list)
        or len(features_out) > 10
        or not all(_is_str(item, 5, 120) for item in features_out)
    ):
        errors.append("features_out allows 0-10 items of 5-120 chars")
    if (
        isinstance(features_in, list)
        and isinstance(features_out, list)
        and set(features_in) & set(features_out)
    ):
        errors.append("features_in and features_out overlap")
    integrations = payload.get("integrations", [])
    if (
        not isinstance(integrations, list)
        or len(integrations) > 8
        or not all(
            isinstance(item, dict)
            and _is_str(item.get("name", ""), 2, 40)
            and _is_str(item.get("purpose", ""), 5, 100)
            for item in integrations
        )
    ):
        errors.append("integrations allows 0-8 {name, purpose} items")
    timeline = payload.get("timeline")
    deadline: str | None = None
    urgency: str | None = None
    if isinstance(timeline, dict):
        deadline = timeline.get("deadline")
        urgency = timeline.get("urgency")
    deadline_ok = deadline is None or (
        isinstance(deadline, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", deadline) is not None
    )
    try:
        deadline_date = (
            datetime.strptime(deadline, "%Y-%m-%d").replace(tzinfo=UTC)
            if isinstance(deadline, str) and deadline_ok
            else None
        )
    except ValueError:
        deadline_date = None
        deadline_ok = False
    if not deadline_ok or urgency not in URGENCIES:
        errors.append("timeline requires {deadline: YYYY-MM-DD|null, urgency}")
    elif created is not None and deadline_date is not None:
        delta_hours = (deadline_date - created).total_seconds() / 3600
        if delta_hours < 48:
            errors.append("timeline deadline is sooner than created_at + 48h")
        if urgency == "urgent" and delta_hours > 90 * 24:
            errors.append("urgent timeline contradicts a >90d deadline")
    for key, hi in (("tech_constraints", 5), ("non_functional", 5), ("marketing_goals", 5)):
        items = payload.get(key, [])
        if (
            not isinstance(items, list)
            or len(items) > hi
            or not all(isinstance(item, str) for item in items)
        ):
            errors.append(f"{key} allows 0-{hi} strings")
    if payload.get("budget_range") not in BUDGET_RANGES:
        errors.append("budget_range is not a known bucket")
    billing = payload.get("billing_model")
    if billing is not None and billing not in BILLING_MODELS:
        errors.append("billing_model is not a known model")
    contact = payload.get("client_contact")
    if not isinstance(contact, dict):
        errors.append("client_contact must be an object")
    else:
        extra_contact = set(contact) - {"name", "email", "company", "phone"}
        if extra_contact:
            warnings.append(
                "client_contact carries extra fields: " + ", ".join(sorted(extra_contact))
            )
        if not _is_str(contact.get("name", ""), 2, 80):
            errors.append("client_contact.name requires 2-80 characters")
        if not isinstance(contact.get("email"), str) or not EMAIL_RE.match(contact["email"]):
            errors.append("client_contact.email is invalid")
        company = contact.get("company", "")
        if not isinstance(company, str) or len(company) > 80:
            errors.append("client_contact.company allows up to 80 characters")
        phone = contact.get("phone", "")
        if not isinstance(phone, str) or (phone != "" and not E164_RE.match(phone)):
            errors.append("client_contact.phone must be E.164 or empty")
    language = payload.get("preferred_language", "pl")
    if language not in LANGUAGES:
        errors.append("preferred_language is not a known language")
    problem = payload.get("problem_statement", "")
    if problem != "" and not _is_str(problem, 1, 600):
        errors.append("problem_statement allows up to 600 characters")
    if _secret_hit(payload):
        errors.append("secret-like pattern detected; strip secrets before saving")
    free_text = " ".join(
        str(payload.get(key, "")) for key in ("goal_summary", "problem_statement")
    ) + " ".join(
        str(item)
        for key in ("features_in", "features_out")
        for item in (payload.get(key) or [])
        if isinstance(item, str)
    )
    if _pii_hit(free_text):
        warnings.append("free-text fields contain email/phone-like patterns")
    if created is not None:
        age_days = (datetime.now(UTC) - created).total_seconds() / 86400
        if age_days > EXPIRY_DAYS:
            errors.append(
                "brief expired (>30 days without approval); re-confirm contact and timeline"
            )
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def intake_dir(repo_root: Path) -> Path:
    """Return the intake directory (created on list/approve)."""
    path = Path(repo_root) / INTAKE_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_name(name: str) -> bool:
    return (
        isinstance(name, str)
        and name.endswith(".json")
        and "/" not in name
        and "\\" not in name
        and name not in (".json", "..json")
        and len(name.encode("utf-8")) <= 128
    )


def list_intake(repo_root: Path) -> list[dict[str, Any]]:
    """List intake files with validation verdicts, oldest first."""
    directory = intake_dir(repo_root)
    entries: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            raw = path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError, UnicodeError) as exc:
            entries.append(
                {
                    "name": path.name,
                    "valid": False,
                    "errors": [f"Unreadable file: {exc}"],
                    "warnings": [],
                    "summary": "",
                }
            )
            continue
        verdict = validate_p7(payload, raw_bytes=len(raw))
        summary = payload.get("goal_summary", "") if isinstance(payload, dict) else ""
        entries.append(
            {
                "name": path.name,
                "valid": verdict["valid"],
                "errors": verdict["errors"],
                "warnings": verdict["warnings"],
                "summary": summary if isinstance(summary, str) else "",
                "project_id": payload.get("project_id", "") if isinstance(payload, dict) else "",
            }
        )
    return entries


def render_brief(payload: dict) -> str:
    """Render an approved brief as plan-body markdown (read-only input)."""
    contact = payload.get("client_contact", {}) or {}
    lines = [
        f"# Intake brief: {payload.get('project_id', '?')}",
        "",
        f"Goal: {payload.get('goal_summary', '')}",
        f"Deliverable: {payload.get('deliverable_type', '')} | Budget: {payload.get('budget_range', '')} | Urgency: {(payload.get('timeline') or {}).get('urgency', '')}",
        f"Contact: {contact.get('name', '')} <{contact.get('email', '')}> ({contact.get('company', '')})",
        "",
        "## In scope",
        *[f"- {item}" for item in payload.get("features_in", [])],
        "",
        "## Out of scope",
        *[f"- {item}" for item in payload.get("features_out", [])],
        "",
        "## Success criteria",
        *[f"- {item}" for item in payload.get("success_criteria", [])],
        "",
        "## Marketing goals",
        *[f"- {item}" for item in payload.get("marketing_goals", [])],
        "",
        "## Integrations",
        *[
            f"- {item.get('name', '?')}: {item.get('purpose', '')}"
            for item in payload.get("integrations", [])
            if isinstance(item, dict)
        ],
    ]
    return "\n".join(lines)


def approve_intake(repo_root: Path, data_dir: Path, name: str) -> dict[str, Any]:
    """Approve a valid intake file into a proposed plan (moves file to approved/).

    Raises ``ValueError`` for unknown/invalid files. Returns the plan record.
    """
    from dashboard_stores import DashboardStores

    if not _safe_name(name):
        raise ValueError("Unknown intake file")
    path = intake_dir(repo_root) / name
    if not path.is_file():
        raise ValueError("Unknown intake file")
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise ValueError(f"Unreadable intake file: {exc}") from exc
    verdict = validate_p7(payload, raw_bytes=len(raw))
    if not verdict["valid"]:
        raise ValueError("Intake file is not valid: " + "; ".join(verdict["errors"][:3]))
    plan_id = str(payload["project_id"])
    record = {
        "id": plan_id,
        "title": f"Intake: {payload.get('goal_summary', plan_id)[:80]}",
        "status": "proposed",
        "body": render_brief(payload),
        "source": f"{INTAKE_DIRNAME}/{name}",
        "intake": {"name": name, "warnings": verdict["warnings"]},
        "updated_at_utc": datetime.now(UTC).isoformat(),
    }
    DashboardStores(Path(data_dir)).plans.put(plan_id, record)
    approved_dir = intake_dir(repo_root) / APPROVED_DIRNAME
    approved_dir.mkdir(parents=True, exist_ok=True)
    path.replace(approved_dir / name)
    return record
