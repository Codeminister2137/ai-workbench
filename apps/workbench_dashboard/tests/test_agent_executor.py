"""AgentLoop executor: run records in, drain receipts with staged files out."""

from __future__ import annotations

import pytest
from agent_executor import build_executor, build_executor_registry
from ai_agent.contracts import ToolResult
from ai_agent.loop import AgentIterationLimitExceeded, AgentResult
from ai_agent.permissions import ApprovalPolicyPreset, PermissionManager, PermissionPolicy
from ai_agent.staged_edits import ProjectRoots
from ai_provider import (
    AIMessage,
    AIResponse,
    BackendInfo,
    BackendLocation,
    MessageRole,
    ProviderError,
)
from ai_provider.config import BackendConfig
from dashboard_config import DashboardConfig


def _response(text: str) -> AIResponse:
    return AIResponse(
        message=AIMessage(role=MessageRole.ASSISTANT, content=text),
        backend=BackendInfo(provider="ollama", model="fake", location=BackendLocation.LOCAL),
    )


class FakeLoop:
    instances: list[FakeLoop] = []

    def __init__(self, client, registry, context, **kwargs):
        self.kwargs = kwargs
        self.context = context
        self.registry = registry
        self.prompts: list[str] = []
        self.result = AgentResult(response=_response("done"))
        self.error: Exception | None = None
        FakeLoop.instances.append(self)

    def run(self, prompt: str, **kwargs):
        self.prompts.append(prompt)
        self.run_kwargs = kwargs
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def harness(tmp_path):
    FakeLoop.instances = []
    project = tmp_path / "proj"
    project.mkdir()
    (project / "app.py").write_text("old\n", encoding="utf-8")

    seen: list = []

    def factory(backend: BackendConfig):
        seen.append(backend)
        return object()

    config = DashboardConfig(provider="ollama", model="fake")
    roots = ProjectRoots((str(project),))
    execute = build_executor(config, roots, tmp_path, client_factory=factory, loop_factory=FakeLoop)
    return execute, seen, project


def test_registry_has_full_staged_toolset() -> None:
    names = {definition.name for definition in build_executor_registry().list_definitions()}
    assert names == {
        "read_file",
        "list_dir",
        "find_files",
        "grep_search",
        "git_status",
        "git_diff",
        "run_command",
        "python_runtime",
        "python_navigate",
        "rename_preview",
        "stage_file",
    }


def test_completed_receipt_maps_result(tmp_path) -> None:
    FakeLoop.instances = []
    loop_result = AgentResult(
        response=_response("all good"),
        tool_results=(
            ToolResult(name="read_file", output="ok"),
            ToolResult(
                name="stage_file",
                output="staged",
                metadata={"staged": {"relpath": "a.py", "content": "x"}},
            ),
        ),
        iterations=3,
    )

    def factory_loop(client, registry, context, **kwargs):
        loop = FakeLoop(client, registry, context, **kwargs)
        loop.result = loop_result
        return loop

    config = DashboardConfig(provider="ollama", model="fake")
    execute = build_executor(
        config,
        ProjectRoots(()),
        tmp_path,
        client_factory=lambda backend: object(),
        loop_factory=factory_loop,
    )
    receipt = execute({"id": "r1", "title": "Do it", "body": "do the thing"})
    assert receipt["status"] == "completed"
    assert receipt["summary"] == "all good"
    assert receipt["iterations"] == 3
    assert receipt["tool_calls"] == ["read_file", "stage_file"]
    assert receipt["staged"] == [{"relpath": "a.py", "content": "x"}]
    assert "do the thing" in FakeLoop.instances[-1].prompts[0]


def test_failed_on_provider_error(tmp_path) -> None:
    FakeLoop.instances = []

    def factory_loop(client, registry, context, **kwargs):
        loop = FakeLoop(client, registry, context, **kwargs)
        loop.error = ProviderError("boom")
        return loop

    config = DashboardConfig(provider="ollama", model="fake")
    execute = build_executor(
        config,
        ProjectRoots(()),
        tmp_path,
        client_factory=lambda backend: object(),
        loop_factory=factory_loop,
    )
    receipt = execute({"id": "r1", "title": "t", "body": "b"})
    assert receipt["status"] == "failed"
    assert "boom" in receipt["error"]


def test_failed_on_iteration_limit(tmp_path) -> None:
    FakeLoop.instances = []

    def factory_loop(client, registry, context, **kwargs):
        loop = FakeLoop(client, registry, context, **kwargs)
        loop.error = AgentIterationLimitExceeded("too long")
        return loop

    config = DashboardConfig(provider="ollama", model="fake")
    execute = build_executor(
        config,
        ProjectRoots(()),
        tmp_path,
        client_factory=lambda backend: object(),
        loop_factory=factory_loop,
    )
    receipt = execute({"id": "r1", "title": "t", "body": "b"})
    assert receipt["status"] == "failed"
    assert "Iteration limit" in receipt["error"]


def test_unknown_provider_fails_closed(tmp_path) -> None:
    seen: list = []
    config = DashboardConfig(provider="nope", model="fake")
    execute = build_executor(
        config,
        ProjectRoots(()),
        tmp_path,
        client_factory=lambda backend: seen.append(backend),
        loop_factory=FakeLoop,
    )
    receipt = execute({"id": "r1", "title": "t", "body": "b"})
    assert receipt["status"] == "failed"
    assert "Unknown provider" in receipt["error"]
    assert seen == []


def test_unknown_project_fails_closed(harness) -> None:
    execute, _factory, _project = harness
    receipt = execute({"id": "r1", "title": "t", "body": "b", "project_id": "ghost"})
    assert receipt["status"] == "failed"
    assert "Project scope refused" in receipt["error"]


def test_scoped_run_uses_project_workspace(harness) -> None:
    execute, _factory, project = harness
    receipt = execute({"id": "r1", "title": "t", "body": "b", "project_id": str(project)})
    assert receipt["status"] == "completed"
    assert FakeLoop.instances[-1].context.workspace_root == project


def test_fanout_flows_to_loop(harness) -> None:
    execute, _factory, _project = harness
    execute({"id": "r1", "title": "t", "body": "b", "fanout_policy": "denied"})
    assert FakeLoop.instances[-1].kwargs["fanout_policy"] == "denied"
    execute({"id": "r2", "title": "t", "body": "b"})
    assert FakeLoop.instances[-1].kwargs["fanout_policy"] == "restricted"


def test_permissions_are_trusted_local(harness) -> None:
    execute, _factory, _project = harness
    execute({"id": "r1", "title": "t", "body": "b"})
    permissions = FakeLoop.instances[-1].kwargs["permissions"]
    assert isinstance(permissions, PermissionManager)
    assert permissions.policy == PermissionPolicy.from_approval_preset(
        ApprovalPolicyPreset.TRUSTED_LOCAL
    )
