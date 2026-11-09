"""Provider-agnostic contact resolution for job vacancies.

Owner direction (inbox 8d325394-A): contact sources follow the same
multi-service approach as ai_provider. Each source proposes one named
contact (or nothing); vendor adapters (Prospeo, Apollo) register later
behind this interface once accounts exist. Nothing here touches the
network.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from models import JobVacancy

GENERIC_LOCAL_PARTS = frozenset(
    {
        "info",
        "contact",
        "careers",
        "jobs",
        "apply",
        "applications",
        "hr",
        "hello",
        "office",
        "admin",
        "support",
        "team",
    }
)


@dataclass(frozen=True, slots=True)
class ContactProposal:
    """One proposed outreach contact with honest provenance."""

    email: str
    name: str | None = None
    title: str | None = None
    source: str = "manual"
    verified: bool = False
    generic_inbox: bool = False
    evidence: tuple[str, ...] = ()


class ContactSource(Protocol):
    """Resolves at most one contact proposal per vacancy."""

    name: str

    def resolve(self, vacancy: JobVacancy) -> ContactProposal | None:
        """Return a proposal, or None when this source has nothing."""
        ...


def is_generic_inbox(email: str) -> bool:
    """True for role addresses (info@, careers@, ...) vs named people."""
    local = email.strip().split("@")[0].lower() if "@" in email else email.strip().lower()
    return local in GENERIC_LOCAL_PARTS


class ManualContactSource:
    """Uses only the vacancy's own contact fields; never the network.

    Proposals are always unverified; generic inboxes are flagged so the
    pipeline prefers named contacts and treats these as fallback.
    """

    name = "manual"

    def resolve(self, vacancy: JobVacancy) -> ContactProposal | None:
        email = (vacancy.contact_email or "").strip()
        if not email or "@" not in email:
            return None
        generic = is_generic_inbox(email)
        evidence = [f"vacancy.contact_email={email}"]
        if vacancy.recruiter_name:
            evidence.append(f"vacancy.recruiter_name={vacancy.recruiter_name}")
        return ContactProposal(
            email=email,
            name=(vacancy.recruiter_name or "").strip() or None,
            source="manual:vacancy",
            verified=False,
            generic_inbox=generic,
            evidence=tuple(evidence),
        )


class ContactRegistry:
    """Ordered contact sources; first proposal wins."""

    def __init__(self, sources: list[ContactSource] | None = None) -> None:
        self._sources: list[ContactSource] = list(sources or [ManualContactSource()])

    def register(self, source: ContactSource) -> None:
        """Append a source (vendor adapters plug in here)."""
        self._sources.append(source)

    @property
    def source_names(self) -> tuple[str, ...]:
        return tuple(s.name for s in self._sources)

    def resolve(self, vacancy: JobVacancy) -> ContactProposal | None:
        proposal, _tried = self.resolve_trace(vacancy)
        return proposal

    def resolve_trace(self, vacancy: JobVacancy) -> tuple[ContactProposal | None, tuple[str, ...]]:
        """Resolve plus the tried source names in order (for spend caps)."""
        tried: list[str] = []
        for source in self._sources:
            tried.append(source.name)
            proposal = source.resolve(vacancy)
            if proposal is not None:
                return proposal, tuple(tried)
        return None, tuple(tried)
