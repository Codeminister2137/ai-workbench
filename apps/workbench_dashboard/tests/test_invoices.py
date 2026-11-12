"""Invoice drafts API: create/get/review/revise over billing validation."""

from __future__ import annotations

from urllib.error import HTTPError

import pytest
from dashboard_test_http import get_json, post_json


def _party(name="Firma", nip="5270204778"):
    return {
        "name": name,
        "nip": nip,
        "street": "Ulica 1",
        "city": "Skoczow",
        "postal": "43-430",
    }


def _draft(**overrides):
    payload = {
        "number": "FV/2026/11/7",
        "issue_date": "2026-11-12",
        "seller": _party(name="Sprzedawca", nip="5270204778"),
        "buyer": _party(name="Klient SA", nip="5260250274"),
        "lines": [
            {
                "description": "Automatyzacja",
                "quantity": "1",
                "unit_net": "10000.00",
                "vat_rate": "23",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_create_get_review_flow(dashboard_server) -> None:
    created = post_json(dashboard_server, "/api/invoices", _draft())
    assert created["ok"] is True
    item_id = created["id"]
    detail = get_json(dashboard_server, f"/api/invoices/{item_id}")
    assert detail["item"]["number"] == "FV/2026/11/7"
    assert detail["item"]["totals"]["gross"] == "12300.00"
    assert detail["item"]["approval_valid"] is False
    assert "SZKIC" in detail["item"]["text"]
    listed = get_json(dashboard_server, "/api/invoices")
    assert [item["id"] for item in listed["items"]] == [item_id]
    reviewed = post_json(dashboard_server, f"/api/invoices/{item_id}/review", {"reviewer": "Jakub"})
    assert reviewed["item"]["approval_valid"] is True
    assert reviewed["item"]["approval"]["reviewer"] == "Jakub"


def test_revise_clears_approval(dashboard_server) -> None:
    created = post_json(dashboard_server, "/api/invoices", _draft())
    item_id = created["id"]
    post_json(dashboard_server, f"/api/invoices/{item_id}/review", {"reviewer": "Jakub"})
    revised = post_json(
        dashboard_server,
        f"/api/invoices/{item_id}",
        _draft(notes="changed scope"),
    )
    assert revised["item"]["approval_valid"] is False
    assert revised["item"]["approval"] is None


def test_duplicate_number_refused(dashboard_server) -> None:
    post_json(dashboard_server, "/api/invoices", _draft())
    with pytest.raises(HTTPError) as exc:
        post_json(dashboard_server, "/api/invoices", _draft())
    assert exc.value.code == 400


def test_validation_errors_are_400(dashboard_server) -> None:
    with pytest.raises(HTTPError) as exc:
        post_json(dashboard_server, "/api/invoices", _draft(number="bogus"))
    assert exc.value.code == 400
    with pytest.raises(HTTPError) as exc:
        post_json(
            dashboard_server,
            "/api/invoices",
            _draft(buyer=_party(nip="1111111112")),
        )
    assert exc.value.code == 400
    with pytest.raises(HTTPError) as exc:
        get_json(dashboard_server, "/api/invoices/does-not-exist")
    assert exc.value.code == 404


def test_invoices_tab_markers() -> None:
    from pathlib import Path

    web = Path(__file__).resolve().parent.parent / "web"
    js = (web / "app.js").read_text(encoding="utf-8")
    html = (web / "index.html").read_text(encoding="utf-8")
    assert 'data-view="invoices"' in html
    assert 'name === "invoices"' in js
    assert "/api/invoices/" in js
    assert "Approve draft" in js
