"""Candidate evidence evaluation and prohibited claims verification.

Enforces the core rule of the Job Search plan: never invent or upgrade
qualifications. Every claim in an application must be traceable to demonstrated
or adjacent evidence in the candidate profile.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from models import CandidateProfile, EvidenceStatus, JobVacancy


class ProhibitedClaimError(ValueError):
    """Raised when an application asserts qualifications not present in the candidate evidence."""


@dataclass(frozen=True, slots=True)
class VacancyMatchAnalysis:
    """Breakdown of how a candidate's evidence maps to a job vacancy's requirements."""

    matched_skills: tuple[str, ...]
    adjacent_skills: tuple[str, ...]
    learning_skills: tuple[str, ...]
    missing_requirements: tuple[str, ...]
    match_score: float

    @property
    def has_critical_gaps(self) -> bool:
        """Return True if more than half of required skills are completely missing."""
        total_reqs = (
            len(self.matched_skills) + len(self.adjacent_skills) + len(self.missing_requirements)
        )
        if total_reqs == 0:
            return False
        return len(self.missing_requirements) > total_reqs / 2


@dataclass(frozen=True, slots=True)
class ClaimVerificationResult:
    """Outcome of validating application content against candidate evidence."""

    is_valid: bool
    verified_claims: tuple[str, ...]
    prohibited_claims: tuple[str, ...]
    warnings: tuple[str, ...]


def analyze_vacancy_fit(
    vacancy: JobVacancy,
    profile: CandidateProfile,
) -> VacancyMatchAnalysis:
    """Compare a vacancy's required and preferred skills against candidate evidence."""
    matched: list[str] = []
    adjacent: list[str] = []
    learning: list[str] = []
    missing: list[str] = []

    all_reqs = list(vacancy.required_skills) + list(vacancy.preferred_skills)
    if not all_reqs:
        # If no explicit skills listed, fallback to a neutral baseline
        return VacancyMatchAnalysis(
            matched_skills=(),
            adjacent_skills=(),
            learning_skills=(),
            missing_requirements=(),
            match_score=1.0,
        )

    for skill in all_reqs:
        status = profile.get_skill_status(skill)
        match status:
            case EvidenceStatus.DEMONSTRATED:
                matched.append(skill)
            case EvidenceStatus.ADJACENT:
                adjacent.append(skill)
            case EvidenceStatus.LEARNING:
                learning.append(skill)
            case EvidenceStatus.ABSENT:
                missing.append(skill)

    total = len(all_reqs)
    score = (len(matched) * 1.0 + len(adjacent) * 0.5 + len(learning) * 0.25) / total
    return VacancyMatchAnalysis(
        matched_skills=tuple(matched),
        adjacent_skills=tuple(adjacent),
        learning_skills=tuple(learning),
        missing_requirements=tuple(missing),
        match_score=round(score, 3),
    )


def verify_application_claims(
    claims: Sequence[str],
    profile: CandidateProfile,
    *,
    strict: bool = True,
) -> ClaimVerificationResult:
    """Check explicit skill claims against the candidate profile.

    If strict is True, any claim with ABSENT status is marked prohibited.
    """
    verified: list[str] = []
    prohibited: list[str] = []
    warnings: list[str] = []

    for claim in claims:
        status = profile.get_skill_status(claim)
        if status in (EvidenceStatus.DEMONSTRATED, EvidenceStatus.ADJACENT):
            verified.append(claim)
        elif status == EvidenceStatus.LEARNING:
            warnings.append(
                f"Claim '{claim}' is marked as in-progress learning, not demonstrated expertise."
            )
            verified.append(claim)
        else:
            prohibited.append(claim)
            warnings.append(
                f"Prohibited claim: '{claim}' has no backing evidence in candidate profile."
            )

    is_valid = len(prohibited) == 0 if strict else True
    return ClaimVerificationResult(
        is_valid=is_valid,
        verified_claims=tuple(verified),
        prohibited_claims=tuple(prohibited),
        warnings=tuple(warnings),
    )
