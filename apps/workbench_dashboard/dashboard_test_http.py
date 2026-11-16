"""Shared HTTP test helpers for the dashboard suite (tests import these)."""

from __future__ import annotations

import contextlib
import json
import threading
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen


def post_json(base: str, path: str, payload: dict, timeout: int = 10) -> dict:
    """POST a JSON payload to the dashboard test server."""
    request = Request(
        f"{base}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(base: str, path: str) -> dict:
    """GET a JSON payload from the dashboard test server."""
    with urlopen(f"{base}{path}", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


@contextlib.contextmanager
def serve_dashboard(
    tmp_path: Path,
    config: dict | None = None,
    drain_calls: list | None = None,
) -> Iterator[tuple[str, Path]]:
    """Serve the dashboard app from a blank tmp data dir; single shared skeleton.

    Yields (base_url, tmp_path). When drain_calls is a list, a fake drain
    executor records run ids into it (covers the drain/schedule fixtures).
    """
    from dashboard_web_app import DashboardRequestHandler

    config_path = tmp_path / "dashboard.json"
    config_path.write_text(
        json.dumps(
            config
            if config is not None
            else {"provider": "ollama", "model": "fake", "title": "Test Board"}
        ),
        encoding="utf-8",
    )

    class TestHandler(DashboardRequestHandler):
        def log_message(self, format, *args):
            return

    TestHandler.config_path = config_path
    TestHandler.data_dir = tmp_path / "data"
    TestHandler.repo_root = tmp_path
    if drain_calls is not None:

        def fake_factory():
            def fake_executor(run: dict) -> dict:
                drain_calls.append(run["id"])
                return {"status": "completed", "summary": "fake ran it"}

            return fake_executor

        TestHandler.drain_executor_factory = staticmethod(fake_factory)
    server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", tmp_path
    finally:
        server.shutdown()
        server.server_close()
