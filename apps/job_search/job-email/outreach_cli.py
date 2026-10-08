"""Reusable terminal review workflow for explicitly addressed recruiter outreach."""

import argparse
import os
from collections.abc import Sequence
from dataclasses import dataclass
from email.utils import parseaddr
from pathlib import Path

from approval import approve_package
from models import ApplicationPackage, ApplicationStatus, CandidateProfile, CVVariant, JobVacancy
from preparation import prepare_application
from sender import UnapprovedApplicationError, YagmailEmailTransport, deliver_application


@dataclass(frozen=True)
class Config:
    GMAIL_PASSWORD: str
    GMAIL_EMAIL: str
    APPLICANT_NAME: str = "Your Name"
    APPLICANT_LOCATION: str = "your location"
    APPLICANT_SUMMARY: str = (
        "I am a Python developer with experience in backend development and AI tooling."
    )
    PORTFOLIO_URL: str = "https://github.com/your-user"
    LINKEDIN_URL: str = "https://www.linkedin.com/in/your-profile"
    CV_ATTACHMENT: str = "cv.pdf"
    SENT_FILE: str = "sent_emails.txt"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recipients", nargs="+", help="Explicit recipient email addresses")
    parser.add_argument(
        "--send", action="store_true", help="Ask for approval and send each package"
    )
    args = parser.parse_args(argv)
    return run_outreach(_load_config(), args.recipients, send=args.send)


def run_outreach(config: Config, recipients: Sequence[str], *, send: bool = False) -> int:
    """Review explicit contacts and record only successful guarded deliveries."""
    sent_emails = _load_sent_emails(config.SENT_FILE)
    seen = set(sent_emails)
    profile = _candidate_profile(config)
    failed = False
    for email in recipients:
        if parseaddr(email)[1] != email or "@" not in email or any(c.isspace() for c in email):
            print(f"Invalid recipient: {email!r}")
            failed = True
            continue
        if email in seen:
            print(f"Skipped {email}")
            continue
        seen.add(email)
        package = prepare_application(
            profile,
            JobVacancy(
                id=f"outreach:{email}",
                company="",
                title="Python Developer",
                location="",
                contact_email=email,
                source="manual-outreach",
            ),
        )
        try:
            reviewed_digest = package.materials_digest(
                Path(package.cv_attachment_path).read_bytes()
            )
        except OSError:
            print(f"Cannot read attachment for {email}; no delivery attempted.")
            failed = True
            continue
        _print_preview(package, reviewed_digest)
        if not send:
            continue
        try:
            confirmation = input(f"Type 'send {email}' to approve this package, or Enter to skip: ")
        except (EOFError, KeyboardInterrupt):
            print("Review cancelled; no further delivery attempted.")
            break
        if confirmation != f"send {email}":
            print(f"Not approved: {email}")
            continue
        try:
            approved = approve_package(package, notes="Explicit terminal review")
            if approved.approved_materials_sha256 != reviewed_digest:
                print(f"Materials changed during review for {email}; run a fresh preview.")
                failed = True
                continue
            if not config.GMAIL_EMAIL or not config.GMAIL_PASSWORD:
                print("Sending requires GMAIL_EMAIL and GMAIL_PASSWORD; no delivery attempted.")
                failed = True
                continue
            delivered = deliver_application(
                approved, YagmailEmailTransport(config.GMAIL_EMAIL, config.GMAIL_PASSWORD)
            )
        except (OSError, UnapprovedApplicationError):
            print(f"Reviewed materials unavailable or changed for {email}; no delivery attempted.")
            failed = True
            continue
        if delivered.status is not ApplicationStatus.SENT:
            print(f"Delivery failed for {email}; sent history was not changed.")
            failed = True
            continue
        # A ledger failure after SMTP success must stop the batch: retrying could duplicate a send.
        try:
            with open(config.SENT_FILE, "a", encoding="utf-8") as history:
                history.write(email + "\n")
        except OSError:
            print(f"Sent to {email}, but recording failed. Stop and reconcile sent history.")
            return 1
        print(f"Sent to {email}")
    return int(failed)


def _load_config() -> Config:
    return Config(
        GMAIL_EMAIL=os.getenv("GMAIL_EMAIL", ""),
        GMAIL_PASSWORD=os.getenv("GMAIL_PASSWORD", ""),
        APPLICANT_NAME=os.getenv("APPLICANT_NAME", Config.APPLICANT_NAME),
        APPLICANT_LOCATION=os.getenv("APPLICANT_LOCATION", Config.APPLICANT_LOCATION),
        APPLICANT_SUMMARY=os.getenv("APPLICANT_SUMMARY", Config.APPLICANT_SUMMARY),
        PORTFOLIO_URL=os.getenv("PORTFOLIO_URL", Config.PORTFOLIO_URL),
        LINKEDIN_URL=os.getenv("LINKEDIN_URL", Config.LINKEDIN_URL),
        CV_ATTACHMENT=os.getenv("CV_ATTACHMENT", Config.CV_ATTACHMENT),
        SENT_FILE=os.getenv("SENT_FILE", Config.SENT_FILE),
    )


def _load_sent_emails(path: str) -> set[str]:
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def _candidate_profile(config: Config) -> CandidateProfile:
    return CandidateProfile(
        applicant_name=config.APPLICANT_NAME,
        applicant_location=config.APPLICANT_LOCATION,
        applicant_summary=config.APPLICANT_SUMMARY,
        portfolio_url=config.PORTFOLIO_URL,
        linkedin_url=config.LINKEDIN_URL,
        cv_variants={"default": CVVariant("default", config.CV_ATTACHMENT, "Python Developer")},
    )


def _print_preview(package: ApplicationPackage, digest: str) -> None:
    print(f"To: {package.contact_email}\nSubject: {package.subject}")
    print(f"Attachment: {package.cv_attachment_path}\nMaterials SHA-256: {digest}")
    print(package.body)


if __name__ == "__main__":
    raise SystemExit(main())
