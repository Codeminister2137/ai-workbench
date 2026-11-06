"""Owner-mail notifications: SMTP config, fail-closed sends, notify plan, settings API."""

from __future__ import annotations

import json
import smtplib
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from dashboard_web_app import DashboardRequestHandler
from owner_mail import (
    ATTENDED_NOTIFY_STATUSES,
    UNATTENDED_NOTIFY_STATUSES,
    format_run_mail,
    load_smtp_config,
    mail_configured,
    notify_plan,
    send_owner_mail,
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


def get_json(base: str, path: str) -> dict:
    with urlopen(f"{base}{path}", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(base: str, path: str, payload: dict) -> dict:
    request = Request(
        f"{base}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


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


def test_notify_plan_attended_narrows_statuses(tmp_path, fake_smtp) -> None:
    sender, notify_on = notify_plan("attended", tmp_path, dict(SMTP_ENV))
    assert sender is not None
    assert notify_on == ATTENDED_NOTIFY_STATUSES
    assert ATTENDED_NOTIFY_STATUSES == frozenset({"failed", "waiting_on_owner"})
    receipt = sender({"run_id": "run-12345678", "status": "failed", "title": "t"})
    assert receipt["sent"] is True
    assert "[workbench] run failed: run-1234" == receipt["subject"]


def test_notify_plan_unattended_mails_terminal(tmp_path) -> None:
    _sender, notify_on = notify_plan("unattended", tmp_path, dict(SMTP_ENV))
    assert notify_on == frozenset({"completed", "failed", "cancelled", "waiting_on_owner"})


def test_format_run_mail_includes_error() -> None:
    body = format_run_mail({"run_id": "r1", "status": "failed", "error": "boom"})
    assert "r1" in body and "failed" in body and "boom" in body


def test_settings_defaults_attended_unconfigured(dashboard_server, monkeypatch) -> None:
    monkeypatch.delenv("WORKBENCH_OWNER_EMAIL", raising=False)
    monkeypatch.delenv("WORKBENCH_SMTP_HOST", raising=False)
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
    assert receipt["sent"] is True
    assert fake_smtp.instances[0].host == "smtp.gmail.com"
    assert fake_smtp.instances[0].logins == [("owner@gmail.test", "app-pass")]
