"""Draft-only Polish invoice helper for the company site.

Builds a validated invoice DRAFT from structured input: NIP checksum,
PL VAT rates, Decimal-exact totals, series numbering, and a KSeF-ready
field export. A draft becomes sendable only through an explicit
hash-chained founder review; any mutation invalidates the approval.

Deliberately NOT in slice 1: KSeF submission (needs certs + the
accountant-verified template), sending, or payment tracking. See
docs/plans/accountant-investigation.md — one paid accountant hour is
due before the first real invoice.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

VAT_RATES = ("23", "8", "5", "0", "zw", "np")
NIP_WEIGHTS = (6, 5, 7, 2, 3, 4, 5, 6, 7)
NUMBER_RE = re.compile(r"^[A-Z0-9]{1,12}/[0-9]{4}/[0-9]{2}/[0-9]{1,6}$")


@dataclass(frozen=True)
class Party:
    name: str
    nip: str
    street: str
    city: str
    postal: str


@dataclass(frozen=True)
class InvoiceLine:
    description: str
    quantity: Decimal
    unit_net: Decimal
    vat_rate: str


@dataclass(frozen=True)
class InvoiceDraft:
    number: str
    issue_date: date
    seller: Party
    buyer: Party
    lines: tuple[InvoiceLine, ...]
    currency: str = "PLN"
    notes: str = ""


@dataclass(frozen=True)
class DraftApproval:
    draft_hash: str
    reviewer: str
    reviewed_at: str


def normalize_nip(nip: str) -> str:
    """Strip separators; the canonical NIP is 10 bare digits."""
    return re.sub(r"[\s\-]", "", nip or "")


def valid_nip(nip: str) -> bool:
    """PL NIP checksum: weighted sum mod 11 must equal the last digit."""
    digits = normalize_nip(nip)
    if not re.fullmatch(r"[0-9]{10}", digits):
        return False
    total = sum(int(d) * w for d, w in zip(digits[:9], NIP_WEIGHTS, strict=True))
    check = total % 11
    return check < 10 and check == int(digits[9])


def _dec(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label} must be a number") from None
    if result.is_nan():
        raise ValueError(f"{label} must be a number")
    return result


def line_totals(line: InvoiceLine) -> dict[str, Decimal]:
    """Net/VAT/gross for one line, exact to the grosz."""
    if line.vat_rate not in VAT_RATES:
        raise ValueError(f"unknown VAT rate: {line.vat_rate!r}")
    if line.quantity <= 0:
        raise ValueError("quantity must be positive")
    if line.unit_net < 0:
        raise ValueError("unit_net must be non-negative")
    net = (line.quantity * line.unit_net).quantize(Decimal("0.01"))
    if line.vat_rate in ("zw", "np", "0"):
        vat = Decimal("0.00")
    else:
        vat = (net * Decimal(line.vat_rate) / 100).quantize(Decimal("0.01"))
    return {"net": net, "vat": vat, "gross": net + vat}


def draft_from_dict(raw: dict) -> InvoiceDraft:
    """Validate structured input into an immutable draft.

    Raises ValueError naming the first problem found.
    """
    if not isinstance(raw, dict):
        raise ValueError("draft input must be an object")
    number = str(raw.get("number", "")).strip()
    if not NUMBER_RE.match(number):
        raise ValueError("number must look like FV/2026/11/7 (SERIES/YYYY/MM/N)")
    try:
        issued = date.fromisoformat(str(raw.get("issue_date", "")))
    except ValueError:
        raise ValueError("issue_date must be ISO YYYY-MM-DD") from None
    seller = _party(raw.get("seller"), "seller")
    buyer = _party(raw.get("buyer"), "buyer")
    lines_raw = raw.get("lines")
    if not isinstance(lines_raw, list) or not lines_raw:
        raise ValueError("at least one line is required")
    lines = tuple(_line(item, index) for index, item in enumerate(lines_raw, 1))
    currency = str(raw.get("currency", "PLN")).strip().upper()
    if currency != "PLN":
        raise ValueError("slice 1 supports PLN only")
    notes = str(raw.get("notes", ""))
    return InvoiceDraft(
        number=number,
        issue_date=issued,
        seller=seller,
        buyer=buyer,
        lines=lines,
        currency=currency,
        notes=notes,
    )


def _party(raw: object, label: str) -> Party:
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object")
    name = str(raw.get("name", "")).strip()
    if not name:
        raise ValueError(f"{label}.name is required")
    nip = normalize_nip(str(raw.get("nip", "")))
    if not valid_nip(nip):
        raise ValueError(f"{label}.nip is not a valid PL NIP")
    street = str(raw.get("street", "")).strip()
    city = str(raw.get("city", "")).strip()
    postal = str(raw.get("postal", "")).strip()
    if not street or not city or not postal:
        raise ValueError(f"{label} needs street, city and postal")
    return Party(name=name, nip=nip, street=street, city=city, postal=postal)


def _line(raw: object, index: int) -> InvoiceLine:
    if not isinstance(raw, dict):
        raise ValueError(f"line {index} must be an object")
    description = str(raw.get("description", "")).strip()
    if not description:
        raise ValueError(f"line {index} needs a description")
    quantity = _dec(raw.get("quantity"), f"line {index} quantity")
    unit_net = _dec(raw.get("unit_net"), f"line {index} unit_net")
    vat_rate = str(raw.get("vat_rate", "")).strip()
    line = InvoiceLine(
        description=description, quantity=quantity, unit_net=unit_net, vat_rate=vat_rate
    )
    line_totals(line)  # validate rates and signs now
    return line


def draft_totals(draft: InvoiceDraft) -> dict[str, Decimal]:
    """Summed net/VAT/gross across lines."""
    total = {"net": Decimal("0.00"), "vat": Decimal("0.00"), "gross": Decimal("0.00")}
    for line in draft.lines:
        parts = line_totals(line)
        for key in total:
            total[key] += parts[key]
    return total


def canonical_json(draft: InvoiceDraft) -> str:
    """Stable serialization for hashing and review."""
    return json.dumps(
        {
            "number": draft.number,
            "issue_date": draft.issue_date.isoformat(),
            "seller": _party_dict(draft.seller),
            "buyer": _party_dict(draft.buyer),
            "lines": [
                {
                    "description": line.description,
                    "quantity": str(line.quantity),
                    "unit_net": str(line.unit_net),
                    "vat_rate": line.vat_rate,
                }
                for line in draft.lines
            ],
            "currency": draft.currency,
            "notes": draft.notes,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _party_dict(party: Party) -> dict:
    return {
        "name": party.name,
        "nip": party.nip,
        "street": party.street,
        "city": party.city,
        "postal": party.postal,
    }


def draft_hash(draft: InvoiceDraft) -> str:
    return hashlib.sha256(canonical_json(draft).encode("utf-8")).hexdigest()


def review_draft(draft: InvoiceDraft, reviewer: str, reviewed_at: str) -> DraftApproval:
    """Founder review: approves THIS exact draft content only."""
    if not reviewer.strip():
        raise ValueError("reviewer is required")
    return DraftApproval(
        draft_hash=draft_hash(draft), reviewer=reviewer.strip(), reviewed_at=reviewed_at
    )


def approval_valid(draft: InvoiceDraft, approval: DraftApproval) -> bool:
    """True only when the draft is byte-identical to the reviewed one."""
    return approval.draft_hash == draft_hash(draft)


def ksef_ready_dict(draft: InvoiceDraft) -> dict:
    """KSeF-shaped field export (structure preview, not a submission).

    Covers the FA header + parties + lines subset our drafts always
    carry; the certified KSeF XML mapping and API submission are a
    later slice behind the accountant-verified template.
    """
    totals = draft_totals(draft)
    return {
        "fa_type": "draft",
        "number": draft.number,
        "issue_date": draft.issue_date.isoformat(),
        "currency": draft.currency,
        "seller": _party_dict(draft.seller),
        "buyer": _party_dict(draft.buyer),
        "lines": [
            {
                "no": index,
                "description": line.description,
                "quantity": str(line.quantity),
                "unit_net": str(line.unit_net),
                "vat_rate": line.vat_rate,
                **{k: str(v) for k, v in line_totals(line).items()},
            }
            for index, line in enumerate(draft.lines, 1)
        ],
        "totals": {key: str(value) for key, value in totals.items()},
        "notes": draft.notes,
    }


def render_text(draft: InvoiceDraft) -> str:
    """Human-readable draft for founder review (not a legal rendering)."""
    totals = draft_totals(draft)
    out = [
        f"FAKTURA (SZKIC, nie do wysyłki) {draft.number} z {draft.issue_date.isoformat()}",
        f"Sprzedawca: {draft.seller.name}, NIP {draft.seller.nip}",
        f"Nabywca: {draft.buyer.name}, NIP {draft.buyer.nip}",
        "",
    ]
    for index, line in enumerate(draft.lines, 1):
        parts = line_totals(line)
        out.append(
            f"{index}. {line.description} — {line.quantity} x {line.unit_net} "
            f"netto, VAT {line.vat_rate}: brutto {parts['gross']}"
        )
    out += [
        "",
        f"Razem netto {totals['net']}, VAT {totals['vat']}, brutto {totals['gross']} {draft.currency}.",
    ]
    if draft.notes:
        out.append(f"Uwagi: {draft.notes}")
    return "\n".join(out)
