"""Run-cancel endpoint: flag queued runs, refuse terminal/executing ones."""

from __future__ import annotations

from urllib.error import HTTPError

import pytest
from dashboard_stores import DashboardStores
from dashboard_test_http import get_json, post_json


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


def test_cancel_claim_only_run_prevents_pickup(dashboard_server, tmp_path, monkeypatch) -> None:
    from ai_agent.supervisor_drain import RunDrain

    stores = DashboardStores(tmp_path / "data")
    _put_run(tmp_path, "r1", "queued")
    run = stores.runs.get("r1")
    assert run is not None
    run["approval_mode"] = "agent-queue"
    path = stores.runs.put("r1", run)
    rename = type(path).rename
    calls = []

    def cancel_after_claim(source, target):
        result = rename(source, target)
        if source == path:
            assert not path.exists()
            payload = post_json(dashboard_server, "/api/runs/r1/cancel", {})
            assert payload["run"]["cancel_requested"] is True
            assert not path.exists()
            claimed = stores.runs.get("r1", claim=True)
            assert claimed is not None
            assert claimed["events"][-1]["kind"] == "cancellation_requested"
        return result

    monkeypatch.setattr(type(path), "rename", cancel_after_claim)

    def executor(run):
        calls.append(run)
        return {"status": "completed", "summary": "done"}

    drain = RunDrain(
        runs_dir=stores.runs.directory,
        get_inbox=stores.inbox.get,
        executor=executor,
    )
    assert drain.drain() == [{"run_id": "r1", "status": "cancelled"}]
    assert calls == []
    stored = stores.runs.get("r1")
    assert stored is not None
    assert stored["status"] == "cancelled"
    assert not list(stores.runs.directory.glob("*.claim"))


@pytest.mark.parametrize("status", ["running", "completed"])
def test_cancel_claim_only_refuses_executing_or_terminal(dashboard_server, tmp_path, status):
    stores = DashboardStores(tmp_path / "data")
    stores.runs.put("r1", {"id": "r1", "status": status}, claim=True)
    with pytest.raises(HTTPError) as exc:
        post_json(dashboard_server, "/api/runs/r1/cancel", {})
    assert exc.value.code == 400
    assert stores.runs.get("r1") is None
    claimed = stores.runs.get("r1", claim=True)
    assert claimed is not None
    assert "cancel_requested" not in claimed


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


def test_fanout_change_queued_run(dashboard_server, tmp_path) -> None:
    _put_run(tmp_path, "r1", "queued")
    payload = post_json(dashboard_server, "/api/runs/r1/fanout", {"policy": "allowed"})
    assert payload["ok"] is True
    assert payload["run"]["fanout_effective"] == "allowed"
    stored = get_json(dashboard_server, "/api/runs/r1")
    assert stored["item"]["fanout_policy"] == "allowed"
    assert stored["item"]["fanout_effective"] == "allowed"


def test_fanout_rejects_bad_policy_and_wrong_state(dashboard_server, tmp_path) -> None:
    _put_run(tmp_path, "r1", "queued")
    with pytest.raises(HTTPError) as exc:
        post_json(dashboard_server, "/api/runs/r1/fanout", {"policy": "sometimes"})
    assert exc.value.code == 400
    _put_run(tmp_path, "r2", "running")
    with pytest.raises(HTTPError) as exc:
        post_json(dashboard_server, "/api/runs/r2/fanout", {"policy": "allowed"})
    assert exc.value.code == 409
    _put_run(tmp_path, "r3", "completed")
    with pytest.raises(HTTPError) as exc:
        post_json(dashboard_server, "/api/runs/r3/fanout", {"policy": "allowed"})
    assert exc.value.code == 409
    with pytest.raises(HTTPError) as exc:
        post_json(dashboard_server, "/api/runs/ghost/fanout", {"policy": "allowed"})
    assert exc.value.code == 404
