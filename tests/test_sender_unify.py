"""Phase-1 sender-unification regressions; dry-run only, never real mail.

Loads the job-email sender the same way the live loop_notify consumer does
(sys.path insert + plain import) and proves, without rewriting the sender:
an unapproved application can never be delivered, and a consumer can run
prepare -> approve -> deliver -> record end to end. Every delivery here
uses DryRunEmailTransport and the public-IP lookup is stubbed wherever
loop_notify runs, so no test touches the network or SMTP.
"""

import dataclasses
import importlib
import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest

JOB_EMAIL_DIR = Path(__file__).resolve().parents[1] / "apps/job_search/job-email"
if str(JOB_EMAIL_DIR) not in sys.path:
    sys.path.insert(0, str(JOB_EMAIL_DIR))

import approval  # noqa: E402
import models  # noqa: E402
import preparation  # noqa: E402
import sender  # noqa: E402


@pytest.fixture
def profile(tmp_path):
    attachment = tmp_path / "cv_phase1.pdf"
    attachment.write_bytes(b"synthetic reviewed CV")
    return models.CandidateProfile(
        applicant_name="Phase One",
        applicant_location="Poland",
        applicant_summary="Python Developer with backend experience.",
        portfolio_url="https://example.invalid",
        linkedin_url="https://example.invalid/in/phase-one",
        skills={
            "Python": models.SkillEvidence("Python", models.EvidenceStatus.DEMONSTRATED),
        },
        cv_variants={
            "backend": models.CVVariant("backend", str(attachment), "Backend Developer"),
        },
    )


@pytest.fixture
def vacancy():
    return models.JobVacancy(
        id="vac-phase1",
        company="Example Sp. z o.o.",
        title="Python Developer",
        location="Warsaw, Poland",
        contact_email="recruiter@example.invalid",
    )


def record_application(package, path):
    """Consumer-side structured record; mirrors the loop_notify receipt pattern."""
    payload = dataclasses.asdict(package)
    payload["recorded_at_utc"] = models.utc_now_iso()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def test_unapproved_package_is_never_delivered(profile, vacancy):
    package = preparation.prepare_application(profile, vacancy)
    transport = sender.DryRunEmailTransport()
    with pytest.raises(sender.UnapprovedApplicationError):
        sender.deliver_application(package, transport)
    assert transport.sent_deliveries == []


def test_rejected_package_is_never_delivered(profile, vacancy):
    package = preparation.prepare_application(profile, vacancy)
    rejected = approval.reject_package(package, reason="role out of scope")
    transport = sender.DryRunEmailTransport()
    with pytest.raises(sender.UnapprovedApplicationError):
        sender.deliver_application(rejected, transport)
    assert transport.sent_deliveries == []


def test_approval_bypass_is_refused(profile, vacancy):
    package = preparation.prepare_application(profile, vacancy)
    transport = sender.DryRunEmailTransport()
    with pytest.raises(sender.UnapprovedApplicationError):
        sender.deliver_application(package, transport, require_approval=False)
    assert transport.sent_deliveries == []


def test_consumer_flow_prepares_delivers_and_records(profile, vacancy, tmp_path):
    prepared = preparation.prepare_application(profile, vacancy)
    assert prepared.status is models.ApplicationStatus.PREPARED
    approved = approval.approve_package(prepared, approved_by="owner", notes="reviewed")
    assert approved.status is models.ApplicationStatus.APPROVED

    transport = sender.DryRunEmailTransport()
    delivered = sender.deliver_application(approved, transport)
    assert delivered.status is models.ApplicationStatus.SENT
    assert delivered.send_receipt is not None
    assert delivered.send_receipt.success is True
    assert len(transport.sent_deliveries) == 1

    record_path = tmp_path / "application-record.json"
    payload = record_application(delivered, record_path)
    assert payload["application_id"] == delivered.application_id
    assert payload["vacancy_ref"] == "vac-phase1"
    assert payload["contact_email"] == "recruiter@example.invalid"
    assert payload["cv_variant_id"] == "backend"
    assert payload["subject"] == delivered.subject
    assert payload["created_at_utc"]
    assert payload["approved_at_utc"]
    assert payload["approved_by"] == "owner"
    assert payload["status"] == "sent"
    assert payload["send_receipt"]["success"] is True
    assert payload["send_receipt"]["transport_name"] == "dry_run"
    assert payload["send_receipt"]["timestamp_utc"]
    assert payload["recorded_at_utc"]
    assert json.loads(record_path.read_text(encoding="utf-8")) == payload


def test_preparation_is_isolated_from_sending(profile, vacancy):
    source = inspect.getsource(preparation)
    for symbol in (
        "EmailTransport",
        "DryRun",
        "Yagmail",
        "deliver_application",
        "UnapprovedApplicationError",
        "import sender",
        "from sender",
        "transport.send",
    ):
        assert symbol not in source
    parameters = inspect.signature(preparation.prepare_application).parameters
    assert "transport" not in parameters
    assert "send" not in parameters

    sender_source = inspect.getsource(sender)
    assert "prepare_application" not in sender_source
    assert "approve_package" not in sender_source

    package = preparation.prepare_application(profile, vacancy)
    assert package.status is models.ApplicationStatus.PREPARED


def test_dry_run_transport_behavior_unchanged():
    transport = sender.DryRunEmailTransport()
    receipt = transport.send(
        to_email="not-an-address",
        subject="s",
        contents="b",
        attachments=None,
    )
    assert receipt.success is False
    assert receipt.transport_name == "dry_run"
    assert transport.sent_deliveries == []

    receipt = transport.send(
        to_email="owner@example.invalid",
        subject="s",
        contents="b",
        attachments=None,
    )
    assert receipt.success is True
    assert receipt.timestamp_utc
    assert transport.sent_deliveries == [
        {
            "to": "owner@example.invalid",
            "subject": "s",
            "contents": "b",
            "attachments": None,
        }
    ]


def test_dry_run_strict_check_reports_missing_attachment_without_raising(tmp_path):
    transport = sender.DryRunEmailTransport(check_attachment_exists=True)
    receipt = transport.send(
        to_email="owner@example.invalid",
        subject="s",
        contents="b",
        attachments=None,
    )
    assert receipt.success is False
    assert "Attachment file not found" in (receipt.error_message or "")
    assert transport.sent_deliveries == []

    missing = tmp_path / "absent.pdf"
    receipt = transport.send(
        to_email="owner@example.invalid",
        subject="s",
        contents="b",
        attachments=str(missing),
    )
    assert receipt.success is False
    assert transport.sent_deliveries == []


def test_yagmail_failure_path_returns_receipt_without_network(monkeypatch):
    def missing_yagmail(name, *args, **kwargs):
        raise ImportError(f"No module named {name!r}")

    monkeypatch.setattr(importlib, "import_module", missing_yagmail)
    transport = sender.YagmailEmailTransport("sender@example.invalid", "synthetic-secret")
    receipt = transport.send(
        to_email="owner@example.invalid",
        subject="s",
        contents="b",
        attachments=None,
    )
    assert receipt.success is False
    assert receipt.transport_name == "yagmail"
    assert "yagmail" in (receipt.error_message or "")


def test_loop_notify_consumer_dry_run(tmp_path, monkeypatch):
    # Owner decision A (inbox eebfd0c1, 2026-11-06): loop pings moved to the
    # dashboard stdlib mailer; sender.py stays the job-search app's transport.
    # The dry-run receipt contract below is unchanged by that move.
    script = Path(__file__).resolve().parents[1] / "scripts/loop_notify.py"
    spec = importlib.util.spec_from_file_location("loop_notify_phase1", script)
    assert spec is not None
    assert spec.loader is not None
    notify = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(notify)

    monkeypatch.setattr(notify, "read_gmail_config", lambda root=notify.ROOT: None)
    monkeypatch.setattr(notify, "public_ip", lambda **kwargs: None)
    receipt = notify.send_ping(
        subject="phase1",
        body="consumer ping",
        run_dir=tmp_path,
        event="phase1-event",
        recipient="owner@example.invalid",
        dry_run=True,
    )
    assert receipt["success"] is True
    assert receipt["live"] is False
    assert receipt["transport_name"] == "dry_run"
    assert receipt["recipient"] == "owner@example.invalid"
    saved = list((tmp_path / "notifications").glob("phase1-event-*.json"))
    assert len(saved) == 1
    assert json.loads(saved[0].read_text(encoding="utf-8"))["event"] == "phase1-event"
