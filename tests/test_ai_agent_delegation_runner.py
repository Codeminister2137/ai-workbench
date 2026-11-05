"""Child runner: narrowed one-level subagents with staged carry-back."""

from ai_agent.contracts import ToolResult
from ai_agent.delegation_runner import build_child_runner
from ai_agent.delegation_scope import DelegationBudget, DelegationScope
from ai_agent.fanout import FanoutPolicy
from ai_agent.loop import AgentIterationLimitExceeded, AgentResult
from ai_agent.permissions import PermissionManager
from ai_agent.tools.base import ToolContext, ToolRegistry
from ai_agent.tools.filesystem import ReadFileTool
from ai_agent.tools.staged import StageFileTool
from ai_provider import (
    AIMessage,
    AIResponse,
    BackendInfo,
    BackendLocation,
    MessageRole,
    ProviderError,
)


def _response(text: str) -> AIResponse:
    return AIResponse(
        message=AIMessage(role=MessageRole.ASSISTANT, content=text),
        backend=BackendInfo(provider="ollama", model="fake", location=BackendLocation.LOCAL),
    )


class FakeLoop:
    def __init__(self, client, registry, context, **kwargs):
        self.kwargs = kwargs
        self.registry = registry
        self.context = context
        self.result = AgentResult(response=_response("child done"))
        self.error: Exception | None = None
        self.prompts: list[str] = []

    def run(self, prompt: str, **kwargs):
        self.prompts.append(prompt)
        self.run_kwargs = kwargs
        if self.error is not None:
            raise self.error
        return self.result


def _scope(tmp_path, **overrides):
    from typing import Any

    registry = ToolRegistry(tools=(ReadFileTool(), StageFileTool()))
    base: dict[str, Any] = dict(
        registry=registry,
        permissions=PermissionManager(),
        workspace=tmp_path,
        budget=DelegationBudget(5),
        approved_client=object(),
    )
    base.update(overrides)
    return DelegationScope(**base)


def test_child_runs_with_narrowed_registry(tmp_path) -> None:
    seen: list = []

    def factory(client, registry, context, **kwargs):
        loop = FakeLoop(client, registry, context, **kwargs)
        seen.append(loop)
        return loop

    runner = build_child_runner(loop_factory=factory)
    context = ToolContext(workspace_root=tmp_path, delegation=_scope(tmp_path))
    result = runner("inspect app.py", context)
    assert result.is_error is False
    assert result.output == "child done"
    assert seen[0].prompts == ["inspect app.py"]
    names = {item.name for item in seen[0].registry.list_definitions()}
    assert names == {"read_file", "stage_file"}
    assert "delegate_task" not in names


def test_child_staged_carries_back(tmp_path) -> None:
    record = {"relpath": "a.py", "content": "x"}

    def factory(client, registry, context, **kwargs):
        loop = FakeLoop(client, registry, context, **kwargs)
        loop.result = AgentResult(
            response=_response("staged it"),
            tool_results=(ToolResult(name="stage_file", output="ok", metadata={"staged": record}),),
        )
        return loop

    runner = build_child_runner(loop_factory=factory)
    context = ToolContext(workspace_root=tmp_path, delegation=_scope(tmp_path))
    result = runner("write a.py", context)
    assert result.metadata["child_staged"] == [record]


def test_no_scope_refuses(tmp_path) -> None:
    runner = build_child_runner(loop_factory=FakeLoop)
    result = runner("task", ToolContext(workspace_root=tmp_path))
    assert result.is_error is True
    assert "no host delegation scope" in result.output


def test_no_client_refuses(tmp_path) -> None:
    runner = build_child_runner(loop_factory=FakeLoop)
    context = ToolContext(
        workspace_root=tmp_path, delegation=_scope(tmp_path, approved_client=None)
    )
    result = runner("task", context)
    assert result.is_error is True
    assert "no approved client" in result.output


def test_child_errors_return_results(tmp_path) -> None:
    def factory(client, registry, context, **kwargs):
        loop = FakeLoop(client, registry, context, **kwargs)
        loop.error = ProviderError("relay down")
        return loop

    runner = build_child_runner(loop_factory=factory)
    context = ToolContext(workspace_root=tmp_path, delegation=_scope(tmp_path))
    result = runner("task", context)
    assert result.is_error is True
    assert "relay down" in result.output

    def limited(client, registry, context, **kwargs):
        loop = FakeLoop(client, registry, context, **kwargs)
        loop.error = AgentIterationLimitExceeded("too long")
        return loop

    runner = build_child_runner(loop_factory=limited)
    result = runner("task", context)
    assert result.is_error is True
    assert "iteration limit" in result.output


def test_fanout_flows_to_child(tmp_path) -> None:
    seen: list = []

    def factory(client, registry, context, **kwargs):
        loop = FakeLoop(client, registry, context, **kwargs)
        seen.append(loop)
        return loop

    runner = build_child_runner(loop_factory=factory)
    scope = _scope(tmp_path, fanout=FanoutPolicy.ALLOWED)
    context = ToolContext(workspace_root=tmp_path, delegation=scope)
    runner("task", context)
    assert seen[0].kwargs["fanout_policy"] == FanoutPolicy.ALLOWED
