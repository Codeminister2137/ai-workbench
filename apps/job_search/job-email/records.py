"""Append-only JSONL persistence for structured application records.

Each line of the ledger is one self-contained JSON object describing a
prepared, approved, sent, or failed application package: vacancy/contact
identifiers, selected CV/message versions, timestamps, and the send outcome.
The ledger is a local file only; this module performs no network or cloud
access and requires no third-party dependencies.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from models import ApplicationPackage, ApplicationStatus, SendReceipt, utc_now_iso

DEFAULT_RECORDS_FILE = "application_records.jsonl"
"""Default local ledger name, resolved like the sent-file against the working directory."""


def application_record_to_dict(package: ApplicationPackage) -> dict[str, Any]:
    """Serialize an application package to a JSON-compatible record dict."""
    receipt: dict[str, Any] | None = None
    if package.send_receipt is not None:
        receipt = {
            "success": package.send_receipt.success,
            "recipient": package.send_receipt.recipient,
            "timestamp_utc": package.send_receipt.timestamp_utc,
            "error_message": package.send_receipt.error_message,
            "transport_name": package.send_receipt.transport_name,
        }
    return {
        "application_id": package.application_id,
        "vacancy_ref": package.vacancy_ref,
        "contact_email": package.contact_email,
        "cv_attachment_path": package.cv_attachment_path,
        "subject": package.subject,
        "body": package.body,
        "cv_variant_id": package.cv_variant_id,
        "message_variant_id": package.message_variant_id,
        "status": package.status.value,
        "created_at_utc": package.created_at_utc,
        "approved_at_utc": package.approved_at_utc,
        "approved_by": package.approved_by,
        "approval_notes": package.approval_notes,
        "approved_materials_sha256": package.approved_materials_sha256,
        "send_receipt": receipt,
        "outcome_by": package.outcome_by,
        "outcome_notes": package.outcome_notes,
        "outcome_at_utc": package.outcome_at_utc,
    }


def application_record_from_dict(data: dict[str, Any]) -> ApplicationPackage:
    """Rebuild an application package from a record dict.

    Raises ValueError when a required field is missing or has an invalid
    type or value. Unknown extra fields are ignored for forward compatibility.
    """
    if not isinstance(data, dict):
        raise ValueError("application record must be a JSON object")
    receipt_data = data.get("send_receipt")
    return ApplicationPackage(
        application_id=_require_str(data, "application_id"),
        vacancy_ref=_require_str(data, "vacancy_ref"),
        contact_email=_require_str(data, "contact_email"),
        cv_attachment_path=_require_str(data, "cv_attachment_path"),
        subject=_require_str(data, "subject"),
        body=_require_str(data, "body"),
        cv_variant_id=_require_str(data, "cv_variant_id"),
        message_variant_id=_require_str(data, "message_variant_id"),
        status=_require_status(data),
        created_at_utc=_require_str(data, "created_at_utc"),
        approved_at_utc=_optional_str(data, "approved_at_utc"),
        approved_by=_optional_str(data, "approved_by"),
        approval_notes=_optional_str(data, "approval_notes"),
        approved_materials_sha256=_optional_str(data, "approved_materials_sha256"),
        send_receipt=_parse_receipt(receipt_data),
        outcome_by=_optional_str(data, "outcome_by"),
        outcome_notes=_optional_str(data, "outcome_notes"),
        outcome_at_utc=_optional_str(data, "outcome_at_utc"),
    )


OUTCOME_TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    ApplicationStatus.SENT: frozenset({ApplicationStatus.RESPONDED, ApplicationStatus.REJECTED}),
    ApplicationStatus.RESPONDED: frozenset(
        {ApplicationStatus.INTERVIEW, ApplicationStatus.REJECTED}
    ),
    ApplicationStatus.INTERVIEW: frozenset({ApplicationStatus.OFFER, ApplicationStatus.REJECTED}),
    ApplicationStatus.OFFER: frozenset(),
    ApplicationStatus.REJECTED: frozenset(),
}
"""Legal outcome moves; anything else (incl. pre-send states) is rejected."""

MIN_REPORT_SAMPLE = 5
"""Fewer sent applications than this: counts only, no rates."""


def append_application_record(path: str | Path, package: ApplicationPackage) -> None:
    """Append one record line to the local JSONL ledger.

    Creates missing parent directories. Never rewrites existing lines.
    """
    ledger = Path(path)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(application_record_to_dict(package), ensure_ascii=True, sort_keys=True)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def read_application_records(path: str | Path) -> list[ApplicationPackage]:
    """Read every record from the local JSONL ledger, preserving order.

    A missing ledger reads as zero records. Blank lines are skipped.
    Raises ValueError naming the offending line number when a line holds
    invalid JSON or a malformed record.
    """
    ledger = Path(path)
    if not ledger.exists():
        return []
    records: list[ApplicationPackage] = []
    with ledger.open(encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{ledger}: line {lineno}: invalid JSON: {exc}") from exc
            try:
                records.append(application_record_from_dict(data))
            except ValueError as exc:
                raise ValueError(f"{ledger}: line {lineno}: {exc}") from exc
    return records


def _require_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"field {key!r} must be a string")
    return value


def _optional_str(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"field {key!r} must be a string or null")
    return value


def _require_status(data: dict[str, Any]) -> ApplicationStatus:
    raw = _require_str(data, "status")
    try:
        return ApplicationStatus(raw)
    except ValueError:
        raise ValueError(f"unknown application status: {raw!r}") from None


def _parse_receipt(data: Any) -> SendReceipt | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ValueError("field 'send_receipt' must be an object or null")
    success = data.get("success")
    if not isinstance(success, bool):
        raise ValueError("field 'send_receipt.success' must be a boolean")
    return SendReceipt(
        success=success,
        recipient=_require_str(data, "recipient"),
        timestamp_utc=_require_str(data, "timestamp_utc"),
        error_message=_optional_str(data, "error_message"),
        transport_name=_require_str(data, "transport_name"),
    )


def record_outcome(
    path: str | Path,
    application_id: str,
    status: ApplicationStatus,
    *,
    by: str | None = None,
    notes: str | None = None,
) -> ApplicationPackage:
    """Append an outcome transition for one application (M4).

    Only forward moves from sent-or-later states are legal; anything
    else raises ValueError and writes nothing. Returns the new record.
    """
    latest: dict[str, ApplicationPackage] = {}
    for package in read_application_records(path):
        latest[package.application_id] = package
    current = latest.get(application_id)
    if current is None:
        raise ValueError(f"unknown application: {application_id!r}")
    if status not in OUTCOME_TRANSITIONS.get(current.status, frozenset()):
        raise ValueError(f"illegal outcome move: {current.status.value} -> {status.value}")
    updated = replace(
        current, status=status, outcome_by=by, outcome_notes=notes, outcome_at_utc=utc_now_iso()
    )
    append_application_record(path, updated)
    return updated


def outcomes_report(packages: list[ApplicationPackage]) -> dict[str, Any]:
    """Descriptive outcome counts; rates only with a sufficient sample.

    Deduplicates by application id (latest wins). Below MIN_REPORT_SAMPLE
    sent applications the report carries counts and an insufficient-data
    flag instead of rates — no statistics on tiny samples.
    """
    latest: dict[str, ApplicationPackage] = {}
    for package in packages:
        latest[package.application_id] = package
    by_status: dict[str, int] = {}
    by_variant: dict[str, int] = {}
    for package in latest.values():
        by_status[package.status.value] = by_status.get(package.status.value, 0) + 1
        by_variant[package.cv_variant_id] = by_variant.get(package.cv_variant_id, 0) + 1
    responded = sum(by_status.get(status, 0) for status in ("responded", "interview", "offer"))
    sent_total = sum(
        by_status.get(status, 0)
        for status in ("sent", "responded", "interview", "offer", "rejected")
    )
    report: dict[str, Any] = {
        "applications": len(latest),
        "by_status": by_status,
        "by_variant": by_variant,
        "response_rate": None,
        "insufficient_data": sent_total < MIN_REPORT_SAMPLE,
    }
    if sent_total >= MIN_REPORT_SAMPLE:
        report["response_rate"] = round(responded / sent_total, 3)
    return report
