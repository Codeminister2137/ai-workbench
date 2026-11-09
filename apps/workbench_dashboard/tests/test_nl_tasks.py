"""NL task proposals: parsing, model routing, approval-gated endpoint."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError

import pytest
from dashboard_test_http import get_json, post_json
from dashboard_web_app import DashboardRequestHandler
from nl_tasks import propose_task


@pytest.fixture
def nl_server(tmp_path, monkeypatch):
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
    monkeypatch.setattr(server, "shutdown", server.shutdown)
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join(timeout=5)


def test_propose_routes_coder_and_parses_duration() -> None:
    proposal = propose_task("Review the auth module, about 30 min")
    assert proposal["model"] == "qwen2.5-coder:14b"
    assert proposal["required_seconds"] == 1800.0
    assert proposal["task_id"].startswith("review-the-auth-module")


def test_propose_routes_thinker_and_defaults() -> None:
    proposal = propose_task("Plan the migration approach")
    assert proposal["model"] == "qwen3:14b"
    assert proposal["required_seconds"] == 600.0


def test_propose_rejects_empty_and_overlong() -> None:
    with pytest.raises(ValueError, match="required"):
        propose_task("   ")
    with pytest.raises(ValueError, match="exceeds"):
        propose_task("x" * 2001)


def test_propose_endpoint_files_inbox_order(nl_server) -> None:
    out = post_json(nl_server, "/api/tasks/propose", {"text": "Fix the flaky login test, 1h"})
    assert out["ok"] is True
    assert out["proposal"]["model"] == "qwen2.5-coder:14b"
    assert out["proposal"]["required_seconds"] == 3600.0
    item = get_json(nl_server, f"/api/inbox/{out['id']}")["item"]
    assert item["type"] == "order"
    assert item["status"] == "open"
    assert "qwen2.5-coder:14b" in item["body"]


def test_propose_endpoint_rejects_bad_input(nl_server) -> None:
    with pytest.raises(HTTPError) as exc:
        post_json(nl_server, "/api/tasks/propose", {"text": ""})
    assert exc.value.code == 400
