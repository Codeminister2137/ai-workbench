from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from ai_provider import route_eval
from ai_provider.allowance_windows import AllowanceWindow
from ai_provider.eval_budget import AllowanceTaskBudget

NOW = datetime(2026, 11, 19, tzinfo=UTC)


def windows(used):
    return [
        AllowanceWindow(
            "opencode-go", "account", "weekly", used, None, "2026-11-20T00:00:00+00:00", "fake"
        )
    ]


def budget(readings, **kwargs):
    readings = iter(readings)
    return AllowanceTaskBudget(
        lambda: next(readings), clock=lambda: NOW, max_read_age=timedelta(seconds=2), **kwargs
    )


class FakeClient:
    def __init__(self):
        self.calls = 0

    def complete(self, request):
        self.calls += 1
        return SimpleNamespace(
            message=SimpleNamespace(content="def add2(x):\n    return x + 2"), usage=None
        )


def walk(client, allowance, **kwargs):
    return route_eval.run_candidate_ladder(
        lambda model: client,
        "opencode_go",
        ["a", "b"],
        stop_on_fail=False,
        walk_all=True,
        budget=allowance,
        **kwargs,
    )


def test_tier_translation_caps_calls_across_candidates():
    allowance = budget([windows(20), windows(21), windows(21), windows(22)])
    assert allowance.tasks == ("T0", "T1")
    assert allowance.max_tasks == 2
    client = FakeClient()
    rows = walk(client, allowance)
    assert [row.task_id for row in rows] == ["T0", "T1"]
    assert client.calls == allowance.calls == 2
    walk(client, allowance)
    assert client.calls == 2


def test_explicit_smaller_cap():
    allowance = budget([windows(20), windows(21)], max_tasks=1)
    client = FakeClient()
    assert len(walk(client, allowance)) == 1
    assert client.calls == 1


@pytest.mark.parametrize("post", [windows(30), windows(35), [], windows(None)])
def test_postflight_stop_preserves_completed_grade(post):
    allowance = budget([windows(20), post])
    client = FakeClient()
    rows = walk(client, allowance)
    assert len(rows) == 1 and rows[0].passed
    assert client.calls == 1
    assert allowance.stop_reason
    walk(client, allowance)
    assert client.calls == 1


@pytest.mark.parametrize("pre", [[], windows(None)])
def test_missing_preflight_never_calls(pre):
    allowance = budget([pre])
    client = FakeClient()
    rows = walk(client, allowance)
    assert client.calls == 0
    assert rows[0].error is not None
    assert rows[0].error.startswith("budget-stop:")


def test_shared_usage_between_calls_stops():
    allowance = budget([windows(20), windows(21), windows(30)])
    client = FakeClient()
    rows = walk(client, allowance)
    assert client.calls == 1
    assert rows[-1].error is not None
    assert rows[-1].error.startswith("budget-stop:")


def test_slow_read_never_calls():
    ticks = iter([NOW, NOW + timedelta(seconds=3)])
    allowance = AllowanceTaskBudget(
        lambda: windows(20), clock=lambda: next(ticks), max_read_age=timedelta(seconds=2)
    )
    client = FakeClient()
    walk(client, allowance)
    assert client.calls == 0
    assert allowance.stop_reason is not None
    assert "Stale" in allowance.stop_reason


def test_allowance_without_budget_fails_closed():
    client = FakeClient()
    rows = walk(client, None)
    assert client.calls == 0
    assert rows[0].error is not None
    assert rows[0].error.startswith("budget-stop:")


def test_empty_tasks_never_call_gate():
    client = FakeClient()
    assert walk(client, budget([]), tasks=()) == []
    assert client.calls == 0


def test_constructing_budget_does_not_read_or_run():
    def unexpected():
        pytest.fail("must require explicit start")

    allowance = AllowanceTaskBudget(unexpected, clock=unexpected, max_read_age=timedelta(seconds=2))
    assert allowance.calls == 0


def test_failed_operation_stops_and_still_reads_after():
    reads = []

    def read():
        reads.append(1)
        return windows(20)

    allowance = AllowanceTaskBudget(read, clock=lambda: NOW, max_read_age=timedelta(seconds=2))

    def fail():
        raise RuntimeError("fake failure")

    with pytest.raises(RuntimeError, match="fake failure"):
        allowance.run(fail)
    assert len(reads) == 2
    assert allowance.run(lambda: 1) is None


def test_transport_failures_consume_same_budget_across_candidates(monkeypatch):
    allowance = budget([windows(20), windows(21), windows(21), windows(22)])
    calls = []

    class BrokenClient:
        def complete(self, request):
            calls.append(1)
            raise RuntimeError("fake transport error")

    monkeypatch.setattr(
        route_eval,
        "_clients",
        lambda credentials: {
            "opencode_go": lambda model: BrokenClient(),
        },
    )
    rows = route_eval.run_all(
        {},
        routes=["opencode_go"],
        models={"opencode_go": ["a", "b", "c"]},
        max_attempts=0,
        walk_all=True,
        budgets={"opencode_go": allowance},
    )
    assert len(rows) == len(calls) == allowance.max_tasks == 2
    assert all(row.error for row in rows)


def test_every_window_counts_and_reset_stops():
    first = windows(20)
    second = [
        AllowanceWindow(
            "opencode-go", "other", "daily", 50, None, "2026-11-20T00:00:00+00:00", "fake"
        )
    ]
    post = [
        AllowanceWindow(
            "opencode-go", "other", "daily", 60, None, "2026-11-20T00:00:00+00:00", "fake"
        )
    ]
    client = FakeClient()
    allowance = budget([first + second, first + post])
    assert len(walk(client, allowance)) == 1
    assert client.calls == 1 and allowance.stop_reason


@pytest.mark.parametrize("cap", [-1])
def test_invalid_cap_rejected(cap):
    with pytest.raises(ValueError, match="max_tasks"):
        budget([], max_tasks=cap)
