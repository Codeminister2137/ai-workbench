"""Offline checks for loop email pings; real delivery is never attempted."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/loop_notify.py"
spec = importlib.util.spec_from_file_location("loop_notify", SCRIPT)
assert spec is not None
assert spec.loader is not None
notify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notify)


def test_dry_run_ping_writes_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(notify, "read_gmail_config", lambda root=notify.ROOT: None)
    receipt = notify.send_ping(
        subject="subject",
        body="body",
        run_dir=tmp_path,
        event="test-event",
        recipient="owner@example.com",
        dry_run=True,
    )
    assert receipt["success"] is True
    assert receipt["live"] is False
    assert receipt["recipient"] == "owner@example.com"
    assert receipt["event"] == "test-event"
    saved = list((tmp_path / "notifications").glob("test-event-*.json"))
    assert len(saved) == 1
    assert json.loads(saved[0].read_text(encoding="utf-8"))["subject"] == "subject"


def test_misdirected_ping_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(
        notify, "read_gmail_config", lambda root=notify.ROOT: ("owner@example.com", "pw")
    )
    with pytest.raises(ValueError, match="owner's Gmail address"):
        notify.send_ping(
            subject="s",
            body="b",
            run_dir=tmp_path,
            event="evil",
            recipient="stranger@example.com",
            dry_run=True,
        )
    assert list((tmp_path / "notifications").glob("evil-*.json")) == []


def test_transport_failure_is_captured_not_raised(tmp_path, monkeypatch):
    class Broken:
        def send(self, **kwargs):
            raise RuntimeError("smtp down")

    class SenderModule:
        def YagmailEmailTransport(self, email, password):
            return Broken()

        def DryRunEmailTransport(self):
            raise AssertionError("live path expected")

    monkeypatch.setattr(notify, "_load_sender", lambda: SenderModule())
    monkeypatch.setattr(
        notify, "read_gmail_config", lambda root=notify.ROOT: ("owner@example.com", "pw")
    )
    receipt = notify.send_ping(subject="s", body="b", run_dir=tmp_path, event="broken")
    assert receipt["success"] is False
    assert receipt["live"] is False
    assert "smtp down" in receipt["error_message"]


def test_gmail_config_precedence(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "GMAIL_EMAIL=root@example.com\nGMAIL_PASSWORD=rootpw\n", encoding="utf-8"
    )
    job_env = tmp_path / "apps/job_search/job-email"
    job_env.mkdir(parents=True)
    (job_env / ".env").write_text(
        "GMAIL_EMAIL=job@example.com\nGMAIL_PASSWORD=jobpw\n", encoding="utf-8"
    )
    monkeypatch.delenv("GMAIL_EMAIL", raising=False)
    monkeypatch.delenv("GMAIL_PASSWORD", raising=False)
    assert notify.read_gmail_config(tmp_path) == ("root@example.com", "rootpw")
    monkeypatch.setenv("GMAIL_EMAIL", "env@example.com")
    monkeypatch.setenv("GMAIL_PASSWORD", "envpw")
    assert notify.read_gmail_config(tmp_path) == ("env@example.com", "envpw")
    (tmp_path / ".env").unlink()
    monkeypatch.delenv("GMAIL_EMAIL")
    monkeypatch.delenv("GMAIL_PASSWORD")
    assert notify.read_gmail_config(tmp_path) == ("job@example.com", "jobpw")
