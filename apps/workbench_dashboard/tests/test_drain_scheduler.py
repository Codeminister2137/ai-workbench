"""Drain scheduler: periodic ticks off by default, shared drain builder."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from dashboard_config import DashboardConfig, load_config
from dashboard_stores import DashboardStores
from dashboard_web_app import (
    build_run_drain,
    should_start_drain_scheduler,
)
from drain_scheduler import DrainScheduler


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_scheduler_ticks_then_stops() -> None:
    calls: list = []
    done = threading.Event()

    def tick() -> None:
        calls.append(1)
        if len(calls) >= 3:
            done.set()

    scheduler = DrainScheduler(tick, 0.02)
    assert scheduler.started is False
    assert scheduler.start() is True
    assert scheduler.started is True
    assert done.wait(5.0) is True
    scheduler.stop()
    assert scheduler.started is False
    assert scheduler.ticks >= 3
    assert scheduler.errors == 0


def test_scheduler_survives_tick_errors() -> None:
    calls: list = []
    done = threading.Event()

    def tick() -> None:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        done.set()

    scheduler = DrainScheduler(tick, 0.02)
    scheduler.start()
    assert done.wait(5.0) is True
    scheduler.stop()
    assert scheduler.errors == 1
    assert scheduler.ticks >= 1
    assert scheduler.last_error is not None and "boom" in scheduler.last_error


def test_scheduler_double_start_refused() -> None:
    scheduler = DrainScheduler(lambda: None, 60.0)
    try:
        assert scheduler.start() is True
        assert scheduler.start() is False
    finally:
        scheduler.stop()


def test_scheduler_rejects_non_positive_interval() -> None:
    with pytest.raises(ValueError, match="positive"):
        DrainScheduler(lambda: None, 0)


def test_drain_interval_defaults_off(tmp_path: Path) -> None:
    assert DashboardConfig().drain_interval_seconds == 0
    assert should_start_drain_scheduler(DashboardConfig()) is False
    config_path = tmp_path / "dashboard.json"
    config_path.write_text(json.dumps({"title": "t"}), encoding="utf-8")
    assert load_config(config_path).drain_interval_seconds == 0


def test_drain_interval_parses_and_validates(tmp_path: Path) -> None:
    config_path = tmp_path / "dashboard.json"
    config_path.write_text(json.dumps({"drain_interval_seconds": 300}), encoding="utf-8")
    assert load_config(config_path).drain_interval_seconds == 300
    assert should_start_drain_scheduler(load_config(config_path)) is True
    config_path.write_text(json.dumps({"drain_interval_seconds": 30}), encoding="utf-8")
    assert should_start_drain_scheduler(load_config(config_path)) is False
    config_path.write_text(json.dumps({"drain_interval_seconds": -1}), encoding="utf-8")
    with pytest.raises(ValueError, match="zero or greater"):
        load_config(config_path)


def test_shared_builder_drains_seeded_run(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write(
        data_dir / "runs" / "r1.json",
        {
            "id": "r1",
            "title": "Seeded",
            "status": "queued",
            "body": "Do it",
            "origin": "chat",
            "session_id": "s",
            "fanout_policy": "restricted",
            "fanout_effective": "restricted",
            "inbox_id": "i1",
            "project_id": None,
            "plan_id": None,
        },
    )
    _write(
        data_dir / "inbox" / "i1.json",
        {"id": "i1", "status": "answered", "answer": "Approve"},
    )
    calls: list = []

    def fake_factory():
        def fake_executor(run: dict) -> dict:
            calls.append(run["id"])
            return {"status": "completed", "summary": "fake"}

        return fake_executor

    config = DashboardConfig(work_roots=())
    drain = build_run_drain(
        config, data_dir, tmp_path, DashboardStores(data_dir), executor_factory=fake_factory
    )
    outcomes = drain.drain(max_runs=1)
    assert calls == ["r1"]
    assert outcomes[0]["status"] == "completed"
