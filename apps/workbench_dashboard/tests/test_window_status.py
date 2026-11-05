"""Agent window status: never-raises reader, rounding writer, status endpoint."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen

import pytest
from dashboard_web_app import DashboardRequestHandler
from window_status import load_window_status, write_window_status


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


def test_missing_file_means_idle(tmp_path) -> None:
    assert load_window_status(tmp_path) == {"running": False}


def test_malformed_file_yields_defaults(tmp_path) -> None:
    (tmp_path / "window-status.json").write_text("{nope", encoding="utf-8")
    status = load_window_status(tmp_path)
    assert status["running"] is False
    assert status["agents"] == []
    assert status["slice"] == ""


def test_non_dict_file_yields_defaults(tmp_path) -> None:
    (tmp_path / "window-status.json").write_text("[1, 2]", encoding="utf-8")
    assert load_window_status(tmp_path)["running"] is False


def test_full_status_round_trips(tmp_path) -> None:
    stored = write_window_status(
        tmp_path,
        slice="mail-slice",
        phase="implement",
        started_utc="2026-11-05T10:00:00+00:00",
        last_heartbeat_utc="2026-11-05T11:00:00+00:00",
        note="wiring hooks",
        agents=[{"name": "coder", "task": "mail", "status": "working"}],
    )
    assert stored["running"] is True
    assert load_window_status(tmp_path) == stored


def test_writer_drops_unknown_keys_and_bad_agents(tmp_path) -> None:
    stored = write_window_status(
        tmp_path,
        slice="s",
        bogus_key="dropped",
        agents=[
            {"name": "ok", "task": "t", "status": "s"},
            {"name": "", "task": "t", "status": "s"},
            {"task": "nameless"},
            "not-a-dict",
        ],
    )
    assert "bogus_key" not in stored
    assert stored["agents"] == [{"name": "ok", "task": "t", "status": "s"}]
    assert load_window_status(tmp_path) == stored


def test_reader_coerces_bad_field_types(tmp_path) -> None:
    (tmp_path / "window-status.json").write_text(
        json.dumps({"slice": 42, "agents": {"name": "x"}}), encoding="utf-8"
    )
    status = load_window_status(tmp_path)
    assert status["running"] is True
    assert status["slice"] == ""
    assert status["agents"] == []


def test_agent_status_endpoint_idle(dashboard_server) -> None:
    with urlopen(f"{dashboard_server}/api/agent-status", timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    assert payload == {"ok": True, "running": False}


def test_agent_status_endpoint_live(dashboard_server, tmp_path) -> None:
    write_window_status(tmp_path, slice="mail-slice", note="wiring hooks")
    with urlopen(f"{dashboard_server}/api/agent-status", timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    assert payload["ok"] is True
    assert payload["running"] is True
    assert payload["slice"] == "mail-slice"
