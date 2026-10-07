"""Tests for job-search models, evidence verification, deduplication, and sending controls."""

from __future__ import annotations

import pytest
from approval import (
    approve_package,
    reject_package,
    update_package_content,
)
from deduplication import compute_duplicate_key, deduplicate_vacancies, is_duplicate_vacancy
from evidence import (
    ProhibitedClaimError,
    verify_application_claims,
)
from models import (
    ApplicationStatus,
    CandidateProfile,
    CVVariant,
    EmploymentType,
    EvidenceStatus,
    JobVacancy,
    SkillEvidence,
    WorkMode,
)
from preparation import prepare_application
from sender import DryRunEmailTransport, UnapprovedApplicationError, deliver_application


@pytest.fixture
def sample_profile() -> CandidateProfile:
    return CandidateProfile(
        applicant_name="Jakub Jaworski",
        applicant_location="Poland",
        applicant_summary="Python Developer with backend and AI tooling experience.",
        portfolio_url="https://github.com/example",
        linkedin_url="https://linkedin.com/in/example",
        skills={
            "Python": SkillEvidence("Python", EvidenceStatus.DEMONSTRATED),
            "FastAPI": SkillEvidence("FastAPI", EvidenceStatus.DEMONSTRATED),
            "Docker": SkillEvidence("Docker", EvidenceStatus.ADJACENT),
            "Kubernetes": SkillEvidence("Kubernetes", EvidenceStatus.LEARNING),
        },
        cv_variants={
            "backend": CVVariant("backend", "cv_backend.pdf", "Backend Developer"),
        },
    )


@pytest.fixture
def sample_vacancy() -> JobVacancy:
    return JobVacancy(
        id="vac-101",
        company="Acme Corp Sp. z o.o.",
        title="Sr. Python Dev",
        location="Warsaw, Poland",
        work_mode=WorkMode.REMOTE,
        employment_type=EmploymentType.B2B,
        required_skills=("Python", "FastAPI"),
        preferred_skills=("Docker", "Rust"),
        source_url="https://example.com/jobs/101",
        contact_email="recruiter@acme.com",
    )


def test_duplicate_detection_normalizes_legal_suffixes_and_titles(
    sample_vacancy: JobVacancy,
) -> None:
    variant = JobVacancy(
        id="vac-102",
        company="acme corp",
        title="Senior Python Developer",
        location="warsaw poland",
    )
    assert compute_duplicate_key(
        sample_vacancy.company, sample_vacancy.title, sample_vacancy.location
    ) == compute_duplicate_key(variant.company, variant.title, variant.location)
    assert is_duplicate_vacancy(variant, [sample_vacancy]) is True


def test_deduplicate_vacancies_preserves_first_occurrence(sample_vacancy: JobVacancy) -> None:
    duplicate = JobVacancy(
        id="vac-103",
        company="Acme Corp",
        title="Python Dev",
        location="Warsaw",
        source_url="https://example.com/jobs/101",
    )
    unique = JobVacancy(
        id="vac-104",
        company="Beta Inc",
        title="Python Developer",
        location="Krakow",
        source_url="https://example.com/jobs/104",
    )
    deduped = deduplicate_vacancies([sample_vacancy, duplicate, unique])
    assert len(deduped) == 2
    assert deduped[0].id == "vac-101"
    assert deduped[1].id == "vac-104"


def test_evidence_verification_prohibits_unbacked_claims(sample_profile: CandidateProfile) -> None:
    # Rust is absent from profile
    claims = ["Python", "Rust"]
    result = verify_application_claims(claims, sample_profile, strict=True)
    assert result.is_valid is False
    assert "Rust" in result.prohibited_claims
    assert "Python" in result.verified_claims


def test_prepare_application_raises_on_prohibited_claims(
    sample_profile: CandidateProfile, sample_vacancy: JobVacancy
) -> None:
    with pytest.raises(ProhibitedClaimError, match="prohibited/fabricated"):
        prepare_application(
            sample_profile,
            sample_vacancy,
            explicit_claims=["Rust", "Golang"],
            strict_evidence=True,
        )


def test_prepare_application_creates_unapproved_package(
    sample_profile: CandidateProfile, sample_vacancy: JobVacancy
) -> None:
    package = prepare_application(sample_profile, sample_vacancy)
    assert package.status is ApplicationStatus.PREPARED
    assert package.is_approved_for_sending() is False
    assert package.contact_email == "recruiter@acme.com"
    assert "Python" in package.body


def test_delivery_strictly_blocks_unapproved_package(
    sample_profile: CandidateProfile, sample_vacancy: JobVacancy
) -> None:
    package = prepare_application(sample_profile, sample_vacancy)
    transport = DryRunEmailTransport()
    with pytest.raises(
        UnapprovedApplicationError, match="cannot be sent without explicit human approval"
    ):
        deliver_application(package, transport)
    assert len(transport.sent_deliveries) == 0


def test_approval_and_successful_delivery_workflow(
    sample_profile: CandidateProfile, sample_vacancy: JobVacancy
) -> None:
    package = prepare_application(sample_profile, sample_vacancy)
    approved = approve_package(package, approved_by="owner", notes="Reviewed draft")
    assert approved.is_approved_for_sending() is True
    assert approved.status is ApplicationStatus.APPROVED

    transport = DryRunEmailTransport()
    delivered = deliver_application(approved, transport)
    assert delivered.status is ApplicationStatus.SENT
    assert delivered.send_receipt is not None
    assert delivered.send_receipt.success is True
    assert len(transport.sent_deliveries) == 1


def test_editing_approved_package_revokes_approval(
    sample_profile: CandidateProfile, sample_vacancy: JobVacancy
) -> None:
    package = prepare_application(sample_profile, sample_vacancy)
    approved = approve_package(package, approved_by="owner")
    assert approved.is_approved_for_sending() is True

    # Mutate content post-approval
    edited = update_package_content(approved, subject="Updated Subject")
    assert edited.status is ApplicationStatus.PREPARED
    assert edited.is_approved_for_sending() is False
    assert edited.approved_at_utc is None


def test_reject_package_marks_skipped_and_blocks_delivery(
    sample_profile: CandidateProfile, sample_vacancy: JobVacancy
) -> None:
    package = prepare_application(sample_profile, sample_vacancy)
    rejected = reject_package(package, reason="Not interested in hybrid/onsite")
    assert rejected.status is ApplicationStatus.SKIPPED

    transport = DryRunEmailTransport()
    with pytest.raises(UnapprovedApplicationError):
        deliver_application(rejected, transport)
