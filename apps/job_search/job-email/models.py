"""Domain models and schemas for job search automation and application workflows.

Implements the normalized job schema, candidate evidence profile, and application
package contracts required by the Job Search Automation plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class WorkMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNSPECIFIED = "unspecified"


class EmploymentType(StrEnum):
    B2B = "b2b"
    PERMANENT = "permanent"
    CONTRACT = "contract"
    UNSPECIFIED = "unspecified"


class EvidenceStatus(StrEnum):
    DEMONSTRATED = "demonstrated"
    ADJACENT = "adjacent"
    LEARNING = "learning"
    ABSENT = "absent"


class ApplicationStatus(StrEnum):
    PREPARED = "prepared"
    APPROVED = "approved"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


def utc_now_iso() -> str:
    """Return the current UTC timestamp formatted as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class SkillEvidence:
    """Evidence record for a single skill or claim in the candidate profile.

    Ensures that qualifications are never invented without verifiable backing.
    """

    skill_name: str
    status: EvidenceStatus
    notes: str = ""
    evidence_sources: tuple[str, ...] = ()

    def is_claim_permitted(self) -> bool:
        """Return True if this skill is backed by demonstrated or adjacent evidence."""
        return self.status in (EvidenceStatus.DEMONSTRATED, EvidenceStatus.ADJACENT)


@dataclass(frozen=True, slots=True)
class CVVariant:
    """A legitimate, verifiable CV variant targeting specific role types."""

    variant_id: str
    file_path: str
    target_role: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class CandidateProfile:
    """Structured candidate profile acting as the source of truth for applications."""

    applicant_name: str
    applicant_location: str
    applicant_summary: str
    portfolio_url: str
    linkedin_url: str
    skills: dict[str, SkillEvidence] = field(default_factory=dict)
    cv_variants: dict[str, CVVariant] = field(default_factory=dict)

    def get_skill_status(self, skill_name: str) -> EvidenceStatus:
        """Return the evidence status for a skill, defaulting to ABSENT if unrecorded."""
        key = skill_name.strip().lower()
        for name, evidence in self.skills.items():
            if name.strip().lower() == key:
                return evidence.status
        return EvidenceStatus.ABSENT


@dataclass(frozen=True, slots=True)
class JobVacancy:
    """Internal normalized vacancy schema for consistent representation."""

    id: str
    company: str
    title: str
    location: str
    work_mode: WorkMode = WorkMode.UNSPECIFIED
    employment_type: EmploymentType = EmploymentType.UNSPECIFIED
    compensation: str | None = None
    description: str = ""
    required_skills: tuple[str, ...] = ()
    preferred_skills: tuple[str, ...] = ()
    experience_requirement: str | None = None
    source: str = "manual"
    source_url: str | None = None
    contact_email: str | None = None
    recruiter_name: str | None = None
    raw_content: str = ""
    created_at_utc: str = field(default_factory=utc_now_iso)
    duplicate_key: str = ""


@dataclass(frozen=True, slots=True)
class SendReceipt:
    """Record of an application transmission attempt."""

    success: bool
    recipient: str
    timestamp_utc: str
    error_message: str | None = None
    transport_name: str = "yagmail"


@dataclass(frozen=True, slots=True)
class ApplicationPackage:
    """A prepared, tailored application unit separating preparation from sending."""

    application_id: str
    vacancy_ref: str
    contact_email: str
    cv_attachment_path: str
    subject: str
    body: str
    cv_variant_id: str = "default"
    status: ApplicationStatus = ApplicationStatus.PREPARED
    created_at_utc: str = field(default_factory=utc_now_iso)
    approved_at_utc: str | None = None
    approved_by: str | None = None
    approval_notes: str | None = None
    send_receipt: SendReceipt | None = None

    def is_approved_for_sending(self) -> bool:
        """Verify that human approval was explicitly granted before delivery."""
        return self.status is ApplicationStatus.APPROVED and self.approved_at_utc is not None
