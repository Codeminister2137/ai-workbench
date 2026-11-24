"""Agent-executed E2E checks: extraction allowlist and execution shape."""

from __future__ import annotations

from pathlib import Path

import e2e_agent_checks


def test_extract_command_allows_pytest_and_help() -> None:
    assert (
        e2e_agent_checks.extract_command("Run `.venv/Scripts/python.exe -m pytest x -q` now")
        == ".venv/Scripts/python.exe -m pytest x -q"
    )
    assert e2e_agent_checks.extract_command("Try `ruff --help` first") == "ruff --help"


def test_extract_command_rejects_prose_and_shell() -> None:
    assert e2e_agent_checks.extract_command("Run the scoped pytest") is None
    assert e2e_agent_checks.extract_command("No backticks here") is None
    assert e2e_agent_checks.extract_command("Run `pytest x & del y`") is None
    assert e2e_agent_checks.extract_command("Run `x; y --help`") is None
    assert e2e_agent_checks.extract_command("Run `$(evil) --help`") is None


def test_extract_command_allows_dryrun_and_http_get() -> None:
    assert (
        e2e_agent_checks.extract_command(
            "Rehearse `.venv/Scripts/python.exe scripts/allowance_healthcheck.py --dry-run`"
        )
        == ".venv/Scripts/python.exe scripts/allowance_healthcheck.py --dry-run"
    )
    assert (
        e2e_agent_checks.extract_command(
            "Probe `.venv/Scripts/python.exe scripts/e2e-http-get.py /api/settings 200`"
        )
        == ".venv/Scripts/python.exe scripts/e2e-http-get.py /api/settings 200"
    )
    assert (
        e2e_agent_checks.extract_command(
            "Run `.venv/Scripts/python.exe scripts/run-tests.py dashboard`"
        )
        == ".venv/Scripts/python.exe scripts/run-tests.py dashboard"
    )
    assert (
        e2e_agent_checks.extract_command("Run `.venv/Scripts/python.exe scripts/run-tests.py full`")
        is None
    )
    assert e2e_agent_checks.extract_command("Run `scripts/x.py --dry-run`") is None
    assert (
        e2e_agent_checks.extract_command("Probe `scripts/e2e-http-get.py /api/x notanum`") is None
    )


def test_http_get_probe_checks_status_and_shape() -> None:
    import importlib.util
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "e2e_http_get", root / "scripts" / "e2e-http-get.py"
    )
    assert spec is not None and spec.loader is not None
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib name
            if self.path == "/api/ok":
                body = b'{"ok": true}'
            elif self.path == "/api/plain":
                body = b"not json"
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib shape
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        assert probe.check(base, "/api/ok", 200)[0] is True
        assert probe.check(base, "/api/plain", 200)[0] is False
        assert probe.check(base, "/api/missing", 404)[0] is True
        assert probe.check(base, "/api/ok", 404)[0] is False
    finally:
        server.shutdown()


def test_execute_check_uses_runner_and_truncates(tmp_path: Path) -> None:
    seen: dict = {}

    def fake_runner(argv, repo_root):
        seen["argv"] = list(argv)
        seen["root"] = repo_root
        return 3, "o" * 9000

    result = e2e_agent_checks.execute_check(
        "Run `.venv/Scripts/python.exe -m pytest x -q`", tmp_path, runner=fake_runner
    )
    assert result["command"] == ".venv/Scripts/python.exe -m pytest x -q"
    assert result["exit_code"] == 3
    assert isinstance(result["output"], str)
    assert len(result["output"]) == e2e_agent_checks.EVIDENCE_CHARS
    assert seen["argv"][0] == ".venv/Scripts/python.exe"
    assert seen["root"] == tmp_path


def test_default_runner_honors_timeout_override(tmp_path) -> None:
    code, output = e2e_agent_checks._default_runner(
        ["python", "-c", "import time; time.sleep(30)"], tmp_path, timeout_seconds=1
    )
    assert code == 124
    assert output.endswith("[TIMEOUT]")


def test_default_runner_anchors_relative_program_at_repo_root(tmp_path: Path, monkeypatch) -> None:
    """Windows resolves relative programs against the CALLER cwd, not the
    child cwd param: serve lives elsewhere, so anchor at the repo root."""
    import os

    bindir = tmp_path / "repo" / "bin"
    bindir.mkdir(parents=True)
    if os.name == "nt":
        prog = bindir / "hello.cmd"
        prog.write_text("@echo hello-from-repo\r\n", encoding="utf-8")
        argv = ["bin/hello.cmd"]
    else:
        prog = bindir / "hello.sh"
        prog.write_text("#!/bin/sh\necho hello-from-repo\n", encoding="utf-8")
        argv = ["bin/hello.sh"]
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    code, output = e2e_agent_checks._default_runner(argv, tmp_path / "repo")
    assert code == 0
    assert "hello-from-repo" in output


def test_summarize_evidence_shows_exit_plus_last_meaningful_line() -> None:
    assert (
        e2e_agent_checks.summarize_evidence(".....\n22 passed in 0.57s\n", 0)
        == "exit 0: 22 passed in 0.57s"
    )
    assert e2e_agent_checks.summarize_evidence(".....\n.....\n", 0) == "exit 0: no output captured"
    assert e2e_agent_checks.summarize_evidence("", 127) == "exit 127: no output captured"
    long = "x" * 300
    assert e2e_agent_checks.summarize_evidence(long, 1).endswith("...")
    assert e2e_agent_checks.summarize_evidence(None, None) == "exit ?: no output captured"


def test_execute_check_refuses_unrunnable(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ValueError, match="no exact runnable command"):
        e2e_agent_checks.execute_check("Just look at it", tmp_path)


def test_auto_checks_persist_invalid_step_and_continue(monkeypatch):
    from types import SimpleNamespace

    from dashboard_web_app import DashboardRequestHandler

    steps = [
        {"agent_runnable": True, "action": "invalid"},
        {"agent_runnable": True, "action": "valid"},
    ]
    record = {"status": "open", "items": [{"steps": steps}]}
    saved = []
    store = SimpleNamespace(get=lambda task_id: record, put=lambda *args: saved.append(args))
    handler = object.__new__(DashboardRequestHandler)
    monkeypatch.setattr(handler, "_stores", lambda: SimpleNamespace(e2e_tasks=store))

    def attach(steps, index, timeout):
        if index == 0:
            raise ValueError("private detail")
        steps[index]["evidence"] = "passed"

    monkeypatch.setattr(handler, "_attach_step_evidence", attach)
    handler._auto_run_pending_checks("task")
    assert saved == [("task", record)]
    assert steps[0]["evidence"] == "[auto-check failed: private detail]"
    assert steps[0]["evidence_utc"]
    assert steps[0]["evidence_exit"] is None
    assert steps[1]["evidence"] == "passed"
