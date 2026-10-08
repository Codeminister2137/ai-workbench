"""Terminal outreach must preserve review and delivery boundaries."""

from pathlib import Path

import outreach_cli as cli
import pytest
from models import SendReceipt, utc_now_iso


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


def test_default_preview_never_prompts_connects_or_records(outreach, monkeypatch, capsys):
    attachment, history, calls, connections = outreach
    monkeypatch.delenv("GMAIL_EMAIL")
    monkeypatch.delenv("GMAIL_PASSWORD")
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("Preview asked for approval"))
    assert cli.main(["recruiter@example.invalid"]) == 0
    output = capsys.readouterr().out
    assert "To: recruiter@example.invalid" in output
    assert "Subject: Python Developer - Application" in output
    assert str(attachment) in output
    assert "Materials SHA-256:" in output
    assert "Hi," in output
    assert not calls and not connections and not history.exists()


@pytest.mark.parametrize("answer", ["", "yes", "send someone-else@example.invalid"])
def test_send_requires_exact_recipient_confirmation(outreach, monkeypatch, answer):
    _, history, calls, connections = outreach
    monkeypatch.setattr("builtins.input", lambda *args: answer)
    assert cli.main(["--send", "recruiter@example.invalid"]) == 0
    assert not calls and not connections and not history.exists()


@pytest.mark.parametrize("interruption", [EOFError, KeyboardInterrupt])
def test_interrupted_review_stops_batch(outreach, monkeypatch, interruption):
    _, history, calls, connections = outreach

    def cancel(prompt):
        raise interruption()

    monkeypatch.setattr("builtins.input", cancel)
    assert cli.main(["--send", "one@example.invalid", "two@example.invalid"]) == 0
    assert not calls and not connections and not history.exists()


def test_approved_delivery_uses_guard_and_deduplicates(outreach, monkeypatch, capsys):
    _, history, calls, connections = outreach
    history.write_text("old@example.invalid\n")
    prompts = []

    def confirm(prompt):
        assert "To: new@example.invalid" in capsys.readouterr().out
        prompts.append(prompt)
        return "send new@example.invalid"

    monkeypatch.setattr("builtins.input", confirm)
    assert (
        cli.main(["--send", "old@example.invalid", "new@example.invalid", "new@example.invalid"])
        == 0
    )
    assert len(prompts) == len(calls) == len(connections) == 1
    assert calls[0][0] == "new@example.invalid"
    assert calls[0][3] == b"reviewed CV"
    assert history.read_text() == "old@example.invalid\nnew@example.invalid\n"


def test_attachment_change_during_review_cannot_send(outreach, monkeypatch):
    attachment, history, calls, connections = outreach

    def confirm(prompt):
        attachment.write_bytes(b"unreviewed replacement")
        return "send recruiter@example.invalid"

    monkeypatch.setattr("builtins.input", confirm)
    assert cli.main(["--send", "recruiter@example.invalid"]) == 1
    assert not calls and not connections and not history.exists()


def test_change_after_approval_is_refused_by_delivery_guard(outreach, monkeypatch):
    attachment, history, calls, _ = outreach
    approve = cli.approve_package

    def changed(package, **kwargs):
        approved = approve(package, **kwargs)
        attachment.write_bytes(b"changed after approval")
        return approved

    monkeypatch.setattr(cli, "approve_package", changed)
    monkeypatch.setattr("builtins.input", lambda *args: "send recruiter@example.invalid")
    assert cli.main(["--send", "recruiter@example.invalid"]) == 1
    assert not calls and not history.exists()


def test_missing_attachment_cannot_prompt_or_send(outreach, monkeypatch):
    attachment, history, calls, connections = outreach
    attachment.unlink()
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("Missing attachment prompted"))
    assert cli.main(["--send", "recruiter@example.invalid"]) == 1
    assert not calls and not connections and not history.exists()


def test_missing_credentials_cannot_connect(outreach, monkeypatch):
    _, history, calls, connections = outreach
    monkeypatch.delenv("GMAIL_PASSWORD")
    monkeypatch.setattr("builtins.input", lambda *args: "send recruiter@example.invalid")
    assert cli.main(["--send", "recruiter@example.invalid"]) == 1
    assert not calls and not connections and not history.exists()


def test_failed_transport_does_not_record_sent(outreach, monkeypatch):
    _, history, _, _ = outreach

    class Failure:
        def __init__(self, *args):
            pass

        def send(self, **kwargs):
            return SendReceipt(False, kwargs["to_email"], utc_now_iso(), transport_name="synthetic")

    monkeypatch.setattr(cli, "YagmailEmailTransport", Failure)
    monkeypatch.setattr("builtins.input", lambda *args: "send recruiter@example.invalid")
    assert cli.main(["--send", "recruiter@example.invalid"]) == 1
    assert not history.exists()


def test_history_failure_after_send_stops_batch(outreach, monkeypatch, capsys):
    _, history, calls, _ = outreach

    def confirm(prompt):
        history.mkdir()
        return "send one@example.invalid"

    monkeypatch.setattr("builtins.input", confirm)
    assert cli.main(["--send", "one@example.invalid", "two@example.invalid"]) == 1
    assert len(calls) == 1
    assert "Sent to one@example.invalid, but recording failed" in capsys.readouterr().out


@pytest.mark.parametrize("recipient", ["invalid", "a@b.invalid\r\nBcc: other@b.invalid"])
def test_invalid_recipient_has_no_effects(outreach, monkeypatch, recipient):
    _, history, calls, connections = outreach
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("Invalid recipient prompted"))
    assert cli.main(["--send", recipient]) == 1
    assert not calls and not connections and not history.exists()
