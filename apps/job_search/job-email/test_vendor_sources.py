"""Vendor adapters: stubbed resolution, key handling, signal gating."""

from __future__ import annotations

from typing import Any

from models import JobVacancy
from vendor_sources import (
    ApolloContactSource,
    ProspeoContactSource,
    VendorError,
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
    import vendor_sources

    monkeypatch.setattr(vendor_sources, "_read_env_or_dotenv", lambda name: None)
    apollo = ApolloContactSource()
    assert apollo.ready is False
    assert apollo.resolve(_vacancy()) is None
    prospeo = ProspeoContactSource()
    assert prospeo.ready is False
    assert prospeo.resolve(_vacancy()) is None
