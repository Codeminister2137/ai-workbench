"""Application package preparation and tailoring workflow.

Separates message/materials preparation from human approval and final sending.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence

from evidence import ProhibitedClaimError, analyze_vacancy_fit, verify_application_claims
from models import (
    ApplicationPackage,
    ApplicationStatus,
    CandidateProfile,
    JobVacancy,
    MessageVariant,
    utc_now_iso,
)

MESSAGE_TEMPLATE_FIELDS = (
    "applicant_name",
    "applicant_location",
    "applicant_summary",
    "portfolio_url",
    "linkedin_url",
    "company",
    "role",
    "location",
    "skills",
)
"""Fixed placeholder set accepted in ``MessageVariant`` templates."""


def render_message_template(
    template: str, values: Mapping[str, str], *, variant_id: str, field_name: str
) -> str:
    """Render one message template against the fixed placeholder mapping.

    Raises ValueError naming the variant and field when the template uses an
    unknown placeholder or malformed format syntax.
    """
    try:
        return template.format_map(values)
    except (KeyError, IndexError, ValueError) as exc:
        raise ValueError(
            f"Message variant {variant_id!r} field {field_name!r} is invalid: {exc}. "
            f"Available placeholders: {', '.join(MESSAGE_TEMPLATE_FIELDS)}."
        ) from exc


def _template_values(
    profile: CandidateProfile,
    vacancy: JobVacancy | None,
    highlighted_skills: Sequence[str],
) -> dict[str, str]:
    """Build the fixed placeholder mapping for message template rendering."""
    return {
        "applicant_name": profile.applicant_name,
        "applicant_location": profile.applicant_location,
        "applicant_summary": profile.applicant_summary,
        "portfolio_url": profile.portfolio_url,
        "linkedin_url": profile.linkedin_url,
        "company": vacancy.company if vacancy else "",
        "role": vacancy.title if vacancy and vacancy.title else "Python Developer",
        "location": vacancy.location if vacancy else "",
        "skills": ", ".join(highlighted_skills),
    }


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
    message_variant_id: str | None = None,
    explicit_claims: Sequence[str] = (),
    strict_evidence: bool = True,
) -> ApplicationPackage:
    """Prepare a verified application package for a vacancy.

    Validates that any explicitly claimed skills exist in the candidate's
    evidence profile. Fails fast with ProhibitedClaimError if an ungrounded
    claim is detected under strict mode. An explicitly requested unknown CV
    variant raises ValueError rather than selecting another document. Message
    variants follow the same rule: an explicitly requested unknown message
    variant raises ValueError, while an omitted selection renders the first
    registered variant or the built-in default message.
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
    if cv_variant_id is not None:
        if cv_variant_id not in profile.cv_variants:
            raise ValueError(f"Unknown CV variant: {cv_variant_id!r}")
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

    message_variant: MessageVariant | None
    message_key = "default"
    if message_variant_id is not None:
        if message_variant_id not in profile.message_variants:
            raise ValueError(f"Unknown message variant: {message_variant_id!r}")
        message_variant = profile.message_variants[message_variant_id]
        message_key = message_variant_id
    elif profile.message_variants:
        message_variant = next(iter(profile.message_variants.values()))
        message_key = message_variant.variant_id
    else:
        message_variant = None

    if message_variant is None:
        subject = build_default_subject(profile, vacancy)
        body = build_default_message(profile, vacancy, highlighted_skills=highlighted)
    else:
        values = _template_values(profile, vacancy, highlighted)
        subject = render_message_template(
            message_variant.subject_template,
            values,
            variant_id=message_key,
            field_name="subject_template",
        )
        body = render_message_template(
            message_variant.body_template,
            values,
            variant_id=message_key,
            field_name="body_template",
        )

    # Generate a deterministic unique ID for the application package
    app_seed = (
        f"{vacancy.id}:{vacancy.contact_email}:{variant_key}:{message_key}:{subject}".encode()
    )
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
        message_variant_id=message_key,
        status=ApplicationStatus.PREPARED,
        created_at_utc=utc_now_iso(),
    )
