"""Reusable terminal review workflow for explicitly addressed recruiter outreach."""

import argparse
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass, replace
from email.utils import parseaddr
from pathlib import Path

import records
from approval import approve_package
from models import ApplicationPackage, ApplicationStatus, CandidateProfile, CVVariant, JobVacancy
from preparation import prepare_application
from sender import UnapprovedApplicationError, YagmailEmailTransport, deliver_application
from vendor_sources import default_contact_registry


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
    RECORDS_FILE: str = "application_records.jsonl"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "recipients",
        nargs="*",
        help="Explicit recipient email addresses (or use --vacancies)",
    )
    parser.add_argument(
        "--send", action="store_true", help="Ask for approval and send each package"
    )
    parser.add_argument(
        "--message-variant",
        default=None,
        help="Explicit message variant id; unknown ids fail without fallback",
    )
    parser.add_argument(
        "--cv-variant",
        default=None,
        help="Explicit CV variant id; unknown ids fail without fallback",
    )
    parser.add_argument(
        "--vacancies",
        default=None,
        help="JSONL vacancy batch; each line resolves to one recipient",
    )
    parser.add_argument(
        "--max-enriches",
        type=int,
        default=25,
        help="Cap on vendor consults for --vacancies (default 25)",
    )
    args = parser.parse_args(argv)
    if not args.recipients and not args.vacancies:
        parser.error("need recipients or --vacancies")
    return run_outreach(
        _load_config(),
        args.recipients,
        send=args.send,
        message_variant_id=args.message_variant,
        cv_variant_id=args.cv_variant,
        vacancies_path=args.vacancies,
        max_enriches=args.max_enriches,
    )


def run_outreach(
    config: Config,
    recipients: Sequence[str],
    *,
    send: bool = False,
    message_variant_id: str | None = None,
    cv_variant_id: str | None = None,
    vacancies_path: str | None = None,
    max_enriches: int = 25,
) -> int:
    """Review explicit contacts and record only successful guarded deliveries.

    ``vacancies_path`` resolves a JSONL vacancy batch to recipients
    through the contact registry before the same review loop.
    """
    jobs: list[JobVacancy] = [
        JobVacancy(
            id=f"outreach:{email}",
            company="",
            title="Python Developer",
            location="",
            contact_email=email,
            source="manual-outreach",
        )
        for email in recipients
    ]
    if vacancies_path:
        try:
            jobs.extend(_resolve_vacancy_file(vacancies_path, max_enriches))
        except OSError as exc:
            print(f"Cannot read vacancies file {vacancies_path}: {exc}")
            return 1
    sent_emails = _load_sent_emails(config.SENT_FILE)
    seen = set(sent_emails)
    profile = _candidate_profile(config)
    failed = False
    for job in jobs:
        email = job.contact_email or ""
        if parseaddr(email)[1] != email or "@" not in email or any(c.isspace() for c in email):
            print(f"Invalid recipient: {email!r}")
            failed = True
            continue
        if email in seen:
            print(f"Skipped {email}")
            continue
        seen.add(email)
        try:
            package = prepare_application(
                profile,
                job,
                message_variant_id=message_variant_id,
                cv_variant_id=cv_variant_id,
            )
        except ValueError as exc:
            print(f"Cannot prepare application for {email}: {exc}; no delivery attempted.")
            failed = True
            continue
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
        try:
            records.append_application_record(config.RECORDS_FILE, delivered)
        except OSError:
            print(
                f"Sent to {email} and recorded in sent history, "
                f"but the application record was not saved. Stop and reconcile {config.RECORDS_FILE}."
            )
            return 1
        print(f"Sent to {email}")
    return int(failed)


def _resolve_vacancy_file(path: str, max_enriches: int) -> list[JobVacancy]:
    """Resolve a JSONL vacancy batch to recipient vacancies.

    Each line needs ``id`` and ``company``; optional ``title``,
    ``location``, ``contact_email``, ``recruiter_name``, ``source``.
    Resolution goes through the default registry (manual first, then
    ready vendors); vendor consults stop at ``max_enriches``. Every
    vacancy is reported: queued, unresolved, malformed, or skipped
    on budget.
    """
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    registry = default_contact_registry()
    queued: list[JobVacancy] = []
    spent = 0
    total = queued_count = unresolved = malformed = skipped_budget = 0
    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        total += 1
        try:
            raw = json.loads(line)
        except ValueError:
            malformed += 1
            print(f"vacancies:{lineno}: malformed JSON; skipped.")
            continue
        if not isinstance(raw, dict) or not raw.get("id") or not raw.get("company"):
            malformed += 1
            print(f"vacancies:{lineno}: needs 'id' and 'company'; skipped.")
            continue
        if spent >= max_enriches:
            skipped_budget += 1
            continue
        vacancy = JobVacancy(
            id=str(raw["id"]),
            company=str(raw["company"]),
            title=str(raw.get("title") or "Python Developer"),
            location=str(raw.get("location") or ""),
            contact_email=str(raw.get("contact_email") or "") or None,
            source=str(raw.get("source") or "vacancies-file"),
            recruiter_name=str(raw.get("recruiter_name") or "") or None,
        )
        proposal, tried = registry.resolve_trace(vacancy)
        spent += sum(1 for name in tried if name != "manual")
        if proposal is None:
            unresolved += 1
            print(f"vac:{vacancy.id}: unresolved (tried: {', '.join(tried)}).")
            continue
        queued_count += 1
        via = "manual (free)" if proposal.source.startswith("manual:") else proposal.source
        print(f"vac:{vacancy.id} -> {proposal.email} (via {via}).")
        queued.append(replace(vacancy, contact_email=proposal.email))
    print(
        f"vacancies: {total} total, {queued_count} queued, {unresolved} unresolved, "
        f"{malformed} malformed, {skipped_budget} skipped on budget, "
        f"{spent}/{max_enriches} vendor consults."
    )
    return queued


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
        RECORDS_FILE=os.getenv("RECORDS_FILE", Config.RECORDS_FILE),
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
    print(f"CV variant: {package.cv_variant_id}\nMessage variant: {package.message_variant_id}")
    print(f"Attachment: {package.cv_attachment_path}\nMaterials SHA-256: {digest}")
    print(package.body)


if __name__ == "__main__":
    raise SystemExit(main())
