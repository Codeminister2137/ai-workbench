"""Native delegation: guidance, sequential fan-out, bounded summaries."""

from __future__ import annotations

from ai_agent import AgentLoop, PermissionManager, PermissionPolicy
from ai_agent.contracts import ToolResult
from ai_agent.repo_coding_assistant import (
    _delegation_guidance,
    _format_delegated_task_output,
)
from ai_agent.tools import ToolContext, ToolRegistry
from ai_agent.tools.delegation import DelegateTaskTool, coding_tools_with_delegation
from ai_agent.tools.filesystem import ReadFileTool
from ai_provider import (
    AIMessage,
    AIResponse,
    AIToolCall,
    BackendInfo,
    BackendLocation,
    FinishReason,
    MessageRole,
    PrivacyClass,
    UsageMetadata,
)


def test_guidance_present_only_when_tool_registered() -> None:
    def runner(task, context):
        return ToolResult("delegate_task", "child report")

    assert _delegation_guidance(coding_tools_with_delegation(runner)) != ""
    guidance = _delegation_guidance(coding_tools_with_delegation(runner))
    assert "isolated context" in guidance
    assert "returns only a summary" in guidance
    assert _delegation_guidance(ToolRegistry((ReadFileTool(),))) == ""


class ScriptedClient:
    backend = BackendInfo("ollama", "parent-model", BackendLocation.LOCAL)

    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        calls = next(self.replies)
        return AIResponse(
            AIMessage(MessageRole.ASSISTANT, "Done" if not calls else "", tool_calls=tuple(calls)),
            self.backend,
            tool_calls=tuple(calls),
        )

    def stream(self, request):
        raise NotImplementedError


def test_two_delegations_run_sequentially_and_both_summaries_return(tmp_path) -> None:
    order: list[str] = []

    def runner(task: str, context: ToolContext) -> ToolResult:
        order.append(task)
        return ToolResult("delegate_task", f"summary of {task}")

    client = ScriptedClient(
        [
            [
                AIToolCall("d1", "delegate_task", {"task": "first file"}),
                AIToolCall("d2", "delegate_task", {"task": "second file"}),
            ],
            [],
        ]
    )
    result = AgentLoop(
        client,
        ToolRegistry((DelegateTaskTool(runner),)),
        ToolContext(tmp_path),
        permissions=PermissionManager(PermissionPolicy.permissive()),
        max_iterations=3,
    ).run("Do both", privacy_class=PrivacyClass.LOCAL_ONLY)
    assert order == ["first file", "second file"]
    assert [item.output for item in result.tool_results] == [
        "summary of first file",
        "summary of second file",
    ]
    assert result.response.message.content == "Done"


def test_delegated_output_bounds_tool_previews() -> None:
    response = AIResponse(
        message=AIMessage(MessageRole.ASSISTANT, "child final"),
        backend=BackendInfo("ollama", "child", BackendLocation.LOCAL),
        finish_reason=FinishReason.STOP,
        usage=UsageMetadata(),
    )
    results = tuple(ToolResult(f"tool_{index}", "x" * 500) for index in range(7))
    output = _format_delegated_task_output(
        task="subtask",
        response=response,
        iterations=4,
        tool_results=results,
    )
    assert "Delegated task status: completed" in output
    assert "7 total" in output
    assert "2 additional tool result(s) omitted" in output
    assert "child final" in output
    assert "x" * 500 not in output


def test_permission_profile_default_means_inherit(tmp_path) -> None:
    seen: list[str] = []

    def runner(task: str, context: ToolContext) -> ToolResult:
        seen.append(task)
        return ToolResult("delegate_task", "child report")

    result = DelegateTaskTool(runner).execute(
        {"task": "do it", "permission_profile": "default"},
        ToolContext(tmp_path),
    )
    assert not result.is_error
    assert seen == ["do it"]


def test_narrow_accepts_default_as_inherit(tmp_path) -> None:
    import time

    from ai_agent import PermissionManager, PermissionPolicy
    from ai_agent.delegation_scope import DelegationBudget, DelegationScope

    scope = DelegationScope(
        ToolRegistry((ReadFileTool(),)),
        PermissionManager(PermissionPolicy.permissive()),
        tmp_path,
        DelegationBudget(8, time.perf_counter() + 30),
    )
    child = scope.narrow(profile="default")
    assert child.profile == "inherit"
