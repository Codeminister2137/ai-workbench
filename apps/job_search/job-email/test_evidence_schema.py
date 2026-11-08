"""Validation tests for the candidate-profile evidence schema.

Pins the plan's four evidence states and their claim semantics: which states
permit a claim, how unrecorded skills resolve, and how strict versus lenient
verification treats learning and absent claims. All fixtures are synthetic.
"""

from __future__ import annotations

import pytest
from evidence import analyze_vacancy_fit, verify_application_claims
from models import (
    EVIDENCE_SOURCE_KINDS,
    CandidateProfile,
    EvidenceStatus,
    JobVacancy,
    SkillEvidence,
)


@pytest.fixture
def synthetic_profile() -> CandidateProfile:
    return CandidateProfile(
        applicant_name="Alex Example",
        applicant_location="Nowhereville",
        applicant_summary="Fictional applicant used only for offline tests.",
        portfolio_url="https://example.invalid/portfolio/alex",
        linkedin_url="https://example.invalid/in/alex-example",
        skills={
            "Python": SkillEvidence("Python", EvidenceStatus.DEMONSTRATED),
            "Docker": SkillEvidence("Docker", EvidenceStatus.ADJACENT),
            "Kubernetes": SkillEvidence("Kubernetes", EvidenceStatus.LEARNING),
            "Cobol": SkillEvidence("Cobol", EvidenceStatus.ABSENT),
        },
    )


def test_evidence_schema_holds_exactly_the_four_plan_states() -> None:
    assert {status.value for status in EvidenceStatus} == {
        "demonstrated",
        "adjacent",
        "learning",
        "absent",
    }


@pytest.mark.parametrize(
    ("status", "permitted"),
    [
        (EvidenceStatus.DEMONSTRATED, True),
        (EvidenceStatus.ADJACENT, True),
        (EvidenceStatus.LEARNING, False),
        (EvidenceStatus.ABSENT, False),
    ],
)
def test_claim_permission_follows_evidence_state(status: EvidenceStatus, permitted: bool) -> None:
    assert SkillEvidence("Synthetic Skill", status).is_claim_permitted() is permitted


def test_unrecorded_skill_resolves_to_absent(synthetic_profile: CandidateProfile) -> None:
    assert synthetic_profile.get_skill_status("Rust") is EvidenceStatus.ABSENT
    assert synthetic_profile.get_skill_status("Python++") is EvidenceStatus.ABSENT
    empty = CandidateProfile(
        applicant_name="Nobody",
        applicant_location="Nowhere",
        applicant_summary="Empty synthetic profile.",
        portfolio_url="https://example.invalid",
        linkedin_url="https://example.invalid",
    )
    assert empty.get_skill_status("Python") is EvidenceStatus.ABSENT


@pytest.mark.parametrize("spelling", ["python", "PYTHON", "  Python  ", "pYtHoN"])
def test_skill_lookup_is_caseless_and_trims_whitespace(
    synthetic_profile: CandidateProfile, spelling: str
) -> None:
    assert synthetic_profile.get_skill_status(spelling) is EvidenceStatus.DEMONSTRATED


def test_backed_claims_verify_cleanly(synthetic_profile: CandidateProfile) -> None:
    result = verify_application_claims(["Python", "Docker"], synthetic_profile, strict=True)
    assert result.is_valid is True
    assert result.verified_claims == ("Python", "Docker")
    assert result.prohibited_claims == ()
    assert result.warnings == ()


@pytest.mark.parametrize("strict", [True, False])
def test_learning_claim_passes_with_warning(
    synthetic_profile: CandidateProfile, strict: bool
) -> None:
    result = verify_application_claims(["Kubernetes"], synthetic_profile, strict=strict)
    assert result.is_valid is True
    assert result.verified_claims == ("Kubernetes",)
    assert result.prohibited_claims == ()
    assert len(result.warnings) == 1
    assert "in-progress learning" in result.warnings[0]


def test_absent_claim_is_prohibited_under_strict(synthetic_profile: CandidateProfile) -> None:
    result = verify_application_claims(["Python", "Rust"], synthetic_profile, strict=True)
    assert result.is_valid is False
    assert result.verified_claims == ("Python",)
    assert result.prohibited_claims == ("Rust",)
    assert any("Prohibited claim" in warning for warning in result.warnings)


def test_absent_claim_is_flagged_but_passes_when_not_strict(
    synthetic_profile: CandidateProfile,
) -> None:
    result = verify_application_claims(["Rust"], synthetic_profile, strict=False)
    assert result.is_valid is True
    assert result.prohibited_claims == ("Rust",)
    assert result.verified_claims == ()


def test_empty_claims_verify_cleanly(synthetic_profile: CandidateProfile) -> None:
    result = verify_application_claims([], synthetic_profile, strict=True)
    assert result.is_valid is True
    assert result.verified_claims == ()
    assert result.prohibited_claims == ()
    assert result.warnings == ()


def test_vacancy_with_only_unknown_skills_scores_zero(synthetic_profile: CandidateProfile) -> None:
    vacancy = JobVacancy(
        id="vac-synthetic-absent",
        company="Example Corp",
        title="Rust Developer",
        location="Remote",
        required_skills=("Rust",),
    )
    result = analyze_vacancy_fit(vacancy, synthetic_profile)
    assert result.matched_skills == ()
    assert result.missing_requirements == ("Rust",)
    assert result.match_score == 0.0
    assert result.has_critical_gaps is True


def test_source_kinds_default_empty_for_backward_compatibility() -> None:
    assert SkillEvidence("Python", EvidenceStatus.DEMONSTRATED).source_kinds == ()


def test_source_kinds_accept_only_lawful_closed_set() -> None:
    assert EVIDENCE_SOURCE_KINDS == {"cv", "github", "linkedin_export", "manual"}
    evidence = SkillEvidence("Python", EvidenceStatus.DEMONSTRATED, source_kinds=("cv", "github"))
    assert evidence.source_kinds == ("cv", "github")


@pytest.mark.parametrize("kind", ["linkedin_scrape", "apollo", "CV", ""])
def test_unknown_source_kind_rejected(kind: str) -> None:
    with pytest.raises(ValueError, match="unknown evidence source kinds"):
        SkillEvidence("Python", EvidenceStatus.DEMONSTRATED, source_kinds=(kind,))


def test_verdicts_carry_status_and_provenance() -> None:
    profile = CandidateProfile(
        applicant_name="Provenance Case",
        applicant_location="Nowhere",
        applicant_summary="Synthetic.",
        portfolio_url="https://example.invalid",
        linkedin_url="https://example.invalid",
        skills={
            "Python": SkillEvidence(
                "Python", EvidenceStatus.DEMONSTRATED, source_kinds=("cv", "github")
            ),
        },
    )
    vacancy = JobVacancy(
        id="vac-verdicts",
        company="Example Corp",
        title="Python Developer",
        location="Remote",
        description="Synthetic vacancy.",
        required_skills=("Python", "Rust"),
    )
    result = analyze_vacancy_fit(vacancy, profile)
    by_requirement = {v.requirement: v for v in result.verdicts}
    assert by_requirement["Python"].verdict == "strong"
    assert by_requirement["Python"].source_kinds == ("cv", "github")
    assert by_requirement["Rust"].verdict == "missing"
    assert by_requirement["Rust"].source_kinds == ()


def test_verdict_labels_cover_all_states(synthetic_profile: CandidateProfile) -> None:
    vacancy = JobVacancy(
        id="vac-labels",
        company="Example Corp",
        title="Generalist",
        location="Remote",
        description="Synthetic vacancy.",
        required_skills=("Python", "Docker", "Kubernetes", "Cobol"),
    )
    result = analyze_vacancy_fit(vacancy, synthetic_profile)
    assert [v.verdict for v in result.verdicts] == [
        "strong",
        "partial",
        "uncertain",
        "missing",
    ]


def test_uncertainty_flags_name_empty_inputs(synthetic_profile: CandidateProfile) -> None:
    bare = JobVacancy(
        id="vac-bare",
        company="Example Corp",
        title="Mystery Role",
        location="Remote",
    )
    result = analyze_vacancy_fit(bare, synthetic_profile)
    assert "no_explicit_skills" in result.uncertainty_flags
    assert "empty_description" in result.uncertainty_flags
    solid = JobVacancy(
        id="vac-solid",
        company="Example Corp",
        title="Python Developer",
        location="Remote",
        description="Synthetic vacancy.",
        required_skills=("Python",),
    )
    assert analyze_vacancy_fit(solid, synthetic_profile).uncertainty_flags == ()
