"""Owner-mail notifications: SMTP config, fail-closed sends, notify plan, settings API."""

from __future__ import annotations

import json
import smtplib
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError

import pytest
from dashboard_test_http import get_json, post_json
from dashboard_web_app import DashboardRequestHandler
from owner_mail import (
    ATTENDED_NOTIFY_STATUSES,
    UNATTENDED_NOTIFY_STATUSES,
    format_run_mail,
    format_run_subject,
    load_smtp_config,
    mail_configured,
    notify_plan,
)
from owner_mail import (
    _send_owner_mail_now as send_owner_mail,
)

SMTP_ENV = {
    "WORKBENCH_OWNER_EMAIL": "owner@example.test",
    "WORKBENCH_SMTP_HOST": "smtp.example.test",
    "WORKBENCH_SMTP_PORT": "2525",
    "WORKBENCH_SMTP_USER": "bot",
    "WORKBENCH_SMTP_PASS": "hunter2",
}


@pytest.fixture
def dashboard_server(tmp_path):
    config_path = tmp_path / "dashboard.json"
    config_path.write_text(
        json.dumps({"provider": "ollama", "model": "fake", "title": "Test Board"}),
        encoding="utf-8",
    )
    data_dir = tmp_path / "data"

    class TestHandler(DashboardRequestHandler):
        def log_message(self, format, *args):
            return

    TestHandler.config_path = config_path
    TestHandler.data_dir = data_dir
    TestHandler.repo_root = tmp_path
    server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


class FakeSMTP:
    instances: list = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.logins: list[tuple[str, str]] = []
        self.sent: list = []
        self.fail: Exception | None = None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def ehlo(self):
        return None

    def starttls(self, context=None):
        return None

    def login(self, username, password):
        self.logins.append((username, password))

    def send_message(self, message):
        if self.fail is not None:
            raise self.fail
        self.sent.append(message)


@pytest.fixture
def fake_smtp(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    return FakeSMTP


def test_smtp_config_loads() -> None:
    config = load_smtp_config(dict(SMTP_ENV))
    assert config["owner"] == "owner@example.test"
    assert config["host"] == "smtp.example.test"
    assert config["port"] == 2525
    assert config["username"] == "bot"
    assert config["password"] == "hunter2"
    assert config["starttls"] is True


def test_smtp_config_defaults() -> None:
    config = load_smtp_config({"WORKBENCH_OWNER_EMAIL": "o@x.test", "WORKBENCH_SMTP_HOST": "h"})
    assert config["port"] == 587
    assert config["username"] == ""
    assert config["starttls"] is True


def test_smtp_config_requires_owner_and_host(tmp_path) -> None:
    with pytest.raises(ValueError, match="WORKBENCH_OWNER_EMAIL"):
        load_smtp_config({"WORKBENCH_SMTP_HOST": "h"}, root=tmp_path)
    with pytest.raises(ValueError, match="WORKBENCH_OWNER_EMAIL"):
        load_smtp_config({"WORKBENCH_OWNER_EMAIL": "o@x.test"}, root=tmp_path)


def test_smtp_config_validates_port() -> None:
    bad = dict(SMTP_ENV, WORKBENCH_SMTP_PORT="nope")
    with pytest.raises(ValueError, match="integer"):
        load_smtp_config(bad)
    bad = dict(SMTP_ENV, WORKBENCH_SMTP_PORT="99999")
    with pytest.raises(ValueError, match="between 1 and 65535"):
        load_smtp_config(bad)


def test_mail_configured_probe(tmp_path) -> None:
    assert mail_configured(dict(SMTP_ENV)) is True
    assert mail_configured({}, root=tmp_path) is False


def test_notify_plan_dedupes_repeat_outcome(tmp_path, fake_smtp) -> None:
    sender, _notify_on = notify_plan("unattended", tmp_path / "rcpt", dict(SMTP_ENV))
    assert sender is not None
    summary = {"run_id": "run1", "status": "failed", "title": "t"}
    first = sender(summary)
    assert first["queued"] is True
    second = sender(summary)
    assert second["sent"] is False
    assert second["deduped"] is True
    assert len(FakeSMTP.instances) == 0
    other = sender({"run_id": "run1", "status": "completed", "title": "t"})
    assert other["queued"] is True  # different outcome joins the digest


def test_send_refuses_off_owner_address(tmp_path) -> None:
    config = load_smtp_config(dict(SMTP_ENV))
    with pytest.raises(ValueError, match="off the owner address"):
        send_owner_mail(
            to="stranger@example.test",
            subject="hi",
            body="x",
            config=config,
            receipts_dir=tmp_path,
        )
    assert list(tmp_path.iterdir()) == []


def test_dry_run_writes_receipt_without_sending(tmp_path, fake_smtp) -> None:
    config = load_smtp_config(dict(SMTP_ENV))
    receipt = send_owner_mail(
        to="owner@example.test",
        subject="hello",
        body="world",
        config=config,
        dry_run=True,
        receipts_dir=tmp_path,
    )
    assert receipt["sent"] is False
    assert receipt["dry_run"] is True
    assert receipt["error"] is None
    assert fake_smtp.instances == []
    files = list(tmp_path.glob("notify-*.json"))
    assert len(files) == 1
    assert "hunter2" not in files[0].read_text(encoding="utf-8")


def test_live_send_logs_in_and_sends(tmp_path, fake_smtp) -> None:
    config = load_smtp_config(dict(SMTP_ENV))
    receipt = send_owner_mail(
        to="owner@example.test",
        subject="hello",
        body="world",
        config=config,
        dry_run=False,
        receipts_dir=tmp_path,
    )
    assert receipt["sent"] is True
    assert len(fake_smtp.instances) == 1
    smtp = fake_smtp.instances[0]
    assert smtp.logins == [("bot", "hunter2")]
    assert len(smtp.sent) == 1
    assert smtp.sent[0]["Subject"] == "hello"


def test_transport_failure_captured_in_receipt(tmp_path, fake_smtp, monkeypatch) -> None:
    def boom(self, message):
        raise smtplib.SMTPException("relay refused")

    monkeypatch.setattr(FakeSMTP, "send_message", boom)
    config = load_smtp_config(dict(SMTP_ENV))
    receipt = send_owner_mail(
        to="owner@example.test",
        subject="hello",
        body="world",
        config=config,
        dry_run=False,
        receipts_dir=tmp_path,
    )
    assert receipt["sent"] is False
    assert "SMTPException" in receipt["error"]


def test_notify_plan_silent_without_smtp(tmp_path) -> None:
    sender, notify_on = notify_plan("unattended", tmp_path, {}, root=tmp_path)
    assert sender is None
    assert notify_on == UNATTENDED_NOTIFY_STATUSES
    assert list(tmp_path.iterdir()) == []


def test_notify_plan_attended_queues_needs_you_only(tmp_path, fake_smtp) -> None:
    # Owner C on c124e9a4: retain these outcomes for periodic status;
    # the shared flusher prevents routine attended mail pages.
    sender, notify_on = notify_plan("attended", tmp_path, dict(SMTP_ENV))
    assert sender is not None
    assert notify_on == ATTENDED_NOTIFY_STATUSES
    assert ATTENDED_NOTIFY_STATUSES == frozenset({"failed", "waiting_on_owner"})
    receipt = sender({"run_id": "run-12345678", "status": "failed", "title": "t"})
    assert receipt.get("queued") is True
    assert "skipped" not in receipt


def test_notify_plan_unattended_mails_terminal(tmp_path) -> None:
    _sender, notify_on = notify_plan("unattended", tmp_path, dict(SMTP_ENV))
    assert notify_on == frozenset({"completed", "failed", "cancelled", "waiting_on_owner"})


def test_format_run_mail_includes_error() -> None:
    body = format_run_mail({"run_id": "r1", "status": "failed", "error": "boom"})
    assert "r1" in body and "Failed" in body and "boom" in body


def test_settings_defaults_attended_unconfigured(dashboard_server, monkeypatch) -> None:
    monkeypatch.delenv("WORKBENCH_OWNER_EMAIL", raising=False)
    monkeypatch.delenv("WORKBENCH_SMTP_HOST", raising=False)
    monkeypatch.delenv("GMAIL_EMAIL", raising=False)
    monkeypatch.delenv("GMAIL_PASSWORD", raising=False)
    payload = get_json(dashboard_server, "/api/settings")
    assert payload == {"ok": True, "supervision": "attended", "mail_configured": False}


def test_settings_save_round_trips_and_preserves_keys(dashboard_server, tmp_path) -> None:
    payload = post_json(dashboard_server, "/api/settings", {"supervision": "unattended"})
    assert payload["supervision"] == "unattended"
    assert payload["ok"] is True
    stored = json.loads((tmp_path / "dashboard.json").read_text(encoding="utf-8"))
    assert stored["supervision"] == "unattended"
    assert stored["title"] == "Test Board"
    assert get_json(dashboard_server, "/api/settings")["supervision"] == "unattended"


def test_settings_rejects_bad_mode(dashboard_server) -> None:
    with pytest.raises(HTTPError) as exc:
        post_json(dashboard_server, "/api/settings", {"supervision": "chaos"})
    assert exc.value.code == 400
    with pytest.raises(HTTPError) as exc:
        post_json(dashboard_server, "/api/settings", {"supervision": 42})
    assert exc.value.code == 400


GMAIL_ENV = {
    "GMAIL_EMAIL": "owner@gmail.test",
    "GMAIL_PASSWORD": "app-pass",
}


def test_gmail_fallback_from_env(tmp_path) -> None:
    config = load_smtp_config(dict(GMAIL_ENV), root=tmp_path)
    assert config["owner"] == "owner@gmail.test"
    assert config["host"] == "smtp.gmail.com"
    assert config["port"] == 587
    assert config["username"] == "owner@gmail.test"
    assert config["password"] == "app-pass"
    assert config["starttls"] is True
    assert mail_configured(dict(GMAIL_ENV), root=tmp_path) is True


def test_gmail_fallback_from_root_env_file(tmp_path) -> None:
    (tmp_path / ".env").write_text(
        "GMAIL_EMAIL=file@gmail.test\nGMAIL_PASSWORD=file-pass\n",
        encoding="utf-8",
    )
    config = load_smtp_config({}, root=tmp_path)
    assert config["owner"] == "file@gmail.test"
    assert config["host"] == "smtp.gmail.com"
    assert config["password"] == "file-pass"


def test_explicit_smtp_wins_over_gmail(tmp_path) -> None:
    both = dict(SMTP_ENV, **GMAIL_ENV)
    config = load_smtp_config(both, root=tmp_path)
    assert config["owner"] == "owner@example.test"
    assert config["host"] == "smtp.example.test"


def test_notify_plan_uses_gmail_fallback(tmp_path, fake_smtp) -> None:
    sender, notify_on = notify_plan("unattended", tmp_path, dict(GMAIL_ENV), root=tmp_path)
    assert sender is not None
    assert notify_on == UNATTENDED_NOTIFY_STATUSES
    receipt = sender({"run_id": "run-abcdef12", "status": "completed", "title": "t"})
    assert receipt["queued"] is True
    assert not fake_smtp.instances


def test_digest_reaches_smtp_only_when_due(tmp_path, fake_smtp):
    import time

    from owner_digest import flush_digest

    sender, _ = notify_plan("unattended", tmp_path / "mail-receipts", dict(SMTP_ENV))
    assert sender is not None
    assert sender({"run_id": "r-digest", "status": "failed"})["queued"]
    assert not fake_smtp.instances
    result = flush_digest(
        data_dir=tmp_path,
        supervision="unattended",
        config=load_smtp_config(dict(SMTP_ENV)),
        now=time.time() + 3601,
    )
    assert result["sent"]
    assert len(fake_smtp.instances) == 1
    content = fake_smtp.instances[0].sent[0].get_content()
    # Digest v2: failed runs page as soon/needs-you, not BLOCKER; only
    # waiting_on_owner (stopped for the owner) keeps the BLOCKER prefix.
    assert "Verdict: soon" in content
    assert "--- NEEDS YOU ---" in content
    assert "BLOCKER" not in content


@pytest.mark.parametrize(
    "status,label",
    [
        ("completed", "Done"),
        ("failed", "Failed"),
        ("waiting_on_owner", "Blocked"),
        ("cancelled", "Cancelled"),
    ],
)
def test_human_run_notification(status, label):
    summary = {
        "run_id": "123456789abcdef",
        "status": status,
        "title": "Fix digest",
        "error": "Validation failed",
        "inbox_id": "source",
        "prompt": "PRIVATE PROMPT",
        "credentials": "SECRET",
    }
    body = format_run_mail(summary)
    assert format_run_subject(summary) == f"{label}: Fix digest"
    assert body.startswith(f"{label}\nTitle: Fix digest\nOutcome: ")
    assert "Reason: Validation failed" in body
    assert body.splitlines()[-1] == "Refs: run:12345678 | inbox:source"
    assert "PRIVATE" not in body and "SECRET" not in body and "Details:" not in body
    if status == "waiting_on_owner":
        assert "Needs owner input; inbox:source" in body


@pytest.mark.parametrize(
    "extra,expected",
    [
        ({"triage_item": "triage1"}, "Triage queued; inbox:triage1"),
        (
            {"shipment": {"merge_item": "review1", "commit": "abc"}},
            "Integration review queued; inbox:review1",
        ),
        ({"shipment": {"merged_sha": "abcdef"}}, "Merged as abcdef"),
        ({}, "no queued follow-up recorded"),
    ],
)
def test_run_notification_next_step_is_evidenced(extra, expected):
    body = format_run_mail({"run_id": "r", "status": "completed", **extra})
    assert expected in body
    assert body.count("Refs:") == 1


def test_run_notification_bounds_and_structured_error():
    summary = {"title": "x\n" * 50000, "error": {"prompt": "SECRET"}, "status": "failed"}
    assert len(format_run_subject(summary)) <= 300
    assert len(format_run_mail(summary)) <= 50000
    assert "SECRET" not in format_run_mail(summary)


def test_human_notification_dry_run_receipt(tmp_path, monkeypatch):
    import owner_mail

    def no_delivery(*args, **kwargs):
        pytest.fail("Dry run attempted SMTP delivery")

    monkeypatch.setattr(owner_mail, "_deliver", no_delivery)
    summary = {
        "run_id": "123456789abcdef",
        "status": "failed",
        "title": "Fix digest",
        "error": "Tests failed",
        "triage_item": "triage1",
    }
    body = format_run_mail(summary)
    receipt = owner_mail.send_owner_mail(
        to="owner@example.test",
        subject=format_run_subject(summary),
        body=body,
        config=load_smtp_config(SMTP_ENV),
        receipts_dir=tmp_path,
        dry_run=True,
    )
    saved = json.loads((tmp_path / receipt["receipt"]).read_text())
    assert saved["subject"] == "Failed: Fix digest"
    assert saved["dry_run"] and not saved["sent"]
    assert saved["error"] is None
    assert "Outcome: Could not complete: Fix digest. Reason: Tests failed" in body
    assert "Next: Triage queued" in body
    assert body.endswith("Refs: run:12345678 | inbox:triage1")
    assert not (tmp_path / "owner-digest.sqlite3").exists()
