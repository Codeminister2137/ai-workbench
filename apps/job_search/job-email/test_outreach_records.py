"""JSONL ledger wiring in the outreach send path.

Successful guarded deliveries append the sent package (with approval
snapshot and send receipt) to the local application-records ledger.
Only SENT packages are recorded, mirroring the sent-history rule; a
ledger failure after SMTP success stops the batch for reconciliation.
All fixtures are obviously synthetic.
"""

from __future__ import annotations

import outreach_cli as cli
import pytest
from models import ApplicationStatus, SendReceipt, utc_now_iso
from records import read_application_records


@pytest.fixture
def outreach(monkeypatch, tmp_path):
    attachment = tmp_path / "cv.pdf"
    attachment.write_bytes(b"reviewed CV")
    history = tmp_path / "sent.txt"
    ledger = tmp_path / "records.jsonl"
    monkeypatch.setenv("CV_ATTACHMENT", str(attachment))
    monkeypatch.setenv("SENT_FILE", str(history))
    monkeypatch.setenv("RECORDS_FILE", str(ledger))
    monkeypatch.setenv("GMAIL_EMAIL", "sender@example.invalid")
    monkeypatch.setenv("GMAIL_PASSWORD", "synthetic-secret")
    calls = []

    class Transport:
        def __init__(self, email, password):
            pass

        def send(self, *, to_email, subject, contents, attachments):
            calls.append(to_email)
            return SendReceipt(True, to_email, utc_now_iso(), transport_name="synthetic")

    monkeypatch.setattr(cli, "YagmailEmailTransport", Transport)
    return history, ledger, calls


def _approve(monkeypatch, recipient):
    monkeypatch.setattr("builtins.input", lambda *args: f"send {recipient}")


def test_send_appends_sent_record_with_receipt(outreach, monkeypatch):
    history, ledger, calls = outreach
    _approve(monkeypatch, "recruiter@example.invalid")
    assert cli.main(["--send", "recruiter@example.invalid"]) == 0
    assert calls == ["recruiter@example.invalid"]
    assert history.read_text() == "recruiter@example.invalid\n"
    (record,) = read_application_records(ledger)
    assert record.contact_email == "recruiter@example.invalid"
    assert record.status is ApplicationStatus.SENT
    assert record.cv_variant_id == "default"
    assert record.message_variant_id == "default"
    assert record.approval_notes == "Explicit terminal review"
    assert record.approved_materials_sha256
    assert record.send_receipt is not None
    assert record.send_receipt.success is True
    assert record.send_receipt.transport_name == "synthetic"


def test_preview_writes_no_ledger(outreach, monkeypatch):
    _, ledger, calls = outreach
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("Preview asked for approval"))
    assert cli.main(["recruiter@example.invalid"]) == 0
    assert not calls and not ledger.exists()


def test_failed_delivery_writes_no_ledger(outreach, monkeypatch):
    history, ledger, _ = outreach

    class FailingTransport:
        def __init__(self, email, password):
            pass

        def send(self, *, to_email, subject, contents, attachments):
            return SendReceipt(
                False,
                to_email,
                utc_now_iso(),
                error_message="synthetic bounce",
                transport_name="synthetic",
            )

    monkeypatch.setattr(cli, "YagmailEmailTransport", FailingTransport)
    _approve(monkeypatch, "recruiter@example.invalid")
    assert cli.main(["--send", "recruiter@example.invalid"]) == 1
    assert not history.exists() and not ledger.exists()


def test_ledger_failure_after_send_stops_batch(outreach, monkeypatch, capsys):
    history, ledger, calls = outreach
    monkeypatch.setattr(
        cli.records,
        "append_application_record",
        lambda path, package: (_ for _ in ()).throw(OSError("synthetic disk full")),
    )
    monkeypatch.setattr("builtins.input", lambda *args: "send good@example.invalid")
    argv = ["--send", "good@example.invalid", "later@example.invalid"]
    assert cli.main(argv) == 1
    output = capsys.readouterr().out
    assert "Sent to good@example.invalid" in output
    assert "reconcile" in output
    assert calls == ["good@example.invalid"]
    assert history.read_text() == "good@example.invalid\n"
    assert not ledger.exists()
