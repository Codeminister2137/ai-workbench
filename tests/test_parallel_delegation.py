"""Parallel sibling delegation: concurrency, order, fallbacks."""

from __future__ import annotations

import threading
import time

import pytest
from ai_agent import AgentLoop, PermissionManager, PermissionPolicy, ToolContext
from ai_agent.contracts import ToolResult
from ai_agent.tools import ToolRegistry
from ai_agent.tools.delegation import DelegateTaskTool
from ai_agent.tools.filesystem import CreateFileTool
from ai_provider import (
    AIMessage,
    AIResponse,
    AIToolCall,
    BackendInfo,
    BackendLocation,
    MessageRole,
    PrivacyClass,
    ProviderError,
)


class ScriptedClient:
    backend = BackendInfo("ollama", "parent", BackendLocation.LOCAL)

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        calls, text = self.replies.pop(0) if self.replies else ([], "Done")
        return AIResponse(
            AIMessage(MessageRole.ASSISTANT, text, tool_calls=tuple(calls)),
            self.backend,
            tool_calls=tuple(calls),
        )

    def stream(self, request):
        raise NotImplementedError


def _call(call_id, task):
    return AIToolCall(call_id, "delegate_task", {"task": task})


def _run(runner, replies, tmp_path, **kwargs):
    notes: list[str] = []
    client = ScriptedClient(replies)
    loop = AgentLoop(
        client,
        ToolRegistry((DelegateTaskTool(runner),)),
        ToolContext(tmp_path),
        permissions=PermissionManager(PermissionPolicy.permissive()),
        max_iterations=4,
        diagnostic=notes.append,
        **kwargs,
    )
    return loop.run("Go", privacy_class=PrivacyClass.LOCAL_ONLY), notes


def test_siblings_run_concurrently(tmp_path) -> None:
    barrier = threading.Barrier(2)

    def runner(task, context):
        barrier.wait(timeout=10)
        return ToolResult("delegate_task", f"summary of {task}")

    result, notes = _run(
        runner,
        [([_call("d1", "one"), _call("d2", "two")], ""), ([], "Done")],
        tmp_path,
    )
    assert [item.output for item in result.tool_results] == [
        "summary of one",
        "summary of two",
    ]
    assert any("delegation_fanout: n=2" in line for line in notes)


def test_results_stay_in_position_order(tmp_path) -> None:
    def runner(task, context):
        if task == "slow":
            time.sleep(0.4)
        return ToolResult("delegate_task", f"summary of {task}")

    result, _ = _run(
        runner,
        [([_call("d1", "slow"), _call("d2", "fast")], ""), ([], "Done")],
        tmp_path,
    )
    assert [item.output for item in result.tool_results] == [
        "summary of slow",
        "summary of fast",
    ]


def test_interactive_approval_forces_sequential(tmp_path) -> None:
    order: list[str] = []
    entered: list[str] = []

    def runner(task, context):
        entered.append(task)
        time.sleep(0.2)
        order.append(task)
        return ToolResult("delegate_task", f"summary of {task}")

    notes: list[str] = []
    client = ScriptedClient([([_call("d1", "one"), _call("d2", "two")], ""), ([], "Done")])
    AgentLoop(
        client,
        ToolRegistry((DelegateTaskTool(runner),)),
        ToolContext(tmp_path),
        permissions=PermissionManager(
            PermissionPolicy.interactive(), approval_callback=lambda call, cat: True
        ),
        max_iterations=4,
        diagnostic=notes.append,
    ).run("Go", privacy_class=PrivacyClass.LOCAL_ONLY)
    assert order == ["one", "two"]
    assert not any("delegation_fanout" in line for line in notes)


def test_max_workers_one_forces_sequential(tmp_path) -> None:
    def runner(task, context):
        return ToolResult("delegate_task", f"summary of {task}")

    result, notes = _run(
        runner,
        [([_call("d1", "one"), _call("d2", "two")], ""), ([], "Done")],
        tmp_path,
        delegation_max_workers=1,
    )
    assert len(result.tool_results) == 2
    assert not any("delegation_fanout" in line for line in notes)


def test_single_delegate_stays_sequential(tmp_path) -> None:
    def runner(task, context):
        return ToolResult("delegate_task", "summary")

    _result, notes = _run(runner, [([_call("d1", "one")], ""), ([], "Done")], tmp_path)
    assert not any("delegation_fanout" in line for line in notes)


def test_child_protocol_error_aborts_loudly(tmp_path) -> None:
    from ai_agent.tools.base import BaseTool
    from ai_provider import ProviderErrorCategory

    real_tool = DelegateTaskTool(
        lambda task, context: ToolResult("delegate_task", "summary of good")
    )

    class ExplodingTool(BaseTool):
        @property
        def definition(self):
            return real_tool.definition

        def execute(self, arguments, context):
            raise AssertionError("unreachable")

        def run(self, call, context):
            raise ProviderError("child blew up", category=ProviderErrorCategory.TIMEOUT)

    client = ScriptedClient(
        [
            (
                [
                    AIToolCall("d1", "delegate_task", {"task": "good"}),
                    AIToolCall("d2", "delegate_task", {"task": "bad"}),
                ],
                "",
            ),
            ([], "Done"),
        ]
    )

    loop = AgentLoop(
        client,
        ToolRegistry((ExplodingTool(),)),
        ToolContext(tmp_path),
        permissions=PermissionManager(PermissionPolicy.permissive()),
        max_iterations=4,
    )
    with pytest.raises(ProviderError, match="child blew up"):
        loop.run("Go", privacy_class=PrivacyClass.LOCAL_ONLY)


def test_mixed_batch_keeps_positional_transcript(tmp_path) -> None:
    def runner(task, context):
        time.sleep(0.2)
        return ToolResult("delegate_task", f"summary of {task}")

    client = ScriptedClient(
        [
            (
                [
                    AIToolCall("c1", "create_file", {"path": "a.txt", "content": "a"}),
                    _call("d1", "one"),
                    _call("d2", "two"),
                ],
                "",
            ),
            ([], "Done"),
        ]
    )
    result = AgentLoop(
        client,
        ToolRegistry((DelegateTaskTool(runner), CreateFileTool())),
        ToolContext(tmp_path),
        permissions=PermissionManager(PermissionPolicy.permissive()),
        max_iterations=4,
    ).run("Go", privacy_class=PrivacyClass.LOCAL_ONLY)
    assert [item.name for item in result.tool_results] == [
        "create_file",
        "delegate_task",
        "delegate_task",
    ]
    assert (tmp_path / "a.txt").read_text() == "a"
