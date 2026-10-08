"""Delivery transport abstractions and sending controls.

Enforces that unapproved applications can never be delivered, and decouples
message delivery from job preparation.
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol, runtime_checkable

from models import ApplicationPackage, ApplicationStatus, SendReceipt, utc_now_iso


class UnapprovedApplicationError(RuntimeError):
    """Raised when an attempt is made to deliver an unapproved application."""


@runtime_checkable
class EmailTransport(Protocol):
    """Protocol defining the application delivery transport interface."""

    def send(
        self,
        *,
        to_email: str,
        subject: str,
        contents: str,
        attachments: str,
    ) -> SendReceipt:
        """Deliver the email message and return a verifiable transmission receipt."""
        ...


class DryRunEmailTransport:
    """Offline/dry-run transport that validates inputs without network or SMTP calls."""

    def __init__(self, *, check_attachment_exists: bool = False) -> None:
        self.check_attachment_exists = check_attachment_exists
        self.sent_deliveries: list[dict[str, str]] = []

    def send(
        self,
        *,
        to_email: str,
        subject: str,
        contents: str,
        attachments: str,
    ) -> SendReceipt:
        if not to_email or "@" not in to_email:
            return SendReceipt(
                success=False,
                recipient=to_email,
                timestamp_utc=utc_now_iso(),
                error_message="Invalid recipient email address",
                transport_name="dry_run",
            )

        if self.check_attachment_exists and not os.path.exists(attachments):
            return SendReceipt(
                success=False,
                recipient=to_email,
                timestamp_utc=utc_now_iso(),
                error_message=f"Attachment file not found: {attachments}",
                transport_name="dry_run",
            )

        self.sent_deliveries.append(
            {
                "to": to_email,
                "subject": subject,
                "contents": contents,
                "attachments": attachments,
            }
        )
        return SendReceipt(
            success=True,
            recipient=to_email,
            timestamp_utc=utc_now_iso(),
            transport_name="dry_run",
        )


class YagmailEmailTransport:
    """Production SMTP transport using yagmail."""

    def __init__(self, gmail_email: str, gmail_password: str) -> None:
        self.gmail_email = gmail_email
        self.gmail_password = gmail_password

    def send(
        self,
        *,
        to_email: str,
        subject: str,
        contents: str,
        attachments: str,
    ) -> SendReceipt:
        try:
            from importlib import import_module
            from typing import Any

            yagmail: Any = import_module("yagmail")
            yag = yagmail.SMTP(self.gmail_email, self.gmail_password)
            yag.send(
                to=to_email,
                subject=subject,
                contents=contents,
                attachments=attachments,
            )
            return SendReceipt(
                success=True,
                recipient=to_email,
                timestamp_utc=utc_now_iso(),
                transport_name="yagmail",
            )
        except Exception as exc:  # noqa: BLE001
            return SendReceipt(
                success=False,
                recipient=to_email,
                timestamp_utc=utc_now_iso(),
                error_message=str(exc),
                transport_name="yagmail",
            )


def deliver_application(
    package: ApplicationPackage,
    transport: EmailTransport,
    *,
    require_approval: bool = True,
) -> ApplicationPackage:
    """Deliver an application package via the supplied transport.

    Approval cannot be disabled. The legacy keyword is retained only to reject
    bypass attempts explicitly. Delivery uses a temporary copy of verified bytes
    so changes to the original attachment after validation cannot change the send.
    """
    try:
        attachment = Path(package.cv_attachment_path).read_bytes()
    except OSError:
        attachment = None
    if (
        require_approval is not True
        or attachment is None
        or not package.approves_materials(attachment)
    ):
        raise UnapprovedApplicationError(
            f"Application package {package.application_id!r} for {package.contact_email!r} "
            f"cannot be sent without explicit human approval (status={package.status.value})."
        )

    with TemporaryDirectory(prefix="approved-application-") as directory:
        snapshot = Path(directory) / Path(package.cv_attachment_path).name
        snapshot.write_bytes(attachment)
        receipt = transport.send(
            to_email=package.contact_email,
            subject=package.subject,
            contents=package.body,
            attachments=str(snapshot),
        )

    new_status = ApplicationStatus.SENT if receipt.success else ApplicationStatus.FAILED
    return replace(
        package,
        status=new_status,
        send_receipt=receipt,
    )
