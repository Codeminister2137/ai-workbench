"""Actual scoped child effects and shared parent/descendant limits, without inference."""

import os
import subprocess
import sys
import time

import pytest
from ai_agent import AgentLoop, PermissionManager, PermissionPolicy
from ai_agent.contracts import ToolCall, ToolCategory, ToolDefinition, ToolParameter, ToolResult
from ai_agent.delegation_scope import DelegationBudget, DelegationScope
from ai_agent.tools import EditFileTool, ReadFileTool, ToolContext, ToolRegistry
from ai_agent.tools.base import BaseTool
from ai_agent.tools.delegation import DelegateTaskTool
from ai_provider import AIMessage, AIResponse, AIToolCall, BackendInfo, BackendLocation, MessageRole


class Client:
    backend = BackendInfo("ollama", "child-model", BackendLocation.LOCAL, "http://localhost:11434")

    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = 0

    def complete(self, request):
        self.calls += 1
        calls = next(self.replies)
        return AIResponse(
            AIMessage(MessageRole.ASSISTANT, "Done" if not calls else "", tool_calls=tuple(calls)),
            self.backend,
            tool_calls=tuple(calls),
        )

    def stream(self, request):
        raise NotImplementedError


class Validate(BaseTool):
    @property
    def definition(self):
        return ToolDefinition(
            "run_command",
            "Run the protected check",
            ToolCategory.SHELL,
            parameters=(ToolParameter("command", "string", "Exact check"),),
        )

    def execute(self, arguments, context):
        assert arguments["command"] == "check"
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                "import runpy; assert runpy.run_path('calc.py')['answer']() == 42; "
                "print('one actual check passed')",
            ],
            cwd=context.workspace_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return ToolResult(
            "run_command", result.stdout + result.stderr, is_error=result.returncode != 0
        )


def initial_scope(tmp_path, **kwargs):
    (tmp_path / "calc.py").write_text("def answer():\n    return 0\n")
    registry = ToolRegistry((EditFileTool(), ReadFileTool(), Validate()))
    return DelegationScope(
        registry,
        PermissionManager(PermissionPolicy.permissive()),
        tmp_path,
        DelegationBudget(8, time.perf_counter() + 30),
        **kwargs,
    )


def edit(registry, root, path="calc.py"):
    return registry.execute(
        ToolCall("edit_file", {"path": path, "new_text": "def answer():\n    return 42\n"}),
        ToolContext(root),
    )


def test_child_really_edits_and_runs_scoped_command(tmp_path):
    parent = initial_scope(tmp_path)
    child = parent.narrow(
        tools=("edit_file", "run_command"), paths=("calc.py",), commands=("check",)
    )
    registry = child.child_registry()
    assert not edit(registry, tmp_path).is_error
    checked = registry.execute(ToolCall("run_command", {"command": "check"}), ToolContext(tmp_path))
    assert not checked.is_error and "one actual check passed" in checked.output
    assert registry.get("read_file") is None


def test_child_cannot_escape_path_command_or_workspace(tmp_path):
    child = initial_scope(tmp_path).narrow(paths=("calc.py",), commands=("check",))
    registry = child.child_registry()
    (tmp_path / "other.py").write_text("unchanged")
    assert edit(registry, tmp_path, "other.py").is_error
    assert edit(registry, tmp_path.parent).is_error
    assert registry.execute(
        ToolCall("run_command", {"command": "different"}), ToolContext(tmp_path)
    ).is_error
    assert (tmp_path / "other.py").read_text() == "unchanged"
    with pytest.raises(ValueError, match="workspace"):
        child.narrow(paths=("../foreign",))


def test_explicit_read_only_cannot_be_escalated_by_grandchild(tmp_path):
    scope = initial_scope(tmp_path)
    child = scope.narrow(profile="read_only")
    grandchild = child.narrow(profile="trusted_local")
    assert edit(child.child_registry(), tmp_path).is_error
    assert edit(grandchild.child_registry(), tmp_path).is_error
    assert "return 0" in (tmp_path / "calc.py").read_text()


def test_parent_policy_and_revocation_remain_live(tmp_path):
    active = [True]
    parent = initial_scope(tmp_path, is_active=lambda: active[0])
    registry = parent.narrow().child_registry()
    parent.permissions.policy = PermissionPolicy.read_only()
    assert edit(registry, tmp_path).is_error
    parent.permissions.policy = PermissionPolicy.permissive()
    active[0] = False
    assert edit(registry, tmp_path).is_error
    assert "return 0" in (tmp_path / "calc.py").read_text()


def test_nested_depth_and_parent_report_reserve(tmp_path):
    scope = initial_scope(tmp_path)
    grandchild = scope.narrow().narrow()
    assert grandchild.budget is scope.budget
    with pytest.raises(ValueError, match="depth"):
        grandchild.narrow()
    budget = DelegationBudget(2)
    with budget.child():
        budget.consume()
        with pytest.raises(Exception, match="exhausted"):
            budget.consume()
    budget.consume()  # The parent's reserved final report.
    assert budget.replies_remaining == 0


@pytest.mark.parametrize("limit,expected_child_calls,failed", [(5, 3, False), (4, 2, True)])
def test_original_reply_budget_shared_with_actual_child_loop(
    tmp_path, limit, expected_child_calls, failed
):
    (tmp_path / "calc.py").write_text("def answer():\n    return 0\n")
    child_client = Client(
        [
            [
                AIToolCall(
                    "edit",
                    "edit_file",
                    {"path": "calc.py", "new_text": "def answer():\n    return 42\n"},
                )
            ],
            [AIToolCall("test", "run_command", {"command": "check"})],
            [],
        ]
    )
    inherited = []

    def run(task, context):
        inherited.append(context.delegation)
        child_result = AgentLoop(
            child_client,
            context.delegation.child_registry(),
            context,
            permissions=PermissionManager(PermissionPolicy.permissive()),
            max_iterations=10,
        ).run(task)
        return ToolResult("delegate_task", child_result.response.message.content)

    registry = ToolRegistry((EditFileTool(), Validate(), DelegateTaskTool(run)))
    parent = Client(
        [[AIToolCall("child", "delegate_task", {"task": "Implement and test answer"})], []]
    )
    result = AgentLoop(
        parent,
        registry,
        ToolContext(tmp_path),
        permissions=PermissionManager(PermissionPolicy.permissive()),
        max_iterations=limit,
    ).run("Original task", system_prompt="Complete original instructions")
    assert parent.calls + child_client.calls == limit
    assert child_client.calls == expected_child_calls
    assert result.tool_results[0].is_error is failed
    assert inherited[0].instructions == "Complete original instructions"
    assert inherited[0].objective == "Original task"
    assert "return 42" in (tmp_path / "calc.py").read_text()


@pytest.mark.parametrize("value", [0, -1, True])
def test_invalid_original_reply_grants_refuse(value):
    with pytest.raises(ValueError):
        DelegationBudget(value)


def test_deadline_can_only_shorten_original_grant():
    budget = DelegationBudget(8, deadline=100)
    budget.tighten_deadline(90)
    budget.tighten_deadline(110)
    assert budget.deadline == 90


@pytest.mark.parametrize("process_tool", [False, True])
def test_delegated_os_process_does_not_inherit_host_credentials(
    tmp_path, monkeypatch, process_tool
):
    from ai_agent.processes import ProcessSupervisor, ProcessTool
    from ai_agent.tools.shell import RunCommandTool

    monkeypatch.setenv("SYNTHETIC_PRIVATE_TOKEN", "must-not-transfer")
    monkeypatch.setenv("META_API_KEY", "synthetic-not-real")
    (tmp_path / "check_env.py").write_text(
        "import os\nassert 'SYNTHETIC_PRIVATE_TOKEN' not in os.environ\n"
        "assert 'META_API_KEY' not in os.environ\nprint('credentials absent', flush=True)\n"
    )
    supervisor = ProcessSupervisor(tmp_path)
    try:
        tool = ProcessTool(supervisor, "start") if process_tool else RunCommandTool()
        parent = DelegationScope(
            ToolRegistry((tool,)),
            PermissionManager(PermissionPolicy.permissive()),
            tmp_path,
            DelegationBudget(4),
        )
        registry = parent.narrow().child_registry()
        context = ToolContext(tmp_path, env={"SYNTHETIC_PRIVATE_TOKEN": "must-not-copy-context"})
        if process_tool:
            result = registry.execute(
                ToolCall("process_start", {"argv": [sys.executable, "check_env.py"]}), context
            )
            assert not result.is_error
            handle = result.metadata["process_handle"]
            until = time.monotonic() + 5
            state = supervisor.status(handle)
            while state["status"] == "running" and time.monotonic() < until:
                time.sleep(0.02)
                state = supervisor.status(handle)
            assert state["status"] != "running"
            assert "credentials absent" in state["stdout"]
        else:
            command = (
                f"& '{sys.executable}' check_env.py"
                if os.name == "nt"
                else f"'{sys.executable}' check_env.py"
            )
            result = registry.execute(ToolCall("run_command", {"command": command}), context)
            assert not result.is_error and "credentials absent" in result.output
    finally:
        supervisor.close()
