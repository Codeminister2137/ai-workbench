import os
import sys
from dataclasses import dataclass
from importlib import import_module
from typing import Any


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


def main() -> None:
    config = _load_config()
    sent_emails = _load_sent_emails(config.SENT_FILE)

    yagmail: Any = import_module("yagmail")
    yag = yagmail.SMTP(config.GMAIL_EMAIL, config.GMAIL_PASSWORD)
    emails = sys.argv[1:]
    print(emails)
    for email in emails:
        if email in sent_emails:
            print(f"Skipped {email}")
            continue
        yag.send(
            to=email,
            subject="Python Developer - Application",
            contents=_build_message(config),
            attachments=config.CV_ATTACHMENT,
        )
        with open(config.SENT_FILE, "a", encoding="utf-8") as f:
            f.write(email + "\n")
        sent_emails.add(email)


def _load_config() -> Config:
    required = {
        "GMAIL_EMAIL": os.getenv("GMAIL_EMAIL"),
        "GMAIL_PASSWORD": os.getenv("GMAIL_PASSWORD"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        names = ", ".join(missing)
        raise SystemExit(f"Missing required environment variable(s): {names}")
    return Config(
        GMAIL_EMAIL=required["GMAIL_EMAIL"] or "",
        GMAIL_PASSWORD=required["GMAIL_PASSWORD"] or "",
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


def _build_message(config: Config) -> str:
    return (
        "Hi,\n\n"
        "I came across your company while looking for teams working with modern backend "
        "technologies, and I wanted to reach out. "
        f"{config.APPLICANT_SUMMARY}\n"
        "I wanted to ask if you are currently looking to expand your team or might have "
        f"openings for a remote developer based in {config.APPLICANT_LOCATION}. "
        "I would be very excited to contribute to your projects and help your team grow. "
        "I have attached my CV for your review, and here is a link to my portfolio: "
        f"{config.PORTFOLIO_URL}\n"
        "Thank you for your time, and I look forward to hearing from you.\n\n"
        "Best regards,\n"
        f"{config.APPLICANT_NAME}\n"
        f"LinkedIn: {config.LINKEDIN_URL}"
    )


if __name__ == "__main__":
    main()
