"""Day-cycle verdict logic; service checks are never executed here."""

import importlib.util
import os
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/day_cycle.py"
_spec = importlib.util.spec_from_file_location("day_cycle", SCRIPT)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)

GitState = _module.GitState
close_verdict = _module.close_verdict
without_warnings = _module.without_warnings
docker_desktop_candidates = _module.docker_desktop_candidates
ensure_docker = _module.ensure_docker
parse_process_count = _module.parse_process_count
service_env = _module.service_env
start_detached = _module.start_detached


def test_close_verdict_clean_trees() -> None:
    states = [
        GitState("/repo/ai-workbench", "develop", True, 0, 0, "abc123"),
        GitState("/repo/remote-ai-operator", "main", True, 0, 0, "def456"),
    ]
    ok, blockers = close_verdict(states)
    assert ok is True
    assert blockers == []


def test_close_verdict_reports_every_blocker() -> None:
    states = [
        GitState("/repo/ai-workbench", "develop", False, 2, 1, "abc123"),
        GitState("/repo/remote-ai-operator", "?", False, 0, 0, "?"),
    ]
    ok, blockers = close_verdict(states)
    assert ok is False
    assert len(blockers) == 4
    assert any("uncommitted" in blocker for blocker in blockers)
    assert any("unpushed" in blocker for blocker in blockers)
    assert any("behind origin" in blocker for blocker in blockers)
    assert any("unreadable" in blocker for blocker in blockers)


def test_without_warnings_strips_warning_lines_only() -> None:
    raw = "abc123\nwarning: could not open directory 'x/': Permission denied\n"
    assert without_warnings(raw) == "abc123\n"
    assert without_warnings("") == ""
    assert without_warnings("clean\noutput\n") == "clean\noutput\n"


def test_parse_process_count_reads_powershell_count() -> None:
    assert parse_process_count("2\r\n") == 2
    assert parse_process_count("0") == 0
    assert parse_process_count("") == 0
    assert parse_process_count("runner error: boom") == 0


def test_docker_desktop_candidates_point_at_exe() -> None:
    candidates = docker_desktop_candidates()
    assert candidates, "at least one well-known install path"
    assert all(path.name == "Docker Desktop.exe" for path in candidates)


def test_ensure_docker_up_touches_nothing() -> None:
    calls: list[str] = []
    ok, line = ensure_docker(
        state_fn=lambda: {"available": True, "server_version": "29.2.1"},
        running_fn=lambda: (_ for _ in ()).throw(AssertionError("must not check")),
        launch_fn=lambda exe: calls.append(str(exe)) or True,
        sleep_fn=lambda seconds: calls.append(f"sleep{seconds}"),
    )
    assert (ok, line) == (True, "docker: daemon up")
    assert calls == []


def test_ensure_docker_launches_and_waits(tmp_path) -> None:
    exe = tmp_path / "Docker Desktop.exe"
    exe.write_text("fake")
    launched: list[str] = []
    states = iter([False, True])
    ok, line = ensure_docker(
        state_fn=lambda: {"available": next(states), "server_version": None},
        running_fn=lambda: False,
        launch_fn=lambda candidate: launched.append(str(candidate)) or True,
        sleep_fn=lambda seconds: None,
        candidates_fn=lambda: [exe],
    )
    assert ok is True
    assert "daemon up" in line
    assert launched == [str(exe)]


def test_ensure_docker_reports_when_desktop_missing() -> None:
    ok, line = ensure_docker(
        state_fn=lambda: {"available": False, "server_version": None},
        running_fn=lambda: False,
        launch_fn=lambda exe: True,
        sleep_fn=lambda seconds: None,
        candidates_fn=lambda: [],
    )
    assert ok is False
    assert "manually" in line


def test_ensure_docker_reports_launch_failure(tmp_path) -> None:
    exe = tmp_path / "Docker Desktop.exe"
    exe.write_text("fake")
    ok, line = ensure_docker(
        state_fn=lambda: {"available": False, "server_version": None},
        running_fn=lambda: False,
        launch_fn=lambda candidate: False,
        sleep_fn=lambda seconds: None,
        candidates_fn=lambda: [exe],
    )
    assert ok is False
    assert "FAILED" in line


def test_ensure_docker_times_out_when_daemon_never_arrives() -> None:
    ok, line = ensure_docker(
        wait_seconds=0,
        state_fn=lambda: {"available": False, "server_version": None},
        running_fn=lambda: True,
        launch_fn=lambda exe: True,
        sleep_fn=lambda seconds: None,
    )
    assert ok is False
    assert "still down" in line


def test_service_env_returns_only_allowlisted_names(tmp_path, monkeypatch) -> None:
    (tmp_path / ".env").write_text(
        "OPERATOR_ACCESS_TOKEN=fake-token\nEXTRA_KEY=1\nEMPTY=\n", encoding="utf-8"
    )
    monkeypatch.delenv("OPERATOR_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("EXTRA_KEY", raising=False)
    try:
        assert service_env("operator-serve", store=tmp_path / "missing") == {}
        assert service_env("operator-serve", store=tmp_path) == {
            "OPERATOR_ACCESS_TOKEN": "fake-token"
        }
        assert service_env("dashboard", store=tmp_path) == {}

    finally:
        os.environ.pop("OPERATOR_ACCESS_TOKEN", None)
        os.environ.pop("EXTRA_KEY", None)


def test_start_detached_passes_env_through(tmp_path, monkeypatch) -> None:
    captured: dict = {}

    class FakePopen:
        def __init__(self, argv, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(_module.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(_module, "SNAPSHOT_DIR", tmp_path)
    assert start_detached("svc", ["echo", "hi"], tmp_path, env={"K": "V"}) is True
    assert captured["env"]["K"] == "V"
    assert "PATH" in captured["env"] or "Path" in captured["env"]
