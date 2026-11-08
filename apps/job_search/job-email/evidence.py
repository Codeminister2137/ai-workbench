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


VERDICT_FOR_STATUS = {
    EvidenceStatus.DEMONSTRATED: "strong",
    EvidenceStatus.ADJACENT: "partial",
    EvidenceStatus.LEARNING: "uncertain",
    EvidenceStatus.ABSENT: "missing",
}


@dataclass(frozen=True, slots=True)
class RequirementVerdict:
    """Per-requirement match verdict with evidence provenance."""

    requirement: str
    verdict: str
    status: EvidenceStatus
    source_kinds: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VacancyMatchAnalysis:
    """Breakdown of how a candidate's evidence maps to a job vacancy's requirements."""

    matched_skills: tuple[str, ...]
    adjacent_skills: tuple[str, ...]
    learning_skills: tuple[str, ...]
    missing_requirements: tuple[str, ...]
    match_score: float
    required_skills: tuple[str, ...] = ()
    verdicts: tuple[RequirementVerdict, ...] = ()
    uncertainty_flags: tuple[str, ...] = ()

    @property
    def has_critical_gaps(self) -> bool:
        """Return True if more than half of required skills are completely missing."""
        required = {skill.strip().casefold() for skill in self.required_skills}
        total_reqs = len(required)
        if total_reqs == 0:
            return False
        missing = {skill.strip().casefold() for skill in self.missing_requirements}
        return len(required & missing) > total_reqs / 2


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

    all_reqs = list(
        {
            skill.strip().casefold(): skill.strip()
            for skill in (*vacancy.required_skills, *vacancy.preferred_skills)
            if skill.strip()
        }.values()
    )

    def find_evidence(skill: str):
        key = skill.strip().casefold()
        for name, evidence in profile.skills.items():
            if name.strip().casefold() == key:
                return evidence
        return None

    flags: list[str] = []
    if not all_reqs:
        flags.append("no_explicit_skills")
    if not vacancy.description.strip():
        flags.append("empty_description")
    if not all_reqs:
        # If no explicit skills listed, fallback to a neutral baseline
        return VacancyMatchAnalysis(
            matched_skills=(),
            adjacent_skills=(),
            learning_skills=(),
            missing_requirements=(),
            match_score=1.0,
            uncertainty_flags=tuple(flags),
        )

    verdicts: list[RequirementVerdict] = []
    for skill in all_reqs:
        status = profile.get_skill_status(skill)
        found = find_evidence(skill)
        verdicts.append(
            RequirementVerdict(
                requirement=skill,
                verdict=VERDICT_FOR_STATUS[status],
                status=status,
                source_kinds=found.source_kinds if found is not None else (),
            )
        )
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
        required_skills=vacancy.required_skills,
        verdicts=tuple(verdicts),
        uncertainty_flags=tuple(flags),
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
