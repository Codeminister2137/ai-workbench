"""Plan approve endpoint and run receipts endpoint over real file stores."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError

import pytest
from dashboard_stores import DashboardStores, StoreError
from dashboard_test_http import get_json, post_json
from dashboard_web_app import DashboardRequestHandler


@pytest.fixture
def dashboard_server(tmp_path, monkeypatch):
    config_path = tmp_path / "dashboard.json"
    config_path.write_text(
        json.dumps({"provider": "ollama", "model": "fake", "title": "Test Board"}),
        encoding="utf-8",
    )
    data_dir = tmp_path / "data"

    class TestHandler(DashboardRequestHandler):
        def log_message(self, format, *args):
            return

    TestHandler.config_path = config_path
    TestHandler.data_dir = data_dir
    TestHandler.repo_root = tmp_path
    server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def _write_plan(tmp_path, plan_id: str, record: dict) -> None:
    plans_dir = tmp_path / "data" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    (plans_dir / f"{plan_id}.json").write_text(json.dumps(record), encoding="utf-8")


def _write_run(tmp_path, run_id: str, record: dict) -> None:
    runs_dir = tmp_path / "data" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / f"{run_id}.json").write_text(json.dumps(record), encoding="utf-8")


def _proposed_plan(plan_id: str = "plan-1") -> dict:
    return {"id": plan_id, "title": "Widget plan", "status": "proposed", "body": "# Plan"}


def test_decide_plan_approves_and_rejects(tmp_path) -> None:
    stores = DashboardStores(tmp_path / "data")
    stores.plans.put("a", _proposed_plan("a"))
    stores.plans.put("b", _proposed_plan("b"))
    approved = stores.decide_plan("a", approved=True)
    assert approved["status"] == "approved"
    assert approved["decided_at"]
    assert approved["updated_at_utc"]
    rejected = stores.decide_plan("b", approved=False)
    assert rejected["status"] == "rejected"


def test_decide_plan_refuses_unknown_non_proposed_and_non_bool(tmp_path) -> None:
    stores = DashboardStores(tmp_path / "data")
    with pytest.raises(StoreError, match="not found"):
        stores.decide_plan("missing", approved=True)
    stores.plans.put("active", {"id": "active", "title": "t", "status": "active"})
    with pytest.raises(StoreError, match="not awaiting approval"):
        stores.decide_plan("active", approved=True)
    stores.plans.put("p", _proposed_plan("p"))
    with pytest.raises(StoreError, match="true or false"):
        stores.decide_plan("p", approved="yes")  # type: ignore[arg-type]
    untouched = stores.plans.get("p")
    assert untouched is not None
    assert untouched["status"] == "proposed"


def test_get_run_receipts_reads_empty_and_values(tmp_path) -> None:
    stores = DashboardStores(tmp_path / "data")
    with pytest.raises(StoreError, match="not found"):
        stores.get_run_receipts("missing")
    stores.runs.put("bare", {"id": "bare", "title": "t", "status": "completed"})
    assert stores.get_run_receipts("bare") == []
    stores.runs.put("nulls", {"id": "nulls", "receipts": None})
    assert stores.get_run_receipts("nulls") == []
    stores.runs.put("rich", {"id": "rich", "receipts": [{"status": "completed"}]})
    assert stores.get_run_receipts("rich") == [{"status": "completed"}]
    stores.runs.put("broken", {"id": "broken", "receipts": {"status": "completed"}})
    with pytest.raises(StoreError, match="malformed"):
        stores.get_run_receipts("broken")


def test_approve_endpoint_decides_proposed_plan(dashboard_server, tmp_path) -> None:
    _write_plan(tmp_path, "plan-1", _proposed_plan())
    decided = post_json(dashboard_server, "/api/plans/plan-1/approve", {"approved": True})
    assert decided == {"ok": True, "id": "plan-1", "status": "approved"}
    detail = get_json(dashboard_server, "/api/plans/plan-1")
    assert detail["item"]["status"] == "approved"

    _write_plan(tmp_path, "plan-2", _proposed_plan("plan-2"))
    rejected = post_json(dashboard_server, "/api/plans/plan-2/approve", {"approved": False})
    assert rejected["status"] == "rejected"


def test_approve_endpoint_rejects_unknown_and_decided(dashboard_server, tmp_path) -> None:
    with pytest.raises(HTTPError) as raised:
        post_json(dashboard_server, "/api/plans/nope/approve", {"approved": True})
    assert raised.value.code == 404
    raised.value.close()

    _write_plan(tmp_path, "plan-1", _proposed_plan())
    post_json(dashboard_server, "/api/plans/plan-1/approve", {"approved": True})
    with pytest.raises(HTTPError) as raised:
        post_json(dashboard_server, "/api/plans/plan-1/approve", {"approved": True})
    assert raised.value.code == 400
    raised.value.close()


def test_approve_endpoint_validates_payload_and_status(dashboard_server, tmp_path) -> None:
    _write_plan(tmp_path, "active", {"id": "active", "title": "t", "status": "active"})
    with pytest.raises(HTTPError) as raised:
        post_json(dashboard_server, "/api/plans/active/approve", {"approved": True})
    assert raised.value.code == 400
    raised.value.close()

    _write_plan(tmp_path, "plan-1", _proposed_plan())
    for payload in ({}, {"approved": "yes"}, {"approved": 1}):
        with pytest.raises(HTTPError) as raised:
            post_json(dashboard_server, "/api/plans/plan-1/approve", payload)
        assert raised.value.code == 400
        raised.value.close()


def test_receipts_endpoint_returns_empty_and_values(dashboard_server, tmp_path) -> None:
    _write_run(tmp_path, "bare", {"id": "bare", "title": "t", "status": "completed"})
    empty = get_json(dashboard_server, "/api/runs/bare/receipts")
    assert empty == {"ok": True, "receipts": []}

    receipts = [{"status": "completed", "summary": "done"}, {"status": "failed"}]
    _write_run(tmp_path, "rich", {"id": "rich", "status": "failed", "receipts": receipts})
    payload = get_json(dashboard_server, "/api/runs/rich/receipts")
    assert payload == {"ok": True, "receipts": receipts}

    with pytest.raises(HTTPError) as raised:
        get_json(dashboard_server, "/api/runs/nope/receipts")
    assert raised.value.code == 404
    raised.value.close()


def test_receipts_endpoint_rejects_malformed(dashboard_server, tmp_path) -> None:
    _write_run(tmp_path, "broken", {"id": "broken", "receipts": "nope"})
    with pytest.raises(HTTPError) as raised:
        get_json(dashboard_server, "/api/runs/broken/receipts")
    assert raised.value.code == 400
    raised.value.close()


def test_run_detail_routing_unaffected_by_receipts(dashboard_server, tmp_path) -> None:
    _write_run(
        tmp_path,
        "w4",
        {"id": "w4", "title": "W4", "status": "completed", "receipts": [{"status": "completed"}]},
    )
    detail = get_json(dashboard_server, "/api/runs/w4")
    assert detail["item"]["title"] == "W4"
    assert detail["item"]["fanout_effective"] == "unknown"
