"""Human approval workflows and package modification before transmission.

Implements Phase 4 of the Job Search plan: strictly enforces that no application
can be delivered without explicit, recorded human approval.
"""

from __future__ import annotations

from dataclasses import replace

from models import ApplicationPackage, ApplicationStatus, utc_now_iso


class ApplicationLifecycleError(RuntimeError):
    """Raised when an operation violates the application state lifecycle."""


def approve_package(
    package: ApplicationPackage,
    *,
    approved_by: str = "operator",
    notes: str = "",
) -> ApplicationPackage:
    """Explicitly grant human approval for a prepared application package."""
    if package.status is ApplicationStatus.SENT:
        raise ApplicationLifecycleError("Cannot approve an already-sent application package.")
    if package.status is ApplicationStatus.SKIPPED:
        raise ApplicationLifecycleError("Cannot approve an explicitly rejected/skipped package.")

    return replace(
        package,
        status=ApplicationStatus.APPROVED,
        approved_at_utc=utc_now_iso(),
        approved_by=approved_by,
        approval_notes=notes,
    )


def reject_package(
    package: ApplicationPackage,
    *,
    reason: str,
) -> ApplicationPackage:
    """Explicitly reject a prepared application package, preventing sending."""
    if package.status is ApplicationStatus.SENT:
        raise ApplicationLifecycleError("Cannot reject an already-sent application package.")

    return replace(
        package,
        status=ApplicationStatus.SKIPPED,
        approval_notes=f"Rejected: {reason}",
    )


def update_package_content(
    package: ApplicationPackage,
    *,
    subject: str | None = None,
    body: str | None = None,
    cv_attachment_path: str | None = None,
) -> ApplicationPackage:
    """Update application content before approval.

    If the package was already approved, modifying content revokes approval
    to require fresh review of the modified material.
    """
    if package.status is ApplicationStatus.SENT:
        raise ApplicationLifecycleError("Cannot edit an already-sent application package.")

    updates: dict[str, object] = {}
    if subject is not None:
        updates["subject"] = subject
    if body is not None:
        updates["body"] = body
    if cv_attachment_path is not None:
        updates["cv_attachment_path"] = cv_attachment_path

    # Any modification after approval revokes approval for safety
    if package.status is ApplicationStatus.APPROVED:
        updates["status"] = ApplicationStatus.PREPARED
        updates["approved_at_utc"] = None
        updates["approved_by"] = None

    return replace(package, **updates)
