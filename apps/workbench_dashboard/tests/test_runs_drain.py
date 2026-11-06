from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from dashboard_web_app import DashboardRequestHandler


@pytest.fixture
def drain_server(tmp_path, monkeypatch):
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
    calls: list = []

    def fake_factory():
        def fake_executor(run: dict) -> dict:
            calls.append(run["id"])
            return {"status": "completed", "summary": "fake ran it"}

        return fake_executor

    monkeypatch.setattr(TestHandler, "drain_executor_factory", staticmethod(fake_factory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", tmp_path, calls
    finally:
        server.shutdown()
        server.server_close()


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_run(tmp_path: Path, run_id: str, inbox_id: str, **overrides) -> None:
    record = {
        "id": run_id,
        "title": "Seeded run",
        "status": "queued",
        "body": "Do the thing",
        "origin": "chat",
        "session_id": "dashboard-test",
        "fanout_policy": "restricted",
        "fanout_effective": "restricted",
        "inbox_id": inbox_id,
        "project_id": None,
        "plan_id": None,
    }
    record.update(overrides)
    _write(tmp_path / "data" / "runs" / f"{run_id}.json", record)


def _seed_inbox(tmp_path: Path, inbox_id: str, *, status: str, answer=None) -> None:
    _write(
        tmp_path / "data" / "inbox" / f"{inbox_id}.json",
        {"id": inbox_id, "status": status, "answer": answer},
    )


def _drain(base: str, payload: dict) -> dict:
    request = Request(
        f"{base}/api/runs/drain",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _drain_status(base: str, payload: dict) -> int:
    request = Request(
        f"{base}/api/runs/drain",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10):
            return 200
    except HTTPError as exc:
        return exc.code


def test_drain_parks_unapproved_run(drain_server) -> None:
    base, tmp_path, calls = drain_server
    _seed_run(tmp_path, "run1", "inbox1")
    _seed_inbox(tmp_path, "inbox1", status="open")

    out = _drain(base, {})
    assert out["ok"] is True
    assert out["outcomes"][0]["action"] == "parked"
    assert calls == []
    run = json.loads((tmp_path / "data" / "runs" / "run1.json").read_text())
    assert run["status"] == "queued"


def test_drain_executes_approved_run(drain_server) -> None:
    base, tmp_path, calls = drain_server
    _seed_run(tmp_path, "run1", "inbox1")
    _seed_inbox(tmp_path, "inbox1", status="answered", answer="Approve")

    out = _drain(base, {})
    assert out["ok"] is True
    assert out["outcomes"][0]["status"] == "completed"
    assert calls == ["run1"]
    run = json.loads((tmp_path / "data" / "runs" / "run1.json").read_text())
    assert run["status"] == "completed"


def test_drain_skips_cancelled_run(drain_server) -> None:
    base, tmp_path, calls = drain_server
    _seed_run(tmp_path, "run1", "inbox1", cancel_requested=True)
    _seed_inbox(tmp_path, "inbox1", status="answered", answer="Approve")

    out = _drain(base, {})
    assert out["ok"] is True
    assert out["outcomes"][0]["status"] == "cancelled"
    assert calls == []


def test_drain_defaults_to_one_run(drain_server) -> None:
    base, tmp_path, calls = drain_server
    _seed_run(tmp_path, "run1", "inbox1")
    _seed_run(tmp_path, "run2", "inbox2")
    _seed_inbox(tmp_path, "inbox1", status="answered", answer="Approve")
    _seed_inbox(tmp_path, "inbox2", status="answered", answer="Approve")

    out = _drain(base, {})
    executed = [o for o in out["outcomes"] if "action" not in o]
    assert len(executed) == 1
    assert len(calls) == 1


def test_drain_rejects_bad_max_runs(drain_server) -> None:
    base, _tmp_path, _calls = drain_server
    assert _drain_status(base, {"max_runs": 0}) == 400
    assert _drain_status(base, {"max_runs": 101}) == 400
    assert _drain_status(base, {"max_runs": "many"}) == 400
    assert _drain_status(base, {"max_runs": True}) == 400
