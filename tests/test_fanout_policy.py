"""Run-level fan-out policy: restricted/denied runs cannot spawn children."""

import sqlite3
import time

import pytest
from ai_agent import AgentLoop, PermissionManager, PermissionPolicy
from ai_agent.contracts import ToolCall, ToolResult
from ai_agent.delegation_scope import DelegationBudget, DelegationScope
from ai_agent.fanout import FanoutPolicy, resolve_fanout_policy
from ai_agent.repo_assistant_args import build_argument_parser
from ai_agent.shared_approvals import scoped_registry
from ai_agent.tools import ToolContext, ToolRegistry
from ai_agent.tools.delegation import DelegateTaskTool, coding_tools_with_delegation
from ai_provider import (
    AIMessage,
    AIResponse,
    AIToolCall,
    BackendInfo,
    BackendLocation,
    MessageRole,
)
from ai_provider.orchestrated_runs import SQLiteOrchestratedRunStore

FORBIDDEN = ("restricted", "denied")


class Client:
    backend = BackendInfo("ollama", "parent-model", BackendLocation.LOCAL)

    def __init__(self, replies):
        self.replies = iter(replies)

    def complete(self, request):
        calls = next(self.replies)
        return AIResponse(
            AIMessage(MessageRole.ASSISTANT, "Done" if not calls else "", tool_calls=tuple(calls)),
            self.backend,
            tool_calls=tuple(calls),
        )

    def stream(self, request):
        raise NotImplementedError


def make_scope(tmp_path, **kwargs):
    return DelegationScope(
        ToolRegistry(()),
        PermissionManager(PermissionPolicy.permissive()),
        tmp_path,
        DelegationBudget(8, time.perf_counter() + 30),
        **kwargs,
    )


def test_resolve_accepts_known_values_case_insensitively():
    assert resolve_fanout_policy("allowed") is FanoutPolicy.ALLOWED
    assert resolve_fanout_policy(" Restricted ") is FanoutPolicy.RESTRICTED
    assert resolve_fanout_policy(FanoutPolicy.DENIED) is FanoutPolicy.DENIED


def test_resolve_rejects_unknown_values():
    with pytest.raises(ValueError, match="fan-out policy"):
        resolve_fanout_policy("sometimes")


@pytest.mark.parametrize(
    ("configured", "parent", "expected"),
    [
        ("allowed", None, FanoutPolicy.ALLOWED),
        ("allowed", "allowed", FanoutPolicy.ALLOWED),
        ("allowed", "restricted", FanoutPolicy.RESTRICTED),
        ("allowed", "denied", FanoutPolicy.DENIED),
        ("restricted", "allowed", FanoutPolicy.RESTRICTED),
        ("restricted", "denied", FanoutPolicy.DENIED),
        ("denied", "allowed", FanoutPolicy.DENIED),
    ],
)
def test_resolve_never_widens_parent_grant(configured, parent, expected):
    assert resolve_fanout_policy(configured, parent) is expected


def test_narrow_allows_spawn_when_allowed(tmp_path):
    child = make_scope(tmp_path).narrow()
    assert child.fanout is FanoutPolicy.ALLOWED
    assert child.depth == 1


@pytest.mark.parametrize("policy", FORBIDDEN)
def test_narrow_refuses_spawn_when_forbidden(tmp_path, policy):
    scope = make_scope(tmp_path, fanout=policy)
    assert scope.fanout is FanoutPolicy(policy)
    with pytest.raises(ValueError, match="fan-out"):
        scope.narrow()


@pytest.mark.parametrize("policy", FORBIDDEN)
def test_unscoped_tool_path_refuses_spawn_when_forbidden(tmp_path, policy):
    calls = []

    def runner(task, context):
        calls.append(task)
        return ToolResult("delegate_task", "must not run")

    result = DelegateTaskTool(runner, fanout=policy).run(
        ToolCall("delegate_task", {"task": "Inspect source"}), ToolContext(tmp_path)
    )
    assert result.is_error and "fan-out" in result.output
    assert calls == []


@pytest.mark.parametrize("policy", FORBIDDEN)
def test_scoped_tool_path_refuses_spawn_when_scope_forbids(tmp_path, policy):
    calls = []

    def runner(task, context):
        calls.append(task)
        return ToolResult("delegate_task", "must not run")

    scope = make_scope(tmp_path, fanout=policy)
    result = DelegateTaskTool(runner).run(
        ToolCall("delegate_task", {"task": "Inspect source"}),
        ToolContext(tmp_path, delegation=scope),
    )
    assert result.is_error and "fan-out" in result.output
    assert calls == []


def test_allowed_scope_and_tool_spawn(tmp_path):
    calls = []

    def runner(task, context):
        calls.append(task)
        assert context.delegation is not None and context.delegation.depth == 1
        return ToolResult("delegate_task", "child report")

    scope = make_scope(tmp_path)
    result = DelegateTaskTool(runner).run(
        ToolCall("delegate_task", {"task": "Inspect source"}),
        ToolContext(tmp_path, delegation=scope),
    )
    assert not result.is_error
    assert calls == ["Inspect source"]


@pytest.mark.parametrize("policy", FORBIDDEN)
def test_shared_approval_injection_path_refuses_spawn(tmp_path, policy):
    calls = []

    def runner(task, context):
        calls.append(task)
        return ToolResult("delegate_task", "must not run")

    registry = scoped_registry(
        ToolRegistry((DelegateTaskTool(runner),)),
        PermissionManager(PermissionPolicy.permissive()),
        tmp_path,
        "task-1",
        "run-1",
        fanout=policy,
    )
    result = registry.execute(
        ToolCall("delegate_task", {"task": "Inspect source"}), ToolContext(tmp_path)
    )
    assert result.is_error and "fan-out" in result.output
    assert calls == []


@pytest.mark.parametrize("policy", FORBIDDEN)
def test_agent_loop_blocks_delegate_task_when_forbidden(tmp_path, policy):
    calls = []

    def runner(task, context):
        calls.append(task)
        return ToolResult("delegate_task", "must not run")

    parent = Client([[AIToolCall("child", "delegate_task", {"task": "Implement answer"})], []])
    result = AgentLoop(
        parent,
        ToolRegistry((DelegateTaskTool(runner),)),
        ToolContext(tmp_path),
        permissions=PermissionManager(PermissionPolicy.permissive()),
        max_iterations=2,
        fanout_policy=policy,
    ).run("Original task")
    assert result.tool_results[0].is_error
    assert "fan-out" in result.tool_results[0].output
    assert calls == []


def test_coding_tools_factory_defaults_to_allowed_and_carries_policy():
    def runner(task, context):
        return ToolResult("delegate_task", "child report")

    default_tool = coding_tools_with_delegation(runner).get("delegate_task")
    assert isinstance(default_tool, DelegateTaskTool)
    assert default_tool.fanout is FanoutPolicy.ALLOWED
    denied_tool = coding_tools_with_delegation(runner, fanout="denied").get("delegate_task")
    assert isinstance(denied_tool, DelegateTaskTool)
    assert denied_tool.fanout is FanoutPolicy.DENIED


def test_cli_flag_defaults_to_allowed_and_accepts_denied():
    parser = build_argument_parser()
    assert parser.parse_args([]).fanout_policy == "allowed"
    assert parser.parse_args(["--fanout-policy", "denied"]).fanout_policy == "denied"


def make_run_kwargs(**overrides):
    kwargs = {
        "repo_root": ".",
        "mode": "implement",
        "prompt": "synthetic fan-out check",
        "budget_seconds": 60.0,
        "approval_policy": "interactive",
        "primary_route_id": None,
        "primary_provider": None,
        "primary_model": None,
    }
    kwargs.update(overrides)
    return kwargs


def test_run_record_persists_configured_and_effective_policy(tmp_path):
    store = SQLiteOrchestratedRunStore(tmp_path / "runs.sqlite3")
    created = store.create_run(
        **make_run_kwargs(fanout_policy="restricted", fanout_effective="restricted")
    )
    assert created.fanout_policy == "restricted"
    assert created.fanout_effective == "restricted"
    fetched = store.get_run(created.run_id)
    assert fetched is not None
    assert fetched.fanout_policy == "restricted"
    assert fetched.fanout_effective == "restricted"


def test_run_record_defaults_to_allowed(tmp_path):
    store = SQLiteOrchestratedRunStore(tmp_path / "runs.sqlite3")
    created = store.create_run(**make_run_kwargs())
    assert created.fanout_policy == "allowed"
    assert created.fanout_effective == "allowed"
    assert store.get_run(created.run_id) == created


def test_pre_policy_database_gains_fanout_columns(tmp_path):
    db = tmp_path / "runs.sqlite3"
    connection = sqlite3.connect(db)
    try:
        connection.execute(
            """
            CREATE TABLE orchestrated_runs (
                run_id TEXT PRIMARY KEY,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                repo_root TEXT NOT NULL,
                mode TEXT NOT NULL,
                prompt_preview TEXT NOT NULL,
                budget_seconds REAL NOT NULL,
                approval_policy TEXT NOT NULL,
                status TEXT NOT NULL,
                execution_status TEXT,
                primary_route_id TEXT,
                primary_provider TEXT,
                primary_model TEXT,
                schema_version INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO orchestrated_runs VALUES "
            "('run-1', 't', 't', '.', 'implement', 'p', 60, 'interactive', "
            "'planned', NULL, NULL, NULL, NULL, 1)"
        )
        connection.commit()
    finally:
        connection.close()
    record = SQLiteOrchestratedRunStore(db).get_run("run-1")
    assert record is not None
    assert record.fanout_policy == "allowed"
    assert record.fanout_effective == "allowed"
