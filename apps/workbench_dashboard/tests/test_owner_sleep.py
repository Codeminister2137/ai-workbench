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
    launch_argv,
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
