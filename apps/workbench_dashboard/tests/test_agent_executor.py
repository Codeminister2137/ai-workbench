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
        "request_owner_task",
        "delegate_task",
        "search_web",
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


def test_owner_tasks_filed_to_inbox(tmp_path) -> None:
    FakeLoop.instances = []
    filed: list[dict] = []

    def inbox_create(**kwargs):
        record = {"id": f"task-{len(filed) + 1}", **kwargs}
        filed.append(record)
        return record

    def factory_loop(client, registry, context, **kwargs):
        loop = FakeLoop(client, registry, context, **kwargs)
        loop.result = AgentResult(
            response=_response("needs a human"),
            tool_results=(
                ToolResult(
                    name="request_owner_task",
                    output="filed",
                    metadata={"owner_task": {"title": "Probe mic", "body": "steps"}},
                ),
            ),
        )
        return loop

    config = DashboardConfig(provider="ollama", model="fake")
    execute = build_executor(
        config,
        ProjectRoots(()),
        tmp_path,
        client_factory=lambda backend: object(),
        loop_factory=factory_loop,
        inbox_create=inbox_create,
    )
    receipt = execute({"id": "r1", "title": "t", "body": "b"})
    assert receipt["status"] == "completed"
    assert receipt["owner_tasks"] == ["task-1"]
    assert filed[0]["task_type"] == "task"
    assert filed[0]["task_id"] == "r1"
    assert filed[0]["context_refs"] == ["run:r1"]


def test_owner_tasks_without_inbox_fail_closed(tmp_path) -> None:
    FakeLoop.instances = []

    def factory_loop(client, registry, context, **kwargs):
        loop = FakeLoop(client, registry, context, **kwargs)
        loop.result = AgentResult(
            response=_response("needs a human"),
            tool_results=(
                ToolResult(
                    name="request_owner_task",
                    output="filed",
                    metadata={"owner_task": {"title": "Probe mic", "body": "steps"}},
                ),
            ),
        )
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
    assert "no inbox is wired" in receipt["error"]


def test_child_staged_merges_into_receipt(tmp_path) -> None:
    FakeLoop.instances = []

    def factory_loop(client, registry, context, **kwargs):
        loop = FakeLoop(client, registry, context, **kwargs)
        loop.result = AgentResult(
            response=_response("delegated"),
            tool_results=(
                ToolResult(
                    name="delegate_task",
                    output="child done",
                    metadata={"child_staged": [{"relpath": "kid.py", "content": "x"}]},
                ),
            ),
        )
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
    assert receipt["staged"] == [{"relpath": "kid.py", "content": "x"}]


def test_delegate_tool_carries_run_fanout(harness) -> None:
    execute, _factory, _project = harness
    execute({"id": "r1", "title": "t", "body": "b", "fanout_policy": "allowed"})
    registry = FakeLoop.instances[-1].registry
    assert registry.get("delegate_task").fanout.value == "allowed"
    execute({"id": "r2", "title": "t", "body": "b"})
    assert FakeLoop.instances[-1].registry.get("delegate_task").fanout.value == "restricted"


def test_executor_sizes_ollama_context(harness, tmp_path) -> None:
    execute, _, _ = harness
    receipt = execute({"id": "r1", "title": "Do it", "body": "do the thing"})
    assert receipt["status"] == "completed"
    metadata = FakeLoop.instances[-1].kwargs["request_metadata"]
    assert metadata["ollama_context_length"] == 32768


def test_blank_summary_falls_back_to_receipt(tmp_path) -> None:
    FakeLoop.instances = []
    loop_result = AgentResult(
        response=_response("   "),
        tool_results=(
            ToolResult(name="read_file", output="ok"),
            ToolResult(
                name="stage_file",
                output="staged",
                metadata={"staged": {"relpath": "a.py", "content": "x"}},
            ),
        ),
        iterations=2,
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
    receipt = execute({"id": "r1", "title": "t", "body": "b"})
    assert receipt["status"] == "completed"
    assert receipt["summary"].strip() != ""
    assert "read_file" in receipt["summary"]
    assert "a.py" in receipt["summary"]


def test_reconstruction_budgets_flow_to_loop(harness) -> None:
    execute, _factory, _project = harness
    execute({"id": "r1", "title": "t", "body": "b"})
    kwargs = FakeLoop.instances[-1].kwargs
    assert kwargs["max_iterations"] == 50
    assert kwargs["loop_context_budget_chars"] == 100000
    assert kwargs["require_grounded_reports"] is True


def test_executor_config_overrides_budgets(tmp_path) -> None:
    from ai_agent.staged_edits import ProjectRoots

    FakeLoop.instances = []
    config = DashboardConfig(
        provider="ollama",
        model="fake",
        max_iterations=7,
        loop_context_budget_chars=0,
        require_grounded_reports=False,
    )
    execute = build_executor(
        config,
        ProjectRoots((str(tmp_path),)),
        tmp_path,
        client_factory=lambda backend: object(),
        loop_factory=FakeLoop,
    )
    execute({"id": "r1", "title": "t", "body": "b"})
    kwargs = FakeLoop.instances[-1].kwargs
    assert kwargs["max_iterations"] == 7
    assert kwargs["loop_context_budget_chars"] is None
    assert kwargs["require_grounded_reports"] is False


def test_receipt_carries_compactions(tmp_path) -> None:
    from ai_agent.staged_edits import ProjectRoots

    FakeLoop.instances = []

    def factory_loop(client, registry, context, **kwargs):
        loop = FakeLoop(client, registry, context, **kwargs)
        loop.result = AgentResult(response=_response("done"), compactions=2)
        return loop

    config = DashboardConfig(provider="ollama", model="fake")
    execute = build_executor(
        config,
        ProjectRoots((str(tmp_path),)),
        tmp_path,
        client_factory=lambda backend: object(),
        loop_factory=factory_loop,
    )
    receipt = execute({"id": "r1", "title": "t", "body": "b"})
    assert receipt["compactions"] == 2


CATALOG_TOML = """[[models]]
route_id = "ollama/fake-local"
provider = "ollama"
product = "ollama"
model = "fake-local"
location = "local"
access_method = "local_runtime"
auth_method = "none"
billing_source = "local_free"
cost_policy_tier = "local_only"
quality = "standard"
latency = "interactive"

[models.capabilities]
chat = true
streaming = true
tools = true
structured_output = false
multimodal_input = false
embeddings = false

[models.context_limits]
context_window_tokens = 32768
runtime_context_tokens = 4096

[models.estimate]
typical_latency_seconds = 1.0
input_cost_per_million_tokens = 0
output_cost_per_million_tokens = 0
"""


def test_configured_routing_uses_dashboard_model(harness) -> None:
    FakeLoop.instances = []
    execute, seen, project = harness
    receipt = execute({"id": "r1", "title": "t", "body": "b"})
    assert seen[-1].model == "fake"
    assert receipt["route_id"] == "ollama/fake"


def test_auto_routing_selects_from_catalog(tmp_path) -> None:
    from ai_agent.staged_edits import ProjectRoots

    FakeLoop.instances = []
    catalog = tmp_path / "catalog.toml"
    catalog.write_text(CATALOG_TOML, encoding="utf-8")
    seen: list = []
    config = DashboardConfig(
        provider="ollama", model="fallback", route_policy="auto", catalog_path=str(catalog)
    )
    execute = build_executor(
        config,
        ProjectRoots((str(tmp_path),)),
        tmp_path,
        client_factory=lambda backend: seen.append(backend) or object(),
        loop_factory=FakeLoop,
    )
    receipt = execute({"id": "r1", "title": "t", "body": "b"})
    assert seen[-1].model == "fake-local"
    assert receipt["route_id"] == "ollama/fake-local"


def test_auto_routing_falls_back_to_configured(tmp_path) -> None:
    from ai_agent.staged_edits import ProjectRoots

    FakeLoop.instances = []
    seen: list = []
    config = DashboardConfig(
        provider="ollama",
        model="fallback",
        route_policy="auto",
        catalog_path=str(tmp_path / "absent.toml"),
    )
    execute = build_executor(
        config,
        ProjectRoots((str(tmp_path),)),
        tmp_path,
        client_factory=lambda backend: seen.append(backend) or object(),
        loop_factory=FakeLoop,
    )
    receipt = execute({"id": "r1", "title": "t", "body": "b"})
    assert seen[-1].model == "fallback"
    assert receipt["route_id"] == "ollama/fallback"


def test_shell_toggle_denies_execution_tools(harness) -> None:
    from ai_agent.contracts import PermissionAction
    from ai_agent.staged_edits import ProjectRoots
    from ai_agent.tools.shell import RunCommandTool

    FakeLoop.instances = []
    execute, _seen, project = harness
    config = DashboardConfig(provider="ollama", model="fake")
    execute = build_executor(
        config,
        ProjectRoots((str(project),)),
        project,
        client_factory=lambda backend: object(),
        loop_factory=FakeLoop,
        restrictions={"shell_tools": False},
    )
    execute({"id": "r1", "title": "t", "body": "b"})
    permissions = FakeLoop.instances[-1].kwargs["permissions"]
    assert (
        permissions.policy.action_for_tool("run_command", RunCommandTool().definition.category)
        is PermissionAction.DENY
    )


def test_sandbox_toggle_pins_context(harness) -> None:
    from ai_agent.staged_edits import ProjectRoots

    FakeLoop.instances = []
    _execute, _seen, project = harness
    config = DashboardConfig(provider="ollama", model="fake")
    execute = build_executor(
        config,
        ProjectRoots((str(project),)),
        project,
        client_factory=lambda backend: object(),
        loop_factory=FakeLoop,
        restrictions={"sandbox": True},
    )
    execute({"id": "r1", "title": "t", "body": "b"})
    assert FakeLoop.instances[-1].context.sandbox is True


def test_delegation_toggle_sets_default_fanout(harness) -> None:
    from ai_agent.staged_edits import ProjectRoots

    FakeLoop.instances = []
    _execute, _seen, project = harness
    config = DashboardConfig(provider="ollama", model="fake")
    execute = build_executor(
        config,
        ProjectRoots((str(project),)),
        project,
        client_factory=lambda backend: object(),
        loop_factory=FakeLoop,
        restrictions={"delegation": True},
    )
    execute({"id": "r1", "title": "t", "body": "b"})
    assert FakeLoop.instances[-1].kwargs["fanout_policy"] == "allowed"


def test_closeout_settles_run_to_ledger(tmp_path) -> None:
    from ai_agent.staged_edits import ProjectRoots
    from ai_orchestrator.spend_ledger import SpendLedger

    FakeLoop.instances = []
    ledger = SpendLedger(tmp_path / "spend.sqlite3")
    config = DashboardConfig(provider="ollama", model="fake")
    execute = build_executor(
        config,
        ProjectRoots((str(tmp_path),)),
        tmp_path,
        client_factory=lambda backend: object(),
        loop_factory=FakeLoop,
        spend_ledger=ledger,
    )
    receipt = execute({"id": "r1", "title": "t", "body": "b"})
    assert receipt["status"] == "completed"
    records = SpendLedger(tmp_path / "spend.sqlite3").records()
    assert len(records) == 1
    assert (records[0].task_id, records[0].provider) == ("r1", "ollama")


def test_closeout_without_ledger_skips_settle(tmp_path) -> None:
    from ai_agent.staged_edits import ProjectRoots

    FakeLoop.instances = []
    config = DashboardConfig(provider="ollama", model="fake")
    execute = build_executor(
        config,
        ProjectRoots((str(tmp_path),)),
        tmp_path,
        client_factory=lambda backend: object(),
        loop_factory=FakeLoop,
    )
    assert execute({"id": "r1", "title": "t", "body": "b"})["status"] == "completed"


def test_grant_bootstrap_is_sticky_and_guarded(tmp_path) -> None:
    import json

    import pytest
    from dashboard_web_app import load_spend_ledger

    grants = tmp_path / "spend" / "grants"
    grants.mkdir(parents=True)
    grant_file = grants / "g.json"
    grant_file.write_text(
        json.dumps(
            {
                "allowance_id": "nov-evals",
                "provider": "meta",
                "kind": "allowance_expiring",
                "granted_cents": 15000,
                "expires_at": 1_800_000_000.0,
                "local_spending_limit_accepted": True,
            }
        ),
        encoding="utf-8",
    )
    first = load_spend_ledger(tmp_path)
    assert first.get_allowance("nov-evals").balance_cents == 15000
    # Second open keeps DB state (bootstrap skips known ids).
    second = load_spend_ledger(tmp_path)
    assert second.get_allowance("nov-evals").balance_cents == 15000
    # Changed grant file fails loud instead of silently forking balances.
    grant_file.write_text(
        json.dumps(
            {
                "allowance_id": "nov-evals",
                "provider": "meta",
                "kind": "allowance_expiring",
                "granted_cents": 99999,
                "expires_at": 1_800_000_000.0,
                "local_spending_limit_accepted": True,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="re-bootstrap"):
        load_spend_ledger(tmp_path)
