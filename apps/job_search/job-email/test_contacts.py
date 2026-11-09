"""Tests for provider-agnostic contact resolution (no network)."""

from __future__ import annotations

from typing import Any

import pytest
from contacts import (
    ContactProposal,
    ContactRegistry,
    ManualContactSource,
    is_generic_inbox,
)
from models import JobVacancy


def _vacancy(**overrides: Any) -> JobVacancy:
    base: dict[str, Any] = {
        "id": "v1",
        "company": "Example",
        "title": "Dev",
        "location": "Warsaw",
    }
    base.update(overrides)
    return JobVacancy(**base)


def test_generic_inbox_detection() -> None:
    assert is_generic_inbox("info@example.com")
    assert is_generic_inbox("Careers@Example.com")
    assert is_generic_inbox("jobs+pl@example.com") is False
    assert not is_generic_inbox("jan.kowalski@example.com")
    assert not is_generic_inbox("not-an-email")


def test_manual_resolves_named_contact_unverified() -> None:
    proposal = ManualContactSource().resolve(
        _vacancy(contact_email="jan.k@example.com", recruiter_name="Jan K")
    )
    assert proposal is not None
    assert proposal.email == "jan.k@example.com"
    assert proposal.name == "Jan K"
    assert proposal.source == "manual:vacancy"
    assert proposal.verified is False
    assert proposal.generic_inbox is False
    assert any("recruiter_name" in e for e in proposal.evidence)


def test_manual_flags_generic_inbox_fallback() -> None:
    proposal = ManualContactSource().resolve(_vacancy(contact_email="info@example.com"))
    assert proposal is not None
    assert proposal.generic_inbox is True
    assert proposal.name is None


def test_manual_returns_none_without_email() -> None:
    assert ManualContactSource().resolve(_vacancy()) is None
    assert ManualContactSource().resolve(_vacancy(contact_email="no-at-sign")) is None


def test_registry_first_proposal_wins() -> None:
    class Vendor:
        name = "vendor"

        def resolve(self, vacancy):
            return ContactProposal(
                email="vet@example.com", name="Vet", source="vendor", verified=True
            )

    registry = ContactRegistry([Vendor(), ManualContactSource()])
    assert registry.source_names == ("vendor", "manual")
    proposal = registry.resolve(_vacancy(contact_email="info@example.com"))
    assert proposal is not None
    assert proposal.source == "vendor"
    assert proposal.verified is True


def test_registry_defaults_to_manual() -> None:
    registry = ContactRegistry()
    assert registry.source_names == ("manual",)
    assert registry.resolve(_vacancy()) is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
