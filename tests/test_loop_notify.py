"""Offline checks for loop email pings; real delivery is never attempted."""

import dataclasses
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

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
    monkeypatch.setattr(notify, "time", SimpleNamespace(sleep=lambda seconds: None))
    receipt = notify.send_ping(subject="s", body="b", run_dir=tmp_path, event="broken")
    assert receipt["success"] is False
    assert receipt["live"] is False
    assert receipt["attempts"] == 3
    assert "smtp down" in receipt["error_message"]


@dataclasses.dataclass
class PingResult:
    success: bool
    recipient: str
    timestamp_utc: str
    error_message: str | None


def test_ping_retries_raising_transport_then_succeeds(tmp_path, monkeypatch):
    calls = []
    sleeps = []

    class Flaky:
        def send(self, **kwargs):
            calls.append(kwargs)
            if len(calls) < 3:
                raise OSError("getaddrinfo failed")
            return PingResult(True, kwargs["to_email"], "t", None)

    class SenderModule:
        def YagmailEmailTransport(self, email, password):
            return Flaky()

        def DryRunEmailTransport(self):
            raise AssertionError("live path expected")

    monkeypatch.setattr(notify, "_load_sender", lambda: SenderModule())
    monkeypatch.setattr(
        notify, "read_gmail_config", lambda root=notify.ROOT: ("owner@example.com", "pw")
    )
    monkeypatch.setattr(notify, "time", SimpleNamespace(sleep=sleeps.append))
    receipt = notify.send_ping(subject="s", body="b", run_dir=tmp_path, event="flaky")
    assert receipt["success"] is True
    assert receipt["live"] is True
    assert receipt["attempts"] == 3
    assert len(calls) == 3
    assert sleeps == [30, 30]


def test_ping_retries_returned_failure_then_succeeds(tmp_path, monkeypatch):
    calls = []

    class Flapping:
        def send(self, **kwargs):
            calls.append(kwargs)
            if len(calls) < 2:
                return PingResult(False, kwargs["to_email"], "t", "dns down")
            return PingResult(True, kwargs["to_email"], "t", None)

    class SenderModule:
        def YagmailEmailTransport(self, email, password):
            return Flapping()

        def DryRunEmailTransport(self):
            raise AssertionError("live path expected")

    monkeypatch.setattr(notify, "_load_sender", lambda: SenderModule())
    monkeypatch.setattr(
        notify, "read_gmail_config", lambda root=notify.ROOT: ("owner@example.com", "pw")
    )
    monkeypatch.setattr(notify, "time", SimpleNamespace(sleep=lambda seconds: None))
    receipt = notify.send_ping(subject="s", body="b", run_dir=tmp_path, event="flap")
    assert receipt["success"] is True
    assert receipt["attempts"] == 2
    assert len(calls) == 2


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


def test_ping_carries_public_ip(tmp_path, monkeypatch):
    captured = {}

    class Capturing:
        def send(self, **kwargs):
            captured.update(kwargs)
            from types import SimpleNamespace

            return SimpleNamespace(
                success=True,
                recipient=kwargs["to_email"],
                timestamp_utc="t",
                error_message=None,
            )

    class SenderModule:
        def YagmailEmailTransport(self, email, password):
            return Capturing()

        def DryRunEmailTransport(self):
            raise AssertionError("live path expected")

    monkeypatch.setattr(notify, "_load_sender", lambda: SenderModule())
    monkeypatch.setattr(
        notify, "read_gmail_config", lambda root=notify.ROOT: ("owner@example.com", "pw")
    )
    monkeypatch.setattr(notify, "public_ip", lambda **kwargs: "203.0.113.7")
    receipt = notify.send_ping(subject="s", body="b", run_dir=tmp_path, event="ip")
    assert receipt["public_ip"] == "203.0.113.7"
    assert "Public IP: 203.0.113.7" in captured["contents"]


def test_public_ip_fails_soft(tmp_path, monkeypatch):
    monkeypatch.setattr(notify, "read_gmail_config", lambda root=notify.ROOT: None)
    monkeypatch.setattr(notify, "public_ip", lambda **kwargs: None)
    receipt = notify.send_ping(
        subject="s",
        body="b",
        run_dir=tmp_path,
        event="noip",
        recipient="owner@example.com",
        dry_run=True,
    )
    assert receipt["public_ip"] is None
    monkeypatch.setattr(
        notify.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("down")),
    )
    assert notify.public_ip() is None
