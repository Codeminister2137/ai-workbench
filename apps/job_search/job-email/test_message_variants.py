"""Explicit message version selection for prepared applications.

Covers the Phase 1 application-record slice: every prepared package records
which message variant produced its subject/body, unknown variants are rejected
instead of silently substituted, and the send receipt completes the record.
All fixtures are obviously synthetic.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from approval import approve_package
from models import (
    ApplicationStatus,
    CandidateProfile,
    CVVariant,
    EvidenceStatus,
    JobVacancy,
    MessageVariant,
    SkillEvidence,
)
from preparation import MESSAGE_TEMPLATE_FIELDS, prepare_application
from sender import DryRunEmailTransport, UnapprovedApplicationError, deliver_application


@pytest.fixture
def synthetic_profile(tmp_path) -> CandidateProfile:
    attachment = tmp_path / "cv_synthetic.pdf"
    attachment.write_bytes(b"synthetic reviewed CV bytes")
    return CandidateProfile(
        applicant_name="Alex Example",
        applicant_location="Nowhereville",
        applicant_summary="Fictional applicant used only for offline tests.",
        portfolio_url="https://example.invalid/portfolio/alex",
        linkedin_url="https://example.invalid/in/alex-example",
        skills={
            "Python": SkillEvidence("Python", EvidenceStatus.DEMONSTRATED),
            "Docker": SkillEvidence("Docker", EvidenceStatus.ADJACENT),
        },
        cv_variants={
            "default": CVVariant("default", str(attachment), "Fictional Role"),
        },
        message_variants={
            "concise": MessageVariant(
                "concise",
                subject_template="{role} application from {applicant_name}",
                body_template=(
                    "Hello {company} team,\n\n"
                    "I am {applicant_name}, {applicant_location}. "
                    "{applicant_summary} Skills: {skills}.\n"
                    "Portfolio: {portfolio_url} ({linkedin_url})."
                ),
            ),
        },
    )


@pytest.fixture
def synthetic_vacancy() -> JobVacancy:
    return JobVacancy(
        id="vac-synthetic-1",
        company="Example Corp",
        title="Python Developer",
        location="Remote",
        required_skills=("Python",),
        preferred_skills=("Docker",),
        contact_email="hiring@example.invalid",
    )


def test_explicit_message_variant_renders_and_is_recorded(
    synthetic_profile: CandidateProfile, synthetic_vacancy: JobVacancy
) -> None:
    package = prepare_application(
        synthetic_profile, synthetic_vacancy, message_variant_id="concise"
    )
    assert package.message_variant_id == "concise"
    assert package.subject == "Python Developer application from Alex Example"
    assert "Hello Example Corp team" in package.body
    assert "Skills: Python." in package.body
    assert package.status is ApplicationStatus.PREPARED


def test_omitted_variant_without_registry_keeps_default_message(
    synthetic_profile: CandidateProfile, synthetic_vacancy: JobVacancy
) -> None:
    profile = replace(synthetic_profile, message_variants={})
    package = prepare_application(profile, synthetic_vacancy)
    assert package.message_variant_id == "default"
    assert package.subject == "Python Developer - Application"
    assert package.body.startswith("Hi,")


def test_omitted_variant_selects_first_registered(
    synthetic_profile: CandidateProfile, synthetic_vacancy: JobVacancy
) -> None:
    package = prepare_application(synthetic_profile, synthetic_vacancy)
    assert package.message_variant_id == "concise"
    assert "Hello Example Corp team" in package.body


@pytest.mark.parametrize("variant_id", ["missing", ""])
def test_explicit_unknown_message_variant_does_not_fall_back(
    synthetic_profile: CandidateProfile, synthetic_vacancy: JobVacancy, variant_id: str
) -> None:
    for profile in (synthetic_profile, replace(synthetic_profile, message_variants={})):
        with pytest.raises(ValueError, match="Unknown message variant"):
            prepare_application(profile, synthetic_vacancy, message_variant_id=variant_id)


def test_unknown_template_placeholder_fails_fast(
    synthetic_profile: CandidateProfile, synthetic_vacancy: JobVacancy
) -> None:
    profile = replace(
        synthetic_profile,
        message_variants={
            "broken": MessageVariant(
                "broken", subject_template="Pay: {salary}?", body_template="Hi"
            )
        },
    )
    with pytest.raises(ValueError, match="field 'subject_template' is invalid"):
        prepare_application(profile, synthetic_vacancy, message_variant_id="broken")


def test_every_template_field_is_renderable(
    synthetic_profile: CandidateProfile, synthetic_vacancy: JobVacancy
) -> None:
    profile = replace(
        synthetic_profile,
        message_variants={
            "all-fields": MessageVariant(
                "all-fields",
                subject_template=" ".join(f"{{{name}}}" for name in MESSAGE_TEMPLATE_FIELDS),
                body_template="ok",
            )
        },
    )
    package = prepare_application(profile, synthetic_vacancy, message_variant_id="all-fields")
    assert "Alex Example" in package.subject
    assert "Nowhereville" in package.subject
    assert "Example Corp" in package.subject
    assert "Python Developer" in package.subject
    assert "Remote" in package.subject

    untitled = replace(synthetic_vacancy, title="")
    fallback = prepare_application(profile, untitled, message_variant_id="all-fields")
    assert "Python Developer" in fallback.subject


def test_changed_message_variant_id_cannot_use_old_approval(
    synthetic_profile: CandidateProfile, synthetic_vacancy: JobVacancy
) -> None:
    package = approve_package(
        prepare_application(synthetic_profile, synthetic_vacancy, message_variant_id="concise")
    )
    assert package.is_approved_for_sending() is True
    tampered = replace(package, message_variant_id="default")
    assert tampered.is_approved_for_sending() is False
    transport = DryRunEmailTransport()
    with pytest.raises(UnapprovedApplicationError):
        deliver_application(tampered, transport)
    assert not transport.sent_deliveries


def test_send_yields_structured_application_record(
    synthetic_profile: CandidateProfile, synthetic_vacancy: JobVacancy
) -> None:
    package = prepare_application(
        synthetic_profile, synthetic_vacancy, message_variant_id="concise"
    )
    approved = approve_package(package, approved_by="reviewer", notes="Synthetic review")
    transport = DryRunEmailTransport()
    delivered = deliver_application(approved, transport)
    assert delivered.status is ApplicationStatus.SENT
    assert delivered.send_receipt is not None
    assert delivered.send_receipt.success is True
    assert delivered.send_receipt.recipient == "hiring@example.invalid"
    assert delivered.send_receipt.timestamp_utc
    assert delivered.vacancy_ref == "vac-synthetic-1"
    assert delivered.contact_email == "hiring@example.invalid"
    assert delivered.cv_variant_id == "default"
    assert delivered.message_variant_id == "concise"
    assert delivered.created_at_utc
    assert transport.sent_deliveries[0]["to"] == "hiring@example.invalid"
