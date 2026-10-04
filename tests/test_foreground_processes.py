"""Local process inspection and bounded output require no AI model calls."""

import sys
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
