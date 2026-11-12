"""Supervision Fleet probe: stuck/broken/parked/ok verdicts over runs."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent.parent
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from dashboard_stores import DashboardStores  # noqa: E402
from dashboard_web_app import fleet_agents  # noqa: E402

NOW = datetime(2026, 11, 12, 14, 0, 0, tzinfo=UTC)


def _put(stores, run_id, *, status, age_minutes=None, receipts=None):
    record = {"id": run_id, "title": f"run {run_id}", "status": status}
    if age_minutes is not None:
        record["updated_at_utc"] = (NOW - timedelta(minutes=age_minutes)).isoformat()
    if receipts is not None:
        record["receipts"] = receipts
    stores.runs.put(run_id, record)


def test_verdicts_cover_stuck_broken_parked_and_ok(tmp_path) -> None:
    stores = DashboardStores(tmp_path)
    _put(stores, "stale-run", status="running", age_minutes=45)
    _put(
        stores,
        "fresh-fail",
        status="failed",
        age_minutes=10,
        receipts=[{"status": "failed", "failure_class": "provider"}],
    )
    _put(stores, "old-fail", status="failed", age_minutes=60 * 25)
    _put(stores, "parked", status="queued", age_minutes=90)
    _put(stores, "fresh", status="running", age_minutes=3)
    _put(stores, "done", status="completed", age_minutes=5)
    out = fleet_agents(stores, now=NOW)
    by_id = {item["id"]: item for item in out["runs"]}
    assert by_id["stale-run"]["verdict"] == "stuck"
    assert "45 min" in by_id["stale-run"]["reason"]
    assert by_id["fresh-fail"]["verdict"] == "broken"
    assert by_id["fresh-fail"]["reason"] == "provider"
    assert "old-fail" not in by_id
    assert by_id["parked"]["verdict"] == "parked"
    assert by_id["fresh"]["verdict"] == "ok"
    assert "done" not in by_id
    assert (out["stuck"], out["broken"], out["attention"]) == (1, 1, True)


def test_broken_without_class_and_unknown_age_stay_quiet(tmp_path) -> None:
    stores = DashboardStores(tmp_path)
    _put(stores, "bare-fail", status="failed")
    _put(stores, "undated", status="running")
    out = fleet_agents(stores, now=NOW)
    by_id = {item["id"]: item for item in out["runs"]}
    assert by_id["bare-fail"]["verdict"] == "broken"
    assert by_id["bare-fail"]["reason"] == "unknown"
    assert by_id["undated"]["verdict"] == "ok"
    assert out["attention"] is True


def test_probe_is_fail_soft_on_broken_store() -> None:
    class _Broken:
        def list(self, **kwargs):
            raise OSError("disk gone")

    class _Stores:
        runs = _Broken()

    assert fleet_agents(_Stores(), now=NOW) == {
        "runs": [],
        "stuck": 0,
        "broken": 0,
        "attention": False,
    }
