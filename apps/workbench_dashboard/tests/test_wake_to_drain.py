"""Wake-to-receipt integration: chat request, inbox approval, drain, receipts.

Exercises the real HTTP app plus the real drain against the real file stores;
only the run executor is a fixture (the AgentLoop wiring is a later slice).
"""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer

import pytest
from ai_agent.supervisor_drain import RunDrain
from dashboard_stores import DashboardStores
from dashboard_test_http import get_json, post_json
from dashboard_web_app import DashboardRequestHandler


@pytest.fixture
def wake_server(tmp_path, monkeypatch):
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
        yield f"http://127.0.0.1:{server.server_port}", tmp_path
    finally:
        server.shutdown()
        server.server_close()


def _drain(data_dir, calls: list) -> RunDrain:
    stores = DashboardStores(data_dir)

    def executor(run: dict) -> dict:
        calls.append(run)
        return {"status": "completed", "summary": "fixture did it"}

    return RunDrain(runs_dir=data_dir / "runs", get_inbox=stores.inbox.get, executor=executor)


def test_preapproved_runs_to_receipt(wake_server) -> None:
    """Chat request is pre-approved: drain executes, receipts are served."""
    base, tmp_path = wake_server
    created = post_json(base, "/api/chat/sessions", {"title": "Wake me"})
    receipt = post_json(
        base,
        f"/api/chat/sessions/{created['id']}/run-request",
        {"text": "Summarize plans"},
    )
    assert receipt["status"] == "preapproved"
    assert receipt["inbox_id"] is None
    run_id = receipt["run_id"]

    calls: list = []
    outcomes = _drain(tmp_path / "data", calls).drain()
    assert outcomes == [{"run_id": run_id, "status": "completed"}]
    assert [call["id"] for call in calls] == [run_id]

    run = get_json(base, f"/api/runs/{run_id}")
    assert run["item"]["status"] == "completed"
    assert run["item"]["fanout_effective"] == "restricted"
    receipts = get_json(base, f"/api/runs/{run_id}/receipts")
    assert receipts["receipts"] == [{"status": "completed", "summary": "fixture did it"}]


def test_reject_parks_forever(wake_server) -> None:
    """A Rejected agent-filed run never executes across drain passes."""
    base, tmp_path = wake_server
    post_json(
        base,
        "/api/inbox",
        {"title": "Agent chore", "body": "Do it", "type": "task", "assignee": "agent"},
    )
    bridged = post_json(base, "/api/inbox/bridge-runs", {})
    assert bridged["ok"] is True
    assert len(bridged["bridged"]) == 1
    run_id = bridged["bridged"][0]["run_id"]
    approval_id = bridged["bridged"][0]["approval_id"]
    post_json(base, f"/api/inbox/{approval_id}/answer", {"answer": "", "option_index": 1})

    calls: list = []
    drain = _drain(tmp_path / "data", calls)
    assert drain.drain()[0]["action"] == "parked"
    assert drain.drain()[0]["action"] == "parked"
    assert calls == []
    run = get_json(base, f"/api/runs/{run_id}")
    assert run["item"]["status"] == "queued"
