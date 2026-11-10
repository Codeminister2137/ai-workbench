"""Vendor adapters: stubbed resolution, key handling, signal gating."""

from __future__ import annotations

import urllib.error
from email.message import Message
from typing import Any

import pytest
import vendor_sources
from models import JobVacancy
from vendor_sources import (
    ApolloContactSource,
    ProspeoContactSource,
    VendorError,
    _post_json,
)


def _vacancy(**overrides: Any) -> JobVacancy:
    base: dict[str, Any] = {
        "id": "v1",
        "company": "Example",
        "title": "Backend dev",
        "location": "Remote",
        "contact_email": "rekrutacja@example.com",
        "recruiter_name": "Anna Kowalska",
    }
    base.update(overrides)
    return JobVacancy(**base)


def _apollo_ok(url, headers, payload, timeout):
    assert url.endswith("/people/match")
    assert headers["x-api-key"] == "k-apollo"
    assert payload == {"first_name": "Anna", "last_name": "Kowalska", "domain": "example.com"}
    return {
        "person": {
            "email": "anna.kowalska@example.com",
            "email_status": "verified",
            "name": "Anna Kowalska",
            "title": "Recruiter",
        }
    }


def _prospeo_ok(url, headers, payload, timeout):
    assert url.endswith("/enrich-person")
    assert headers["X-KEY"] == "k-prospeo"
    assert payload["data"] == {
        "first_name": "Anna",
        "last_name": "Kowalska",
        "company_name": "Example",
        "company_website": "example.com",
    }
    assert payload["only_verified_email"] is True
    return {
        "person": {
            "email": {
                "email": "anna.kowalska@example.com",
                "status": "VERIFIED",
            },
            "full_name": "Anna Kowalska",
            "current_job_title": "Recruiter",
        }
    }


def test_apollo_resolves_verified_proposal() -> None:
    source = ApolloContactSource(api_key="k-apollo", post=_apollo_ok)
    assert source.ready is True
    proposal = source.resolve(_vacancy())
    assert proposal is not None
    assert proposal.email == "anna.kowalska@example.com"
    assert proposal.verified is True
    assert proposal.source == "apollo:people/match"


def test_prospeo_resolves_verified_proposal() -> None:
    source = ProspeoContactSource(api_key="k-prospeo", post=_prospeo_ok)
    assert source.ready is True
    proposal = source.resolve(_vacancy())
    assert proposal is not None
    assert proposal.email == "anna.kowalska@example.com"
    assert proposal.verified is True
    assert proposal.source == "prospeo:enrich-person"


def test_vendors_return_none_without_signals() -> None:
    apollo = ApolloContactSource(api_key="k", post=_apollo_ok)
    assert apollo.resolve(_vacancy(recruiter_name=None)) is None
    assert apollo.resolve(_vacancy(recruiter_name="Madonna")) is None
    assert apollo.resolve(_vacancy(contact_email="anna@gmail.com")) is None
    assert apollo.resolve(_vacancy(contact_email=None)) is None
    prospeo = ProspeoContactSource(api_key="k", post=_prospeo_ok)
    assert prospeo.resolve(_vacancy(recruiter_name=None)) is None
    assert prospeo.resolve(_vacancy(contact_email="x@o2.pl")) is None


def test_vendors_return_none_on_vendor_failure() -> None:
    def boom(url, headers, payload, timeout):
        raise VendorError("down")

    assert ApolloContactSource(api_key="k", post=boom).resolve(_vacancy()) is None
    assert ProspeoContactSource(api_key="k", post=boom).resolve(_vacancy()) is None
    empty = ApolloContactSource(api_key="k", post=lambda *a: {"person": None})
    assert empty.resolve(_vacancy()) is None


def test_missing_key_leaves_source_dormant(monkeypatch) -> None:
    monkeypatch.delenv("APOLLO_API_KEY", raising=False)
    monkeypatch.delenv("PROSPEO_API_KEY", raising=False)
    monkeypatch.setattr(vendor_sources, "_read_env_or_dotenv", lambda name: None)
    apollo = ApolloContactSource()
    assert apollo.ready is False
    assert apollo.resolve(_vacancy()) is None
    prospeo = ProspeoContactSource()
    assert prospeo.ready is False
    assert prospeo.resolve(_vacancy()) is None


def test_post_json_reports_http_status(monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise urllib.error.HTTPError("https://api.apollo.io/x", 403, "Forbidden", Message(), None)

    monkeypatch.setattr(vendor_sources.urllib.request, "urlopen", forbidden)
    with pytest.raises(VendorError, match="returned HTTP 403"):
        _post_json("https://api.apollo.io/x", {}, {}, 1)


def test_post_json_reports_unreachable_without_status(monkeypatch) -> None:
    def down(*args, **kwargs):
        raise OSError("dns down")

    monkeypatch.setattr(vendor_sources.urllib.request, "urlopen", down)
    with pytest.raises(VendorError, match="unreachable: OSError"):
        _post_json("https://api.apollo.io/x", {}, {}, 1)


PAGE_FIXTURE = {
    "error": False,
    "free": False,
    "companies": [
        {
            "company": {
                "company_id": "c1",
                "name": "Acme Metal",
                "website": "https://acme.example.pl",
                "domain": "acme.example.pl",
                "industry": "Mechanical Engineering",
                "employee_count": 120,
                "employee_range": "51-200",
                "location": {"country": "Poland", "city": "Bielsko"},
                "keywords": ["cnc", "automation"],
                "description_ai": "Metal parts maker.",
            }
        },
        {"company": {"name": "  ", "domain": None}},
        {"company": None},
        "not-a-dict",
    ],
    "current_page": 1,
    "per_page": 25,
    "total_page": 4,
    "total_count": 87,
}


def _stub_post_factory(captured: dict, payload: dict):
    def _stub(url: str, headers: dict, body: dict, timeout: float) -> dict:
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = body
        return payload

    return _stub


def test_search_prospeo_companies_parses_page() -> None:
    from vendor_sources import PROSPEO_SEARCH_COMPANY_URL, search_prospeo_companies

    captured: dict = {}
    page = search_prospeo_companies(
        api_key="k",
        filters={"company_location_search": {"include": ["Poland"]}},
        page=2,
        post=_stub_post_factory(captured, PAGE_FIXTURE),
    )
    assert captured["url"] == PROSPEO_SEARCH_COMPANY_URL
    assert captured["headers"] == {"X-KEY": "k"}
    assert captured["body"] == {
        "filters": {"company_location_search": {"include": ["Poland"]}},
        "page": 2,
    }
    assert page.total_count == 87 and page.total_pages == 4 and page.current_page == 1
    assert page.served_free_dedup is False
    assert len(page.companies) == 1
    company = page.companies[0]
    assert company.name == "Acme Metal"
    assert company.domain == "acme.example.pl"
    assert company.hq_country == "Poland" and company.hq_city == "Bielsko"
    assert company.keywords == ("cnc", "automation")


def test_search_prospeo_companies_validates_and_maps_errors() -> None:
    from vendor_sources import VendorError, search_prospeo_companies

    with pytest.raises(VendorError, match="API key"):
        search_prospeo_companies(api_key="", filters={"a": 1}, post=lambda *a: {})
    with pytest.raises(VendorError, match="at least one filter"):
        search_prospeo_companies(api_key="k", filters={}, post=lambda *a: {})
    with pytest.raises(VendorError, match="page"):
        search_prospeo_companies(api_key="k", filters={"a": 1}, page=0, post=lambda *a: {})
    with pytest.raises(VendorError, match="INVALID_FILTERS"):
        search_prospeo_companies(
            api_key="k",
            filters={"a": 1},
            post=lambda *a: {"error": True, "error_code": "INVALID_FILTERS"},
        )
    with pytest.raises(VendorError, match="non-list"):
        search_prospeo_companies(
            api_key="k", filters={"a": 1}, post=lambda *a: {"error": False, "companies": {}}
        )
