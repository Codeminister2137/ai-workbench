"""Client-search slice 1: scoring rules, opener drafts, brief assembly."""

from __future__ import annotations

import pytest
from client_search import (
    ClientBrief,
    CompanyLead,
    OfferProfile,
    build_brief,
    draft_opener,
    fit_score,
)
from contacts import ContactProposal

OFFER = OfferProfile(
    name="Automation",
    capabilities=("chatbot", "crm", "faktury"),
    ideal_sectors=("produkcja", "handel"),
    ideal_sizes=("smb", "mid"),
)


def _lead(**overrides) -> CompanyLead:
    base = {
        "name": "Acme Sp. z o.o.",
        "domain": "acme.example.pl",
        "sector": "produkcja",
        "size_band": "smb",
        "notes": "Ręczne faktury, stary CRM.",
    }
    base.update(overrides)
    return CompanyLead(**base)


def test_full_match_scores_100_with_rationale() -> None:
    fit = fit_score(_lead(), OFFER)
    assert fit.score == 100
    assert any("sector" in line for line in fit.rationale)
    assert any("size" in line for line in fit.rationale)
    assert any("faktury" in line for line in fit.rationale)


def test_partial_and_empty_signals() -> None:
    assert fit_score(_lead(sector="rolnictwo", size_band="mid", notes=""), OFFER).score == 30
    empty = fit_score(_lead(sector="", size_band="", notes="nic"), OFFER)
    assert empty.score == 0
    assert empty.rationale == ("no sector/size/capability signal",)


def test_opener_personalized_or_generic() -> None:
    personal = draft_opener(_lead(), OFFER, author_name="Jan K", contact_name="Anna")
    assert personal.startswith("Dzień dobry Anna,")
    assert "Jan K" in personal and "Acme" in personal
    generic = draft_opener(_lead(), OFFER, author_name="Jan K")
    assert generic.startswith("Dzień dobry,")
    with pytest.raises(ValueError, match="author_name"):
        draft_opener(_lead(), OFFER, author_name="  ")


def test_build_brief_assembles_contact_and_fit() -> None:
    contact = ContactProposal(email="anna@acme.example.pl", name="Anna", source="manual:list")
    brief = build_brief(_lead(), OFFER, author_name="Jan K", contact=contact)
    assert isinstance(brief, ClientBrief)
    assert brief.fit.score == 100
    assert brief.contact is contact
    assert "Anna" in brief.opener
    with pytest.raises(ValueError, match="name and domain"):
        build_brief(_lead(name=" "), OFFER, author_name="Jan K")
