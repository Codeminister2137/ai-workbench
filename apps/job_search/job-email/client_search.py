"""Client-search slice 1: fit scoring + opener drafts from supplied leads.

Same contact model as employer search (ContactProposal), different source:
leads come from an owner-supplied company list. No vendor calls, no sending —
this module scores fit against an offer profile and drafts openers for owner
review. Vendor person-search plugs in when an endpoint is confirmed.
"""

from __future__ import annotations

from dataclasses import dataclass

from contacts import ContactProposal

SIZE_BANDS = ("solo", "micro", "smb", "mid", "enterprise")


@dataclass(frozen=True, slots=True)
class CompanyLead:
    """One candidate client company from the owner-supplied list."""

    name: str
    domain: str
    sector: str = ""
    size_band: str = ""
    notes: str = ""
    source: str = "manual:list"


@dataclass(frozen=True, slots=True)
class OfferProfile:
    """What we sell and who it fits; caller-supplied (no approved offering yet)."""

    name: str
    capabilities: tuple[str, ...] = ()
    ideal_sectors: tuple[str, ...] = ()
    ideal_sizes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ClientFit:
    """Deterministic fit score with auditable rationale."""

    score: int
    rationale: tuple[str, ...] = ()


def fit_score(lead: CompanyLead, offer: OfferProfile) -> ClientFit:
    """Score 0-100: sector 50, size 30, capability-keyword overlap 20."""
    reasons: list[str] = []
    score = 0
    sector = lead.sector.strip().lower()
    if sector and sector in {s.strip().lower() for s in offer.ideal_sectors}:
        score += 50
        reasons.append(f"sector match: {lead.sector.strip()}")
    size = lead.size_band.strip().lower()
    if size and size in {s.strip().lower() for s in offer.ideal_sizes}:
        score += 30
        reasons.append(f"size match: {lead.size_band.strip()}")
    haystack = f"{lead.name} {lead.notes}".lower()
    hits = sorted(
        {cap for cap in offer.capabilities if cap.strip() and cap.strip().lower() in haystack}
    )
    if hits:
        score += 20
        reasons.append(f"capability overlap: {', '.join(hits)}")
    if not reasons:
        reasons.append("no sector/size/capability signal")
    return ClientFit(score=min(score, 100), rationale=tuple(reasons))


@dataclass(frozen=True, slots=True)
class ClientBrief:
    """One reviewable client brief: fit + opener + optional contact."""

    lead: CompanyLead
    fit: ClientFit
    opener: str
    contact: ContactProposal | None = None


def draft_opener(
    lead: CompanyLead, offer: OfferProfile, *, author_name: str, contact_name: str | None = None
) -> str:
    """Draft a short first-touch opener for owner review. Never sends."""
    if not author_name.strip():
        raise ValueError("author_name is required")
    greeting = (
        f"Dzień dobry {contact_name.strip()},"
        if contact_name and contact_name.strip()
        else "Dzień dobry,"
    )
    capabilities = ", ".join(offer.capabilities) if offer.capabilities else offer.name
    return (
        f"{greeting}\n\n"
        f"Nazywam się {author_name.strip()} i pomagam firmom takim jak {lead.name} "
        f"automatyzować powtarzalną pracę ({capabilities}).\n\n"
        "Czy 15-minutowa rozmowa o Waszych najbardziej czasochłonnych procesach "
        "miałaby sens?\n\n"
        f"Pozdrawiam,\n{author_name.strip()}"
    )


def build_brief(
    lead: CompanyLead,
    offer: OfferProfile,
    *,
    author_name: str,
    contact: ContactProposal | None = None,
) -> ClientBrief:
    """Assemble one reviewable brief. No network, no sending."""
    if not lead.name.strip() or not lead.domain.strip():
        raise ValueError("lead needs a name and domain")
    fit = fit_score(lead, offer)
    opener = draft_opener(
        lead, offer, author_name=author_name, contact_name=contact.name if contact else None
    )
    return ClientBrief(lead=lead, fit=fit, opener=opener, contact=contact)
