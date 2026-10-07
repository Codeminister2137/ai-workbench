"""Application package preparation and tailoring workflow.

Separates message/materials preparation from human approval and final sending.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from evidence import ProhibitedClaimError, analyze_vacancy_fit, verify_application_claims
from models import (
    ApplicationPackage,
    ApplicationStatus,
    CandidateProfile,
    JobVacancy,
    utc_now_iso,
)


def build_default_message(
    profile: CandidateProfile,
    vacancy: JobVacancy | None = None,
    highlighted_skills: Sequence[str] = (),
) -> str:
    """Build a professional, tailored outreach email body grounded in candidate evidence."""
    company_phrase = (
        f"at {vacancy.company}" if vacancy and vacancy.company else "with modern technologies"
    )
    location_phrase = f"based in {profile.applicant_location}"

    skills_text = ""
    if highlighted_skills:
        skills_joined = ", ".join(highlighted_skills)
        skills_text = f" My experience includes work with {skills_joined}."

    return (
        "Hi,\n\n"
        f"I came across your team while looking for teams working {company_phrase}, "
        "and I wanted to reach out. "
        f"{profile.applicant_summary}{skills_text}\n\n"
        "I wanted to ask if you are currently looking to expand your team or might have "
        f"openings for a remote developer {location_phrase}. "
        "I would be very excited to contribute to your projects and help your team grow. "
        "I have attached my CV for your review, and here is a link to my portfolio: "
        f"{profile.portfolio_url}\n\n"
        "Thank you for your time, and I look forward to hearing from you.\n\n"
        "Best regards,\n"
        f"{profile.applicant_name}\n"
        f"LinkedIn: {profile.linkedin_url}"
    )


def build_default_subject(
    profile: CandidateProfile,
    vacancy: JobVacancy | None = None,
) -> str:
    """Build a clean, relevant subject line."""
    role = vacancy.title if vacancy and vacancy.title else "Python Developer"
    return f"{role} - Application"


def prepare_application(
    profile: CandidateProfile,
    vacancy: JobVacancy,
    *,
    cv_variant_id: str | None = None,
    explicit_claims: Sequence[str] = (),
    strict_evidence: bool = True,
) -> ApplicationPackage:
    """Prepare a verified application package for a vacancy.

    Validates that any explicitly claimed skills exist in the candidate's
    evidence profile. Fails fast with ProhibitedClaimError if an ungrounded
    claim is detected under strict mode.
    """
    if explicit_claims:
        verification = verify_application_claims(explicit_claims, profile, strict=strict_evidence)
        if not verification.is_valid:
            prohibited_str = ", ".join(verification.prohibited_claims)
            raise ProhibitedClaimError(
                f"Cannot prepare application with prohibited/fabricated claims: {prohibited_str}"
            )

    # Determine CV attachment
    cv_attachment = "cv.pdf"
    variant_key = "default"
    if cv_variant_id and cv_variant_id in profile.cv_variants:
        variant = profile.cv_variants[cv_variant_id]
        cv_attachment = variant.file_path
        variant_key = cv_variant_id
    elif profile.cv_variants:
        # Default to the first available variant
        first_variant = next(iter(profile.cv_variants.values()))
        cv_attachment = first_variant.file_path
        variant_key = first_variant.variant_id

    fit = analyze_vacancy_fit(vacancy, profile)
    highlighted = fit.matched_skills[:3] if fit.matched_skills else ()

    subject = build_default_subject(profile, vacancy)
    body = build_default_message(profile, vacancy, highlighted_skills=highlighted)

    # Generate a deterministic unique ID for the application package
    app_seed = f"{vacancy.id}:{vacancy.contact_email}:{variant_key}:{subject}".encode()
    app_id = hashlib.sha256(app_seed).hexdigest()[:12]

    recipient = vacancy.contact_email or ""

    return ApplicationPackage(
        application_id=app_id,
        vacancy_ref=vacancy.id,
        contact_email=recipient,
        cv_attachment_path=cv_attachment,
        subject=subject,
        body=body,
        cv_variant_id=variant_key,
        status=ApplicationStatus.PREPARED,
        created_at_utc=utc_now_iso(),
    )
