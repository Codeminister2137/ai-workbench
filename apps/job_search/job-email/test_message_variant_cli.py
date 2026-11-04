"""CLI selection of the outreach message variant.

The ``--message-variant`` flag passes an explicit variant id through to
``prepare_application``: unknown ids fail without fallback or side effects,
while a registered variant renders its subject/body for review and sending.
All fixtures are obviously synthetic.
"""

from __future__ import annotations

from pathlib import Path

import outreach_cli as cli
import pytest
from models import (
    CandidateProfile,
    CVVariant,
    MessageVariant,
    SendReceipt,
    utc_now_iso,
)


@pytest.fixture
def outreach(monkeypatch, tmp_path):
    attachment = tmp_path / "cv.pdf"
    attachment.write_bytes(b"reviewed CV")
    history = tmp_path / "sent.txt"
    monkeypatch.setenv("CV_ATTACHMENT", str(attachment))
    monkeypatch.setenv("SENT_FILE", str(history))
    monkeypatch.setenv("GMAIL_EMAIL", "sender@example.invalid")
    monkeypatch.setenv("GMAIL_PASSWORD", "synthetic-secret")
    calls = []
    connections = []

    class Transport:
        def __init__(self, email, password):
            connections.append(email)

        def send(self, *, to_email, subject, contents, attachments):
            calls.append((to_email, subject, contents, Path(attachments).read_bytes()))
            return SendReceipt(True, to_email, utc_now_iso(), transport_name="synthetic")

    monkeypatch.setattr(cli, "YagmailEmailTransport", Transport)
    return attachment, history, calls, connections


def _profile_with_variant(config: cli.Config, attachment: Path) -> CandidateProfile:
    return CandidateProfile(
        applicant_name=config.APPLICANT_NAME,
        applicant_location=config.APPLICANT_LOCATION,
        applicant_summary=config.APPLICANT_SUMMARY,
        portfolio_url=config.PORTFOLIO_URL,
        linkedin_url=config.LINKEDIN_URL,
        cv_variants={"default": CVVariant("default", str(attachment), "Fictional Role")},
        message_variants={
            "concise": MessageVariant(
                "concise",
                subject_template="{role} application from {applicant_name}",
                body_template="Hello {company} team, I am {applicant_name}. Skills: {skills}.",
            ),
        },
    )


def test_default_preview_shows_default_variant_ids(outreach, monkeypatch, capsys):
    _, history, calls, connections = outreach
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("Preview asked for approval"))
    assert cli.main(["recruiter@example.invalid"]) == 0
    output = capsys.readouterr().out
    assert "CV variant: default" in output
    assert "Message variant: default" in output
    assert "Subject: Python Developer - Application" in output
    assert "Hi," in output
    assert not calls and not connections and not history.exists()


@pytest.mark.parametrize("variant_id", ["missing", ""])
@pytest.mark.parametrize("extra", [[], ["--send"]])
def test_unknown_message_variant_has_no_effects(outreach, monkeypatch, variant_id, extra, capsys):
    _, history, calls, connections = outreach
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("Unknown variant prompted"))
    argv = [*extra, "--message-variant", variant_id, "recruiter@example.invalid"]
    assert cli.main(argv) == 1
    assert "Unknown message variant" in capsys.readouterr().out
    assert not calls and not connections and not history.exists()


def test_unknown_variant_does_not_stop_other_recipients(outreach, monkeypatch, capsys):
    _, history, calls, _ = outreach
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("Preview asked for approval"))
    assert cli.main(["--message-variant", "missing", "good@example.invalid"]) == 1
    assert "Cannot prepare application for good@example.invalid" in capsys.readouterr().out
    assert not calls and not history.exists()


def test_known_variant_renders_in_preview(outreach, monkeypatch, capsys):
    attachment, history, calls, connections = outreach
    monkeypatch.setattr(
        cli, "_candidate_profile", lambda config: _profile_with_variant(config, attachment)
    )
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("Preview asked for approval"))
    assert cli.main(["--message-variant", "concise", "recruiter@example.invalid"]) == 0
    output = capsys.readouterr().out
    assert "Message variant: concise" in output
    assert "Python Developer application from Your Name" in output
    assert "Hello  team, I am Your Name." in output
    assert not calls and not connections and not history.exists()


def test_known_variant_flows_through_approval_and_delivery(outreach, monkeypatch):
    attachment, history, calls, connections = outreach
    monkeypatch.setattr(
        cli, "_candidate_profile", lambda config: _profile_with_variant(config, attachment)
    )
    monkeypatch.setattr("builtins.input", lambda *args: "send recruiter@example.invalid")
    argv = ["--send", "--message-variant", "concise", "recruiter@example.invalid"]
    assert cli.main(argv) == 0
    assert len(calls) == len(connections) == 1
    assert calls[0][0] == "recruiter@example.invalid"
    assert calls[0][1] == "Python Developer application from Your Name"
    assert "Hello  team, I am Your Name." in calls[0][2]
    assert history.read_text() == "recruiter@example.invalid\n"


def test_broken_template_variant_fails_without_effects(outreach, monkeypatch, capsys):
    attachment, history, calls, connections = outreach

    def broken_profile(config: cli.Config) -> CandidateProfile:
        profile = _profile_with_variant(config, attachment)
        variants = dict(profile.message_variants)
        variants["broken"] = MessageVariant(
            "broken", subject_template="Pay: {salary}?", body_template="Hi"
        )
        return CandidateProfile(
            applicant_name=profile.applicant_name,
            applicant_location=profile.applicant_location,
            applicant_summary=profile.applicant_summary,
            portfolio_url=profile.portfolio_url,
            linkedin_url=profile.linkedin_url,
            skills=profile.skills,
            cv_variants=profile.cv_variants,
            message_variants=variants,
        )

    monkeypatch.setattr(cli, "_candidate_profile", broken_profile)
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("Broken variant prompted"))
    argv = ["--send", "--message-variant", "broken", "recruiter@example.invalid"]
    assert cli.main(argv) == 1
    assert "field 'subject_template' is invalid" in capsys.readouterr().out
    assert not calls and not connections and not history.exists()
