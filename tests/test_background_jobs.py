"""Background shell jobs: start/poll/stop, cursors, caps, eviction."""

from __future__ import annotations

import shutil
import sys
import time

import pytest
from ai_agent.tools import default_coding_tools
from ai_agent.tools.background import (
    JobManager,
    PollCommandTool,
    RunCommandBackgroundTool,
    StopCommandTool,
    jobs_root,
)
from ai_agent.tools.base import ToolContext


@pytest.fixture(autouse=True)
def _clean_jobs(tmp_path):
    yield
    # Safety net: stop anything still running (even after a failed assert),
    # then remove the scratch records.
    try:
        manager = JobManager(jobs_root(tmp_path))
        for job in manager.list_jobs():
            if job["status"] == "running":
                try:
                    manager.stop(job["id"])
                except (KeyError, OSError):
                    pass
    finally:
        shutil.rmtree(jobs_root(tmp_path), ignore_errors=True)


def _context(tmp_path):
    return ToolContext(workspace_root=tmp_path)


def _py(code: str) -> str:
    # No quotes around the exe: PowerShell parses a bare quoted string as
    # an expression, not a command. Our venv path carries no spaces.
    assert " " not in sys.executable
    return f'{sys.executable} -c "{code}"'


def _env() -> dict:
    """Viable child env mirroring the host allowlist (PATHEXT is required:
    without it PowerShell silently drops native-command output)."""
    import os

    from ai_agent.tools.base import HOST_ENV_ALLOWLIST

    return {name: value for name, value in os.environ.items() if name.upper() in HOST_ENV_ALLOWLIST}


def test_spawn_critical_vars_stay_allowed() -> None:
    """Windows spawns break without these: PATHEXT (silent output loss),
    SYSTEMDRIVE (unexpanded %SystemDrive% litter in the cwd)."""
    from ai_agent.tools.base import HOST_ENV_ALLOWLIST

    assert {"PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC"} <= HOST_ENV_ALLOWLIST


def _poll_until_done(manager, job_id, *, tries=50):
    for _ in range(tries):
        state = manager.poll(job_id)
        if state["status"] != "running":
            return state
        time.sleep(0.2)
    raise AssertionError(f"job {job_id} still running")


def test_start_fast_command_and_poll_output(tmp_path) -> None:
    manager = JobManager(jobs_root(tmp_path))
    record = manager.start(_py("print('hello')"), tmp_path, _env())
    state = _poll_until_done(manager, record.id)
    assert state["status"] == "done"
    assert state["exit_code"] == 0
    assert state["stdout"].strip() == "hello"
    # Second poll has no repeats (cursor persisted).
    again = manager.poll(record.id)
    assert again["stdout"] == "" and again["stderr"] == ""


def test_poll_streams_output_before_done(tmp_path) -> None:
    manager = JobManager(jobs_root(tmp_path))
    record = manager.start(
        _py("import time; print('a', flush=True); time.sleep(3); print('b', flush=True)"),
        tmp_path,
        _env(),
    )
    seen = ""
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = manager.poll(record.id)
        seen += state["stdout"]
        if state["status"] != "running":
            break
        time.sleep(0.2)
    assert manager.poll(record.id)["status"] == "done"
    assert seen.replace("\n", "") == "ab"


def test_stop_terminates_sleeping_job(tmp_path) -> None:
    manager = JobManager(jobs_root(tmp_path))
    record = manager.start(_py("import time; time.sleep(10)"), tmp_path, _env())
    assert manager.poll(record.id)["status"] == "running"
    stopped = manager.stop(record.id)
    assert stopped["status"] == "stopped"
    assert manager.poll(record.id)["status"] == "stopped"


def test_unknown_job_is_key_error(tmp_path) -> None:
    manager = JobManager(jobs_root(tmp_path))
    with pytest.raises(KeyError):
        manager.poll("nope")
    with pytest.raises(KeyError):
        manager.stop("nope")


def test_dead_pid_without_handle_is_orphaned(tmp_path) -> None:
    import json

    job_dir = jobs_root(tmp_path) / "abc123"
    job_dir.mkdir(parents=True)
    (job_dir / "stdout.log").write_bytes(b"partial")
    (job_dir / "stderr.log").write_bytes(b"")
    (job_dir / "meta.json").write_text(
        json.dumps(
            {
                "id": "abc123",
                "pid": 2**31 - 1,
                "command": "gone",
                "cwd": str(tmp_path),
                "started_at": "2026-01-01T00:00:00+00:00",
                "status": "running",
            }
        ),
        encoding="utf-8",
    )
    manager = JobManager(jobs_root(tmp_path))
    state = manager.poll("abc123")
    assert state["status"] == "orphaned"
    assert state["exit_code"] is None
    assert state["stdout"] == "partial"


def test_output_cap_kills_runaway_job(tmp_path, monkeypatch) -> None:
    import ai_agent.tools.background as background

    monkeypatch.setattr(background, "STREAM_HARD_CAP_BYTES", 1024)
    manager = JobManager(jobs_root(tmp_path))
    record = manager.start(
        _py("import time; [print('x' * 1000, flush=True) or time.sleep(0.01) for _ in range(200)]"),
        tmp_path,
        _env(),
    )
    state = _poll_until_done(manager, record.id)
    assert state["status"] == "killed"
    assert state["stdout_capped"] is True


def test_old_done_jobs_evict_past_cap(tmp_path, monkeypatch) -> None:
    import ai_agent.tools.background as background

    monkeypatch.setattr(background, "MAX_KEPT_JOBS", 2)
    manager = JobManager(jobs_root(tmp_path))
    first = manager.start(_py("print(1)"), tmp_path, _env())
    _poll_until_done(manager, first.id)
    second = manager.start(_py("print(2)"), tmp_path, _env())
    _poll_until_done(manager, second.id)
    third = manager.start(_py("print(3)"), tmp_path, _env())
    _poll_until_done(manager, third.id)
    ids = {job["id"] for job in manager.list_jobs()}
    assert third.id in ids and second.id in ids
    assert first.id not in ids


def test_stop_refuses_bare_pid_without_handle(tmp_path) -> None:
    manager_a = JobManager(jobs_root(tmp_path))
    record = manager_a.start(_py("import time; time.sleep(10)"), tmp_path, _env())
    manager_b = JobManager(jobs_root(tmp_path))
    refused = manager_b.stop(record.id)
    assert refused["status"] == "running"
    assert "refused" in refused["note"]
    assert manager_a.stop(record.id)["status"] == "stopped"


def test_list_jobs_summarizes(tmp_path) -> None:
    manager = JobManager(jobs_root(tmp_path))
    record = manager.start(_py("print('hi')"), tmp_path, _env())
    _poll_until_done(manager, record.id)
    (summary,) = manager.list_jobs()
    assert summary["id"] == record.id and summary["status"] == "done"
    assert summary["exit_code"] == 0


def test_tools_validate_and_register(tmp_path) -> None:
    context = _context(tmp_path)
    assert "run_command_background" in {
        item.name for item in default_coding_tools().list_definitions()
    }
    missing = RunCommandBackgroundTool().execute({}, context)
    assert missing.is_error and "command" in missing.output
    outside = RunCommandBackgroundTool().execute({"command": "echo hi", "cwd": ".."}, context)
    assert outside.is_error and "outside workspace" in outside.output
    started = RunCommandBackgroundTool().execute({"command": _py("print('tooled')")}, context)
    assert not started.is_error
    job_id = started.metadata["job_id"]
    assert PollCommandTool().execute({}, context).is_error
    ghost = PollCommandTool().execute({"job_id": "ghost"}, context)
    assert ghost.is_error and "unknown" in ghost.output
    assert StopCommandTool().execute({"job_id": "ghost"}, context).is_error
    seen = ""
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        tick = PollCommandTool().execute({"job_id": job_id}, context)
        seen += tick.output
        if tick.metadata["status"] != "running":
            break
        time.sleep(0.2)
    final = PollCommandTool().execute({"job_id": job_id}, context)
    assert final.metadata["status"] == "done"
    assert "tooled" in seen
    stopped = StopCommandTool().execute({"job_id": job_id}, context)
    assert not stopped.is_error and stopped.metadata["status"] == "done"
