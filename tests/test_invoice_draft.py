"""Draft-only invoicing: NIP checksum, VAT math, review gate."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "company-site"))

from billing import (
    approval_valid,
    canonical_json,
    draft_from_dict,
    draft_hash,
    draft_totals,
    ksef_ready_dict,
    line_totals,
    render_text,
    review_draft,
    valid_nip,
)


def _party(**over):
    base = {
        "name": "Acme Sp. z o.o.",
        "nip": "5270204778",
        "street": "ul. Testowa 1",
        "city": "Bielsko-Biała",
        "postal": "43-300",
    }
    base.update(over)
    return base


def _draft(**over):
    base = {
        "number": "FV/2026/11/7",
        "issue_date": "2026-11-09",
        "seller": _party(),
        "buyer": _party(name="Klient SA", nip="5260250274"),
        "lines": [
            {
                "description": "Automatyzacja obiegu faktur",
                "quantity": "1",
                "unit_net": "12000.00",
                "vat_rate": "23",
            },
            {
                "description": "Opieka miesięczna",
                "quantity": "2",
                "unit_net": "500.00",
                "vat_rate": "23",
            },
        ],
        "notes": "Płatność 14 dni.",
    }
    base.update(over)
    return base


def test_nip_checksum_accepts_and_rejects() -> None:
    assert valid_nip("5270204778") is True
    assert valid_nip("527-020-47-78") is True
    assert valid_nip("5270204775") is False  # bad check digit
    assert valid_nip("1111111112") is False
    assert valid_nip("123") is False
    assert valid_nip("") is False


def test_vat_math_is_grosz_exact() -> None:
    draft = draft_from_dict(_draft())
    first = line_totals(draft.lines[0])
    assert first == {
        "net": Decimal("12000.00"),
        "vat": Decimal("2760.00"),
        "gross": Decimal("14760.00"),
    }
    totals = draft_totals(draft)
    assert totals == {
        "net": Decimal("13000.00"),
        "vat": Decimal("2990.00"),
        "gross": Decimal("15990.00"),
    }


def test_zw_np_and_zero_carry_no_vat() -> None:
    draft = draft_from_dict(
        _draft(
            lines=[
                {"description": "a", "quantity": "1", "unit_net": "100", "vat_rate": "zw"},
                {"description": "b", "quantity": "1", "unit_net": "100", "vat_rate": "np"},
                {"description": "c", "quantity": "1", "unit_net": "100", "vat_rate": "0"},
            ]
        )
    )
    assert draft_totals(draft)["vat"] == Decimal("0.00")


def test_validation_names_problems() -> None:
    with pytest.raises(ValueError, match="SERIES/YYYY/MM/N"):
        draft_from_dict(_draft(number="nope"))
    with pytest.raises(ValueError, match="seller.nip"):
        draft_from_dict(_draft(seller=_party(nip="1111111112")))
    with pytest.raises(ValueError, match="line 2 needs a description"):
        draft_from_dict(
            _draft(
                lines=[
                    {"description": "ok", "quantity": "1", "unit_net": "1", "vat_rate": "23"},
                    {"description": " ", "quantity": "1", "unit_net": "1", "vat_rate": "23"},
                ]
            )
        )
    with pytest.raises(ValueError, match="unknown VAT rate"):
        draft_from_dict(
            _draft(lines=[{"description": "x", "quantity": "1", "unit_net": "1", "vat_rate": "99"}])
        )
    with pytest.raises(ValueError, match="PLN only"):
        draft_from_dict(_draft(currency="EUR"))


def test_review_gate_breaks_on_mutation() -> None:
    draft = draft_from_dict(_draft())
    approval = review_draft(draft, "Jakub", "2026-11-09T22:00:00+01:00")
    assert approval_valid(draft, approval) is True
    changed = draft_from_dict(_draft(notes="Płatność 30 dni."))
    assert approval_valid(changed, approval) is False
    assert draft_hash(draft) != draft_hash(changed)
    assert len(draft_hash(draft)) == 64


def test_ksef_export_covers_header_parties_lines() -> None:
    exported = ksef_ready_dict(draft_from_dict(_draft()))
    assert exported["number"] == "FV/2026/11/7"
    assert exported["seller"]["nip"] == "5270204778"
    assert exported["totals"] == {"net": "13000.00", "vat": "2990.00", "gross": "15990.00"}
    assert len(exported["lines"]) == 2
    assert exported["lines"][0]["gross"] == "14760.00"


def test_render_text_marks_draft_and_totals() -> None:
    text = render_text(draft_from_dict(_draft()))
    assert "SZKIC, nie do wysyłki" in text
    assert "brutto 15990.00 PLN" in text
    assert canonical_json(draft_from_dict(_draft())) == canonical_json(draft_from_dict(_draft()))
