"""Owner sleep button: schedule/cancel one self-service timer, never real sleep."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError

import pytest
from dashboard_test_http import get_json, post_json
from dashboard_web_app import DashboardRequestHandler
from owner_sleep import (
    cancel_owner_sleep,
    describe_sleep_outcome,
    last_outcome,
    launch_argv,
    parse_wake_source,
    read_lastwake_text,
    receipt_paths,
    schedule_owner_sleep,
    timer_state,
)


def _receipt(root, *, status="sleep_scheduled", due_in_minutes=30):
    receipt, _ = receipt_paths(root)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    due = datetime.now(UTC) + timedelta(minutes=due_in_minutes)
    receipt.write_text(
        json.dumps(
            {
                "status": status,
                "planned_sleep_utc": due.isoformat(),
                "planned_sleep_warsaw": due.isoformat(),
                "process_id": None,  # informational only; never signalled
            }
        ),
        encoding="utf-8",
    )
    return receipt


def test_launch_argv_short_and_long_delays(tmp_path) -> None:
    receipt, cancel = receipt_paths(tmp_path)
    short = launch_argv(tmp_path, delay_minutes=5, receipt=receipt, cancel=cancel)
    assert short[-2:] == ["-DelaySeconds", "300"]
    assert "-SleepAtUtc" not in short
    long = launch_argv(tmp_path, delay_minutes=60, receipt=receipt, cancel=cancel)
    assert "-SleepAtUtc" in long and "-DelaySeconds" not in long
    assert "Hidden" in long and str(receipt) in long and str(cancel) in long
    with pytest.raises(ValueError, match="delay must be"):
        launch_argv(tmp_path, delay_minutes=0, receipt=receipt, cancel=cancel)
    with pytest.raises(ValueError, match="delay must be"):
        launch_argv(tmp_path, delay_minutes=2000, receipt=receipt, cancel=cancel)
    with pytest.raises(ValueError, match="delay must be"):
        launch_argv(tmp_path, delay_minutes=True, receipt=receipt, cancel=cancel)


def test_timer_state_tracks_status_and_staleness(tmp_path) -> None:
    assert timer_state(tmp_path) == {"active": False, "status": "none"}
    _receipt(tmp_path, due_in_minutes=30)
    live = timer_state(tmp_path)
    assert live["active"] is True and live["stale"] is False
    _receipt(tmp_path, due_in_minutes=-16)  # past the stale grace
    stale = timer_state(tmp_path)
    assert stale["active"] is False and stale["stale"] is True
    _receipt(tmp_path, status="sleep_cancelled")
    assert timer_state(tmp_path)["active"] is False


def test_schedule_validates_delay_before_state(tmp_path) -> None:
    _receipt(tmp_path, due_in_minutes=30)
    with pytest.raises(ValueError, match="delay must be"):
        schedule_owner_sleep(tmp_path, 5000, launcher=lambda argv: None)


def test_schedule_writes_receipt_and_refuses_live_double(tmp_path) -> None:
    def fake_launcher(argv):
        assert argv[0] == "powershell.exe"
        _receipt(tmp_path, due_in_minutes=30)

    out = schedule_owner_sleep(tmp_path, 5, launcher=fake_launcher)
    assert out["ok"] is True
    saved = json.loads(receipt_paths(tmp_path)[0].read_text(encoding="utf-8"))
    assert out["due_warsaw"] == saved["planned_sleep_warsaw"]
    with pytest.raises(ValueError, match="already scheduled"):
        schedule_owner_sleep(tmp_path, 5, launcher=fake_launcher)
    state = timer_state(tmp_path)
    assert state["active"] is True and state["stale"] is False


def test_schedule_overwrites_stale_receipt(tmp_path) -> None:
    _receipt(tmp_path, due_in_minutes=-16)
    assert timer_state(tmp_path)["active"] is False
    out = schedule_owner_sleep(tmp_path, 5, launcher=lambda argv: _receipt(tmp_path))
    assert out["ok"] is True


def test_schedule_times_out_without_ack(tmp_path, monkeypatch) -> None:
    import owner_sleep

    monkeypatch.setattr(owner_sleep, "RECEIPT_WAIT_SECONDS", 0.05)
    with pytest.raises(ValueError, match="did not acknowledge"):
        schedule_owner_sleep(tmp_path, 5, launcher=lambda argv: None)


def test_cancel_paths(tmp_path, monkeypatch) -> None:
    import owner_sleep

    assert cancel_owner_sleep(tmp_path)["cancelled"] is False
    _receipt(tmp_path, status="sleep_cancelled")
    assert cancel_owner_sleep(tmp_path)["status"] == "sleep_cancelled"
    _, cancel = receipt_paths(tmp_path)
    assert not cancel.is_file()  # terminal receipts are left alone
    monkeypatch.setattr(owner_sleep, "RECEIPT_WAIT_SECONDS", 0.05)
    _receipt(tmp_path, due_in_minutes=-16)
    out = cancel_owner_sleep(tmp_path)
    assert out["cancelled"] is False and "stale" in out["status"]
    assert cancel.is_file()  # a stale-but-unfired helper still honors it


def test_sleep_endpoints(dashboard_server, tmp_path, monkeypatch) -> None:
    assert get_json(dashboard_server, "/api/sleep")["active"] is False

    def fake_launcher(argv):
        _receipt(tmp_path, due_in_minutes=30)

    monkeypatch.setattr(
        DashboardRequestHandler, "sleep_launcher", staticmethod(fake_launcher), raising=False
    )
    out = post_json(dashboard_server, "/api/sleep", {"delay_minutes": 30})
    assert out["ok"] is True
    with pytest.raises(HTTPError) as exc:
        post_json(dashboard_server, "/api/sleep", {"delay_minutes": 30})
    assert exc.value.code == 409
    with pytest.raises(HTTPError) as exc:
        post_json(dashboard_server, "/api/sleep", {"delay_minutes": "soon"})
    assert exc.value.code == 400
    with pytest.raises(HTTPError) as exc:
        post_json(dashboard_server, "/api/sleep", {"delay_minutes": 5000})
    assert exc.value.code == 400
    assert get_json(dashboard_server, "/api/sleep")["active"] is True
    import owner_sleep

    monkeypatch.setattr(owner_sleep, "RECEIPT_WAIT_SECONDS", 0.05)
    cancelled = post_json(dashboard_server, "/api/sleep/cancel", {})
    assert cancelled["cancelled"] is False  # no live helper to acknowledge
    assert "acknowledgement" in cancelled["status"]


POWER_BUTTON_LASTWAKE = """Wake History Count - 1
Wake History [0]
  Wake Source Count - 1
  Wake Source [0]
    Type: Fixed Feature
    Power Button
"""

DEVICE_LASTWAKE = """Wake History Count - 1
Wake History [0]
  Wake Source Count - 1
  Wake Source [0]
    Type: Device
    Instance Path: USB\\VID_046D&PID_C52B\\6&2b9a3c4&0&2
    Description: USB Input Device
    Manufacturer: (Standard system devices)
"""


def _success_receipt():
    # Shape of .tmp/owner-sleep/sleep-owner.json, 2026-11-21 01:14 sleep.
    return {
        "status": "sleep_api_returned_success",
        "transition_times_utc": {
            "sleep_requested": "2026-11-21T00:14:10.1016380+00:00",
            "sleep_api_returned_success": "2026-11-21T00:26:49.4163944+00:00",
        },
        "transition_times_warsaw": {
            "sleep_requested": "2026-11-21 01:14:10",
            "sleep_api_returned_success": "2026-11-21 01:26:49",
        },
    }


def test_describe_success_reports_span_and_wake_source() -> None:
    outcome = describe_sleep_outcome(_success_receipt(), lastwake_text=POWER_BUTTON_LASTWAKE)
    assert outcome["status"] == "sleep_api_returned_success"
    assert outcome["slept"] == "12m39s"
    assert outcome["wake_source"] == "Power Button"
    assert "12m39s" in outcome["summary"]
    assert "2026-11-21 01:14:10" in outcome["summary"]
    assert "Power Button" in outcome["summary"]


def test_describe_success_without_lastwake_capture() -> None:
    outcome = describe_sleep_outcome(_success_receipt())
    assert outcome["slept"] == "12m39s"
    assert outcome["wake_source"] == "unknown (no lastwake capture)"


def test_describe_success_without_transitions() -> None:
    outcome = describe_sleep_outcome({"status": "sleep_api_returned_success"})
    assert outcome["slept"] == "unknown span"
    assert "unknown span" in outcome["summary"]


def test_describe_non_success_states() -> None:
    assert describe_sleep_outcome(None)["summary"] == "no sleep receipt recorded"
    assert describe_sleep_outcome({})["status"] is None
    cancelled = describe_sleep_outcome({"status": "sleep_cancelled"})
    assert "cancelled" in cancelled["summary"]
    blocked = describe_sleep_outcome(
        {"status": "sleep_blocked_pending_update", "detail": "pending update reboot: X"}
    )
    assert "not attempted" in blocked["summary"] and "X" in blocked["summary"]
    assert (
        "pending update reboot"
        in describe_sleep_outcome({"status": "sleep_blocked_pending_update"})["summary"]
    )
    assert "rejected" in describe_sleep_outcome({"status": "sleep_request_rejected"})["summary"]
    scheduled = describe_sleep_outcome(
        {"status": "sleep_scheduled", "planned_sleep_warsaw": "2026-11-21 02:00:00"}
    )
    assert "02:00:00" in scheduled["summary"]
    requested = describe_sleep_outcome({"status": "sleep_requested"})
    assert "not reported back" in requested["summary"]
    weird = describe_sleep_outcome({"status": "sleep_bogus"})
    assert "unrecognized" in weird["summary"]


def test_parse_wake_source_shapes() -> None:
    assert parse_wake_source(POWER_BUTTON_LASTWAKE) == "Power Button"
    assert parse_wake_source(DEVICE_LASTWAKE) == "USB Input Device"
    assert parse_wake_source("Wake History Count - 0\n") == "none recorded"
    assert parse_wake_source(None) == "unknown (no lastwake capture)"
    assert parse_wake_source("  \n") == "unknown (no lastwake capture)"
    assert parse_wake_source("Wake History Count - 1\nWake History [0]\n") == "unknown"


def test_read_lastwake_text_runner_contract() -> None:
    from types import SimpleNamespace

    ok = read_lastwake_text(runner=lambda argv: SimpleNamespace(returncode=0, stdout="text"))
    assert ok == "text"
    assert read_lastwake_text(runner=lambda argv: (_ for _ in ()).throw(OSError())) is None
    failed = read_lastwake_text(runner=lambda argv: SimpleNamespace(returncode=1, stdout="text"))
    assert failed is None
    blank = read_lastwake_text(runner=lambda argv: SimpleNamespace(returncode=0, stdout="  \n"))
    assert blank is None


def _success_receipt_file(root) -> None:
    receipt, _ = receipt_paths(root)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(_success_receipt()), encoding="utf-8")


def test_last_outcome_reads_timer_slot(tmp_path) -> None:
    assert last_outcome(tmp_path)["status"] == "none"
    _success_receipt_file(tmp_path)
    outcome = last_outcome(tmp_path, lastwake_text=POWER_BUTTON_LASTWAKE)
    assert outcome["slept"] == "12m39s"
    assert outcome["wake_source"] == "Power Button"


def test_sleep_get_reports_last_outcome(dashboard_server, tmp_path, monkeypatch) -> None:
    _success_receipt_file(tmp_path)
    monkeypatch.setattr("dashboard_web_app.read_lastwake_text", lambda: POWER_BUTTON_LASTWAKE)
    payload = get_json(dashboard_server, "/api/sleep")
    assert payload["active"] is False
    assert payload["last_outcome"]["slept"] == "12m39s"
    assert "Power Button" in payload["last_outcome"]["summary"]
