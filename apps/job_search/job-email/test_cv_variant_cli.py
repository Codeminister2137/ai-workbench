"""CLI selection of the outreach CV variant.

The ``--cv-variant`` flag passes an explicit variant id through to
``prepare_application``: unknown ids fail without fallback or side effects,
while a registered variant selects its attachment for review and sending.
All fixtures are obviously synthetic.
"""

from __future__ import annotations

from pathlib import Path

import outreach_cli as cli
import pytest
from models import (
    CandidateProfile,
    CVVariant,
    SendReceipt,
    utc_now_iso,
)


@pytest.fixture
def outreach(monkeypatch, tmp_path):
    attachment = tmp_path / "cv.pdf"
    attachment.write_bytes(b"reviewed CV")
    alternate = tmp_path / "cv_alternate.pdf"
    alternate.write_bytes(b"synthetic alternate CV")
    history = tmp_path / "sent.txt"
    monkeypatch.setenv("CV_ATTACHMENT", str(attachment))
    monkeypatch.setenv("SENT_FILE", str(history))
    monkeypatch.setenv("RECORDS_FILE", str(tmp_path / "records.jsonl"))
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
    return attachment, alternate, history, calls, connections


def _profile_with_variants(
    config: cli.Config, attachment: Path, alternate: Path
) -> CandidateProfile:
    return CandidateProfile(
        applicant_name=config.APPLICANT_NAME,
        applicant_location=config.APPLICANT_LOCATION,
        applicant_summary=config.APPLICANT_SUMMARY,
        portfolio_url=config.PORTFOLIO_URL,
        linkedin_url=config.LINKEDIN_URL,
        cv_variants={
            "default": CVVariant("default", str(attachment), "Fictional Role"),
            "alternate": CVVariant("alternate", str(alternate), "Alternate Role"),
        },
    )


def test_explicit_default_cv_variant_renders_in_preview(outreach, monkeypatch, capsys):
    _, _, history, calls, connections = outreach
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("Preview asked for approval"))
    assert cli.main(["--cv-variant", "default", "recruiter@example.invalid"]) == 0
    output = capsys.readouterr().out
    assert "CV variant: default" in output
    assert not calls and not connections and not history.exists()


@pytest.mark.parametrize("variant_id", ["missing", ""])
@pytest.mark.parametrize("extra", [[], ["--send"]])
def test_unknown_cv_variant_has_no_effects(outreach, monkeypatch, variant_id, extra, capsys):
    _, _, history, calls, connections = outreach
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("Unknown variant prompted"))
    argv = [*extra, "--cv-variant", variant_id, "recruiter@example.invalid"]
    assert cli.main(argv) == 1
    assert "Unknown CV variant" in capsys.readouterr().out
    assert not calls and not connections and not history.exists()


def test_known_cv_variant_selects_attachment_through_delivery(outreach, monkeypatch):
    attachment, alternate, history, calls, _ = outreach
    monkeypatch.setattr(
        cli,
        "_candidate_profile",
        lambda config: _profile_with_variants(config, attachment, alternate),
    )
    monkeypatch.setattr("builtins.input", lambda *args: "send recruiter@example.invalid")
    argv = ["--send", "--cv-variant", "alternate", "recruiter@example.invalid"]
    assert cli.main(argv) == 0
    assert len(calls) == 1
    assert calls[0][0] == "recruiter@example.invalid"
    assert calls[0][3] == b"synthetic alternate CV"
    assert history.read_text() == "recruiter@example.invalid\n"
