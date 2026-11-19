from __future__ import annotations

import pytest
from ai_provider.allowance_windows import AllowanceWindow
from ai_provider.eval_budget import observed_spend, over_threshold, snapshot


def _window(bucket: str, used: float | None) -> AllowanceWindow:
    return AllowanceWindow(
        provider="codex",
        bucket_id=bucket,
        window="weekly",
        used_percent=used,
        remaining_percent=None,
        resets_at_utc=None,
        source="test",
    )


def test_snapshot_compare_stop_cycle() -> None:
    before = snapshot([_window("a", 10.0), _window("b", 50.0)])
    now = snapshot([_window("a", 12.5), _window("b", 50.0)])
    spend = observed_spend(before, now)
    assert spend == {"codex/a/weekly": 2.5, "codex/b/weekly": 0.0}
    assert over_threshold(spend, 2.0) == ["codex/a/weekly"]
    assert over_threshold(spend, 2.5) == []


def test_unknown_readings_never_count_as_spend() -> None:
    before = snapshot([_window("a", None)])
    now = snapshot([_window("a", 90.0)])
    assert observed_spend(before, now) == {}
    assert over_threshold({}, 0.1) == []
    with pytest.raises(ValueError):
        over_threshold({"x": 1.0}, 0)


def test_eval_command_gates_hosted_on_allowance_ack(tmp_path) -> None:
    from ai_provider.task_scheduler import (
        ResearchTask,
        ResearchTaskSettings,
        ResearchTaskStore,
        eval_command,
    )

    catalog = tmp_path / "cat.toml"
    catalog.write_text("[models]\n", encoding="utf-8")
    store = ResearchTaskStore(tmp_path / "runs.sqlite3")
    plain = ResearchTask(
        "ev-local",
        tmp_path,
        "cat.toml",
        "ollama/qwen3:14b",
        600,
        task_kind="route-eval",
    )
    store.plan(plain)
    assert "--allow-hosted" not in eval_command(store.get_task("ev-local"), store.path)
    acked = ResearchTask(
        "ev-host",
        tmp_path,
        "cat.toml",
        "requesty/m",
        600,
        task_kind="route-eval",
        settings=ResearchTaskSettings(allowance_ack="bd5fa3a2-B"),
    )
    store.plan(acked)
    assert "--allow-hosted" in eval_command(store.get_task("ev-host"), store.path)
