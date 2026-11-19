from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from ai_provider.allowance_windows import AllowanceWindow
from ai_provider.eval_planner import plan_eval_windows

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


def _window(provider: str, bucket: str, window: str, **over) -> AllowanceWindow:
    base = {
        "provider": provider,
        "bucket_id": bucket,
        "window": window,
        "used_percent": 10.0,
        "remaining_percent": 90.0,
        "resets_at_utc": None,
        "source": "test",
    }
    base.update(over)
    return AllowanceWindow(**base)


def test_proposes_after_reset_earliest_first() -> None:
    soon = (NOW + timedelta(hours=2)).isoformat()
    later = (NOW + timedelta(days=1)).isoformat()
    windows = [
        _window("codex", "weekly", "weekly", resets_at_utc=later),
        _window("copilot", "monthly", "monthly", resets_at_utc=soon),
    ]
    plan = plan_eval_windows(windows, now=NOW)
    assert [entry.bucket_id for entry in plan] == ["monthly", "weekly"]
    assert plan[0].window_start_utc == soon
    assert plan[0].stop_policy == "observed"


def test_skips_empty_buckets_and_runs_unknown_resets_now() -> None:
    windows = [
        _window("kiro", "empty", "monthly", used_percent=100.0, remaining_percent=0.0),
        _window("codex", "live", "weekly", resets_at_utc=None),
    ]
    plan = plan_eval_windows(windows, now=NOW)
    assert [entry.bucket_id for entry in plan] == ["live"]
    assert plan[0].window_start_utc == NOW.isoformat()


def test_opencode_weekly_paced_against_monthly() -> None:
    monthly_reset = (NOW + timedelta(days=21)).isoformat()
    weekly_reset = (NOW + timedelta(days=2)).isoformat()
    windows = [
        _window("opencode-go", "m", "monthly", remaining_percent=60.0, resets_at_utc=monthly_reset),
        _window("opencode-go", "w", "weekly", remaining_percent=80.0, resets_at_utc=weekly_reset),
    ]
    plan = plan_eval_windows(windows, now=NOW)
    weekly = next(entry for entry in plan if entry.bucket_id == "w")
    assert weekly.window_start_utc == weekly_reset
    assert weekly.suggested_share == pytest.approx(0.6 / 3.0 / 4.0, rel=0.01)
    assert "monthly 60%" in weekly.reason


def test_rejects_bad_share() -> None:
    with pytest.raises(ValueError):
        plan_eval_windows([], now=NOW, eval_share=0)
