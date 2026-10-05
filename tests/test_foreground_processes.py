"""Local process inspection and bounded output require no AI model calls."""

import sys
import threading
import time

import pytest
from ai_agent.contracts import PermissionAction, ToolCall, ToolCategory
from ai_agent.permissions import PermissionManager, PermissionPolicy
from ai_agent.processes import OUTPUT_LIMIT, ProcessSupervisor, ProcessTool
from ai_agent.tools import ToolContext


def finish(supervisor, handle):
    until = time.monotonic() + 5
    result = supervisor.status(handle)
    while result["status"] == "running" and time.monotonic() < until:
        time.sleep(0.02)
        result = supervisor.status(handle)
    return result


def test_native_process_completion_output_and_failure_without_model(tmp_path):
    supervisor = ProcessSupervisor(tmp_path)
    try:
        handle = supervisor.start([sys.executable, "-c", "print('completed')"])
        result = finish(supervisor, handle)
        assert result["returncode"] == 0 and result["stdout"].strip() == "completed"
        failure = supervisor.start([sys.executable, "-c", "import sys; sys.exit(3)"])
        assert finish(supervisor, failure)["status"] == "failed"
    finally:
        supervisor.close()


def test_running_output_is_visible_before_exit_and_cleanup_stops_owned_child(tmp_path):
    supervisor = ProcessSupervisor(tmp_path)
    handle = supervisor.start(
        [sys.executable, "-u", "-c", "import time; print('started', flush=True); time.sleep(30)"]
    )
    until = time.monotonic() + 5
    while "started" not in supervisor.status(handle)["stdout"] and time.monotonic() < until:
        time.sleep(0.02)
    assert supervisor.status(handle)["status"] == "running"
    assert "started" in supervisor.status(handle)["stdout"]
    supervisor.close()
    assert supervisor.status(handle)["returncode"] is not None


def test_process_output_is_bounded_and_truncation_is_explicit(tmp_path):
    supervisor = ProcessSupervisor(tmp_path)
    try:
        handle = supervisor.start([sys.executable, "-c", f"print('x' * {OUTPUT_LIMIT * 3})"])
        result = finish(supervisor, handle)
        assert len(result["stdout"]) == OUTPUT_LIMIT
        assert result["truncated"] == ["stdout"]
    finally:
        supervisor.close()


def test_process_ownership_workspace_and_approval_boundaries(tmp_path):
    supervisor = ProcessSupervisor(tmp_path)
    with pytest.raises(ValueError, match="Unknown process"):
        supervisor.stop(str(__import__("os").getpid()))
    with pytest.raises(ValueError, match="inside the workspace"):
        supervisor.start([sys.executable], "..")
    policy = PermissionPolicy.read_only()
    assert policy.action_for_category(ToolCategory.SHELL) is PermissionAction.DENY
    manager = PermissionManager(policy)
    for operation in ("start", "stop"):
        tool = ProcessTool(supervisor, operation)
        assert not manager.check_and_authorize(tool, ToolCall(tool.definition.name, {}))
    status = ProcessTool(supervisor, "status")
    assert manager.check_and_authorize(status, ToolCall(status.definition.name, {}))
    assert status.run(
        ToolCall(status.definition.name, {"process_handle": "missing"}), ToolContext(tmp_path)
    ).is_error


def test_closed_supervisor_refuses_new_children_but_retains_observations(tmp_path):
    supervisor = ProcessSupervisor(tmp_path)
    handle = supervisor.start([sys.executable, "-c", "import time; time.sleep(30)"])
    supervisor.close()
    supervisor.close()
    assert supervisor.status(handle)["returncode"] is not None
    with pytest.raises(ValueError, match="supervisor has closed"):
        supervisor.start([sys.executable, "-c", "raise SystemExit('must not start')"])
    assert len(supervisor.processes) == 1


def test_cleanup_continues_after_one_child_termination_fails(tmp_path, monkeypatch):
    supervisor = ProcessSupervisor(tmp_path)
    handles = [
        supervisor.start([sys.executable, "-c", "import time; time.sleep(30)"]) for _ in range(2)
    ]
    original_stop = supervisor.stop
    observed = []

    def stop(handle):
        observed.append(handle)
        result = original_stop(handle)
        if handle == handles[0]:
            raise OSError("fixture termination reporting error")
        return result

    monkeypatch.setattr(supervisor, "stop", stop)
    try:
        with pytest.raises(OSError, match="reporting error"):
            supervisor.close()
        assert observed == handles
        assert all(supervisor.status(handle)["returncode"] is not None for handle in handles)
    finally:
        monkeypatch.setattr(supervisor, "stop", original_stop)
        supervisor.close()


def test_shutdown_waits_for_inflight_launch_and_then_stops_that_child(tmp_path, monkeypatch):
    from ai_agent import processes

    supervisor = ProcessSupervisor(tmp_path)
    original_popen = processes.subprocess.Popen
    launching, release, closing, closed = (threading.Event() for _ in range(4))
    failures = []

    def launch(*args, **kwargs):
        launching.set()
        if not release.wait(5):
            raise RuntimeError("fixture launch was not released")
        return original_popen(*args, **kwargs)

    def start():
        try:
            supervisor.start([sys.executable, "-c", "import time; time.sleep(30)"])
        except Exception as error:
            failures.append(error)

    def close():
        closing.set()
        try:
            supervisor.close()
        except Exception as error:
            failures.append(error)
        finally:
            closed.set()

    monkeypatch.setattr(processes.subprocess, "Popen", launch)
    starter, closer = threading.Thread(target=start), threading.Thread(target=close)
    starter.start()
    try:
        assert launching.wait(5)
        closer.start()
        assert closing.wait(5)
        assert not closed.wait(0.02)
    finally:
        release.set()
        starter.join(5)
        if closer.ident is not None:
            closer.join(5)
        supervisor.close()
    assert not starter.is_alive() and not closer.is_alive()
    assert not failures
    assert len(supervisor.processes) == 1
    assert all(item.process.poll() is not None for item in supervisor.processes.values())
