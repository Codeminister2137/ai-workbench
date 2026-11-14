"""Boot reconciliation resumes orphaned runs at dashboard startup."""

from __future__ import annotations

import json

from dashboard_config import load_config
from dashboard_stores import DashboardStores
from dashboard_web_app import build_run_drain, reconcile_runs_at_startup


def test_startup_reconcile_requeues_orphans(tmp_path) -> None:
    config_path = tmp_path / "dashboard.json"
    config_path.write_text(json.dumps({"title": "Test Board"}), encoding="utf-8")
    config = load_config(config_path)
    data_dir = tmp_path / "data"
    stores = DashboardStores(data_dir)
    stores.runs.put(
        "orphan",
        {
            "id": "orphan",
            "title": "t",
            "status": "running",
            "worker_epoch": "boot-1",
            "attempts": 2,
            "updated_at_utc": "2026-11-14T10:00:00+00:00",
        },
    )
    outcomes = reconcile_runs_at_startup(config, data_dir, tmp_path, stores, "boot-2")
    assert outcomes == [{"run_id": "orphan", "action": "requeued"}]
    stored = stores.runs.get("orphan")
    assert stored["status"] == "queued"
    assert stored["events"][-1]["payload"]["reconciled_by_epoch"] == "boot-2"


def test_build_run_drain_stamps_worker_epoch(tmp_path) -> None:
    config_path = tmp_path / "dashboard.json"
    config_path.write_text(json.dumps({"title": "Test Board"}), encoding="utf-8")
    config = load_config(config_path)
    data_dir = tmp_path / "data"
    stores = DashboardStores(data_dir)
    drain = build_run_drain(config, data_dir, tmp_path, stores, worker_epoch="boot-9")
    assert drain._worker_epoch == "boot-9"
    defaulted = build_run_drain(config, data_dir, tmp_path, stores)
    assert defaulted._worker_epoch
