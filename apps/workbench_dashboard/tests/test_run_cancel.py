"""Run-cancel endpoint: flag queued runs, refuse terminal/executing ones."""

from __future__ import annotations

from urllib.error import HTTPError

import pytest
from dashboard_stores import DashboardStores
from dashboard_test_http import post_json


def _put_run(tmp_path, run_id: str, status: str) -> None:
    DashboardStores(tmp_path / "data").runs.put(
        run_id, {"id": run_id, "title": "t", "status": status}
    )


def test_cancel_queued_run_flags_it(dashboard_server, tmp_path) -> None:
    _put_run(tmp_path, "r1", "queued")
    payload = post_json(dashboard_server, "/api/runs/r1/cancel", {})
    assert payload["ok"] is True
    assert payload["run"]["cancel_requested"] is True
    stored = DashboardStores(tmp_path / "data").runs.get("r1")
    assert stored is not None
    assert stored["cancel_requested"] is True
    assert stored["events"][-1]["kind"] == "cancellation_requested"


def test_cancel_missing_run_404(dashboard_server) -> None:
    with pytest.raises(HTTPError) as exc:
        post_json(dashboard_server, "/api/runs/ghost/cancel", {})
    assert exc.value.code == 404


def test_cancel_terminal_run_refused(dashboard_server, tmp_path) -> None:
    _put_run(tmp_path, "r1", "completed")
    with pytest.raises(HTTPError) as exc:
        post_json(dashboard_server, "/api/runs/r1/cancel", {})
    assert exc.value.code == 400


def test_cancel_running_run_refused(dashboard_server, tmp_path) -> None:
    _put_run(tmp_path, "r1", "running")
    with pytest.raises(HTTPError) as exc:
        post_json(dashboard_server, "/api/runs/r1/cancel", {})
    assert exc.value.code == 400
