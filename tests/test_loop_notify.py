"""Offline checks for loop email pings; real delivery is never attempted."""

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


@pytest.fixture(autouse=True)
def _isolate_stable_ip(tmp_path, monkeypatch):
    """Keep the cross-window IP file inside the test tmp dir."""
    monkeypatch.setattr(
        notify, "stable_ip_path", lambda root=notify.ROOT: tmp_path / "stable-ip.txt"
    )


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


def _om_receipt(sent: bool, error=None) -> dict:
    return {
        "to": "owner@example.com",
        "subject": "s",
        "dry_run": False,
        "sent": sent,
        "error": error,
        "finished": "t",
        "receipt": None,
    }


def test_transport_failure_is_captured_not_raised(tmp_path, monkeypatch):
    class OwnerMailModule:
        @staticmethod
        def send_owner_mail(**kwargs):
            raise RuntimeError("smtp down")

    monkeypatch.setattr(notify, "_load_owner_mail", lambda: OwnerMailModule())
    monkeypatch.setattr(
        notify, "read_gmail_config", lambda root=notify.ROOT: ("owner@example.com", "pw")
    )
    monkeypatch.setattr(notify, "time", SimpleNamespace(sleep=lambda seconds: None))
    receipt = notify.send_ping(subject="s", body="b", run_dir=tmp_path, event="broken")
    assert receipt["success"] is False
    assert receipt["live"] is False
    assert receipt["attempts"] == 3
    assert "smtp down" in receipt["error_message"]


def test_ping_retries_raising_transport_then_succeeds(tmp_path, monkeypatch):
    calls = []
    sleeps = []

    class OwnerMailModule:
        @staticmethod
        def send_owner_mail(**kwargs):
            calls.append(kwargs)
            if len(calls) < 3:
                raise OSError("getaddrinfo failed")
            return _om_receipt(True)

    monkeypatch.setattr(notify, "_load_owner_mail", lambda: OwnerMailModule())
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

    class OwnerMailModule:
        @staticmethod
        def send_owner_mail(**kwargs):
            calls.append(kwargs)
            if len(calls) < 2:
                return _om_receipt(False, "SMTPException: dns down")
            return _om_receipt(True)

    monkeypatch.setattr(notify, "_load_owner_mail", lambda: OwnerMailModule())
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

    class OwnerMailModule:
        @staticmethod
        def send_owner_mail(**kwargs):
            captured.update(kwargs)
            return _om_receipt(True)

    monkeypatch.setattr(notify, "_load_owner_mail", lambda: OwnerMailModule())
    monkeypatch.setattr(
        notify, "read_gmail_config", lambda root=notify.ROOT: ("owner@example.com", "pw")
    )
    monkeypatch.setattr(notify, "public_ip", lambda **kwargs: "203.0.113.7")
    receipt = notify.send_ping(subject="s", body="b", run_dir=tmp_path, event="ip")
    assert receipt["public_ip"] == "203.0.113.7"
    assert "Public IP: 203.0.113.7" in captured["body"]
    assert captured["config"]["host"] == "smtp.gmail.com"
    assert captured["config"]["username"] == "owner@example.com"
    assert captured["dry_run"] is False


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


def _seed_receipt(run_dir: Path, address: str | None) -> None:
    notifications = run_dir / "notifications"
    notifications.mkdir(parents=True, exist_ok=True)
    (notifications / "progress-20261106T120000Z.json").write_text(
        json.dumps({"event": "progress", "public_ip": address}), encoding="utf-8"
    )


def _capture(monkeypatch, tmp_path, address):
    calls = []

    class OwnerMailModule:
        @staticmethod
        def send_owner_mail(**kwargs):
            calls.append(kwargs)
            return {
                "sent": True,
                "finished": "t",
                "error": None,
                "receipt": None,
            }

    monkeypatch.setattr(notify, "_load_owner_mail", lambda: OwnerMailModule())
    monkeypatch.setattr(
        notify, "read_gmail_config", lambda root=notify.ROOT: ("owner@example.com", "pw")
    )
    monkeypatch.setattr(notify, "public_ip", lambda timeout=10: address)
    return calls


def test_ip_change_flagged_in_body(tmp_path, monkeypatch) -> None:
    _seed_receipt(tmp_path, "83.26.59.90")
    calls = _capture(monkeypatch, tmp_path, "83.26.80.50")
    receipt = notify.send_ping(subject="s", body="b", run_dir=tmp_path, event="progress")
    assert receipt["success"] is True
    assert "Public IP: 83.26.80.50" in calls[0]["body"]
    assert "83.26.59.90 -> 83.26.80.50" in calls[0]["body"]


def test_same_ip_not_flagged(tmp_path, monkeypatch) -> None:
    _seed_receipt(tmp_path, "83.26.80.50")
    calls = _capture(monkeypatch, tmp_path, "83.26.80.50")
    notify.send_ping(subject="s", body="b", run_dir=tmp_path, event="progress")
    assert "Public IP: 83.26.80.50" in calls[0]["body"]
    assert "changed since last ping" not in calls[0]["body"]


def test_first_ping_no_flag(tmp_path, monkeypatch) -> None:
    calls = _capture(monkeypatch, tmp_path, "83.26.80.50")
    notify.send_ping(subject="s", body="b", run_dir=tmp_path, event="progress")
    assert "changed since last ping" not in calls[0]["body"]


def test_cross_window_change_flagged_via_stable_file(tmp_path, monkeypatch) -> None:
    (tmp_path / "stable-ip.txt").write_text("83.26.59.90\n", encoding="utf-8")
    calls = _capture(monkeypatch, tmp_path, "83.26.80.50")
    notify.send_ping(subject="s", body="b", run_dir=tmp_path, event="progress")
    assert "83.26.59.90 -> 83.26.80.50" in calls[0]["body"]
    assert (tmp_path / "stable-ip.txt").read_text(encoding="utf-8").strip() == ("83.26.80.50")


def test_status_subject_tags_state_and_summary() -> None:
    assert notify.format_status_subject("WAITING_FOR_OWNER", "1 owner task left") == (
        "[workbench][WAITING_FOR_OWNER] 1 owner task left"
    )


def test_status_subject_rejects_unknown_state_or_blank_summary() -> None:
    with pytest.raises(ValueError, match="unknown mail state"):
        notify.format_status_subject("IDLE", "summary")
    with pytest.raises(ValueError, match="summary"):
        notify.format_status_subject("DONE", "  ")


def test_status_body_has_fixed_sections_in_order() -> None:
    body = notify.format_status_body(
        state="WAITING_FOR_OWNER",
        done=["loop-3 merged", "loop-4 merged"],
        remaining=["register CloneScan task (owner: run elevated script)"],
        waiting_on=["owner: inbox f06d2537 Done"],
        sleep="scheduled 2026-11-07 14:35 Warsaw (+10min closeout)",
        details="loop_status: 12 complete, 1 blocked, 0 remaining",
    )
    lines = body.splitlines()
    assert lines[0] == "State: WAITING_FOR_OWNER"
    sections = ("Done:", "Remaining:", "Waiting on:", "Sleep:", "Details:")

    def position(section: str) -> int:
        return next(
            i for i, line in enumerate(lines) if line == section or line.startswith(section + " ")
        )

    positions = [position(section) for section in sections]
    assert positions == sorted(positions)
    assert "- loop-3 merged" in lines
    assert "- register CloneScan task (owner: run elevated script)" in lines
    assert "- owner: inbox f06d2537 Done" in lines
    assert "Sleep: scheduled 2026-11-07 14:35 Warsaw (+10min closeout)" in lines
    assert "loop_status: 12 complete, 1 blocked, 0 remaining" in body


def test_status_body_renders_empty_sections_explicitly() -> None:
    body = notify.format_status_body(state="DONE")
    assert "State: DONE" in body.splitlines()
    assert body.count("- none") == 3  # done, remaining, waiting-on
    assert "Sleep: none" in body
    assert "(no details)" in body


def test_status_body_rejects_unknown_state() -> None:
    with pytest.raises(ValueError, match="unknown mail state"):
        notify.format_status_body(state="IDLE")


def test_cli_state_composes_structured_ping(tmp_path, monkeypatch) -> None:
    calls = _capture(monkeypatch, tmp_path, None)
    assert (
        notify.main(
            [
                "--run-dir",
                str(tmp_path),
                "--event",
                "waiting",
                "--subject",
                "1 owner task left",
                "--state",
                "WAITING_FOR_OWNER",
                "--done",
                "loop-4 merged",
                "--remaining",
                "register tasks",
                "--waiting-on",
                "owner inbox f06d2537",
                "--sleep-note",
                "sleep +10min",
                "--body",
                "loop_status quoted here",
                "--to",
                "owner@example.com",
                "--dry-run",
            ]
        )
        == 0
    )
    assert calls[0]["subject"] == "[workbench][WAITING_FOR_OWNER] 1 owner task left"
    assert calls[0]["body"].splitlines()[0] == "State: WAITING_FOR_OWNER"
    assert "- register tasks" in calls[0]["body"]
    saved = list((tmp_path / "notifications").glob("waiting-*.json"))
    assert len(saved) == 1
    assert json.loads(saved[0].read_text(encoding="utf-8"))["state"] == "WAITING_FOR_OWNER"


def test_cli_without_state_keeps_freeform_subject(tmp_path, monkeypatch) -> None:
    calls = _capture(monkeypatch, tmp_path, None)
    assert (
        notify.main(
            [
                "--run-dir",
                str(tmp_path),
                "--event",
                "legacy",
                "--subject",
                "plain subject",
                "--body",
                "plain body",
                "--to",
                "owner@example.com",
                "--dry-run",
            ]
        )
        == 0
    )
    assert calls[0]["subject"] == "plain subject"
    assert calls[0]["body"] == "plain body"
    saved = list((tmp_path / "notifications").glob("legacy-*.json"))
    assert len(saved) == 1
    assert json.loads(saved[0].read_text(encoding="utf-8"))["state"] is None
