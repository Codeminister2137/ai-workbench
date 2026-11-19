from datetime import UTC, datetime, timedelta

import pytest
from ai_provider.allowance_windows import AllowanceWindow
from ai_provider.eval_threshold import EvalThresholdStop, ObservedEvalThreshold

NOW = datetime(2026, 11, 19, tzinfo=UTC)


def windows(used, reset="2026-11-20T00:00:00+00:00"):
    return [AllowanceWindow("codex", "account", "weekly", used, None, reset, "test")]


def run(guard, readings, calls, **kwargs):
    iterator = iter(readings)
    return guard.run(
        lambda: calls.append(1),
        lambda: next(iterator),
        clock=lambda: NOW,
        max_read_age=timedelta(seconds=2),
        **kwargs,
    )


def test_sequential_calls_allow_overshoot_then_latch():
    guard, calls = ObservedEvalThreshold(), []
    run(guard, [windows(30), windows(39)], calls)
    with pytest.raises(EvalThresholdStop):
        run(guard, [windows(39), windows(43)], calls)
    with pytest.raises(EvalThresholdStop):
        run(guard, [], calls)
    assert len(calls) == 2


def test_shared_usage_at_threshold_blocks_before_call():
    guard, calls = ObservedEvalThreshold(), []
    run(guard, [windows(20), windows(21)], calls)
    with pytest.raises(EvalThresholdStop):
        run(guard, [windows(30)], calls)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "bad",
    [
        [],
        windows(None),
        windows(float("nan")),
        windows(101),
        windows(1, "bad"),
        windows(1, "2026-11-18T00:00:00+00:00"),
    ],
)
def test_invalid_pre_read_stops_without_call(bad):
    guard, calls = ObservedEvalThreshold(), []
    with pytest.raises(ValueError):
        run(guard, [bad], calls)
    assert guard.stopped and calls == []


@pytest.mark.parametrize("post", [[], windows(19), windows(21, "2026-11-21T00:00:00+00:00")])
def test_missing_or_changed_post_read_stops(post):
    guard, calls = ObservedEvalThreshold(), []
    with pytest.raises(ValueError):
        run(guard, [windows(20), post], calls)
    assert guard.stopped and calls == [1]


def test_slow_read_is_stale():
    guard = ObservedEvalThreshold()
    times = iter([NOW, NOW + timedelta(seconds=3)])
    calls = []
    with pytest.raises(ValueError, match="Stale"):
        guard.run(
            lambda: calls.append(1),
            lambda: windows(20),
            clock=lambda: next(times),
            max_read_age=timedelta(seconds=2),
        )
    assert guard.stopped and calls == []


def test_operation_error_still_reads_after_and_stops():
    guard, reads = ObservedEvalThreshold(), []

    def read():
        reads.append(1)
        return windows(20)

    def fail():
        raise RuntimeError("operation failed")

    with pytest.raises(RuntimeError, match="operation failed"):
        guard.run(fail, read, clock=lambda: NOW, max_read_age=timedelta(seconds=2))
    assert guard.stopped and len(reads) == 2


def test_any_window_stops_even_when_other_window_is_below_threshold():
    guard, calls = ObservedEvalThreshold(), []

    def pair(weekly, monthly):
        return windows(weekly) + [
            AllowanceWindow(
                "codex", "account", "monthly", monthly, None, "2026-12-01T00:00:00+00:00", "test"
            )
        ]

    with pytest.raises(EvalThresholdStop):
        run(guard, [pair(20, 30), pair(21, 40)], calls)
    assert calls == [1]


def test_reentrant_call_is_rejected():
    guard = ObservedEvalThreshold()

    def nested():
        with pytest.raises(EvalThresholdStop):
            run(guard, [], [])

    guard.run(nested, lambda: windows(20), clock=lambda: NOW, max_read_age=timedelta(seconds=2))
