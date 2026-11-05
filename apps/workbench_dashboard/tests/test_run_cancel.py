"""Run-cancel endpoint: flag queued runs, refuse terminal/executing ones."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from dashboard_stores import DashboardStores
from dashboard_web_app import DashboardRequestHandler


@pytest.fixture
def dashboard_server(tmp_path):
    config_path = tmp_path / "dashboard.json"
    config_path.write_text(json.dumps({"title": "Test Board"}), encoding="utf-8")

    class TestHandler(DashboardRequestHandler):
        def log_message(self, format, *args):
            return

    TestHandler.config_path = config_path
    TestHandler.data_dir = tmp_path / "data"
    TestHandler.repo_root = tmp_path
    server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def post_json(base: str, path: str, payload: dict) -> dict:
    request = Request(
        f"{base}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


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
