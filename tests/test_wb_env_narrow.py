"""Regression tests for workbench secret-exposure narrowing (env allowlists)."""

from __future__ import annotations

import ast
import importlib.util
import os
from dataclasses import replace
from pathlib import Path

import pytest
from ai_agent.delegation_scope import DelegationBudget, DelegationScope
from ai_agent.permissions import PermissionManager
from ai_agent.tools.base import ToolContext, ToolRegistry
from ai_agent.tools.shell import RunCommandTool
from ai_orchestrator import AccessMethod
from ai_provider.external_agents import ExternalAgentConfig
from ai_provider.foreground_tools import ForegroundTools

PLANTED_KEY = "WB_NARROW_PLANTED_SECRET"
PLANTED_VALUE = "planted-secret-value"

REPO_ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE_SCRIPT = REPO_ROOT / "scripts" / "alternate-agent-acceptance.py"


def _acceptance_module():
    spec = importlib.util.spec_from_file_location("alternate_agent_acceptance", ACCEPTANCE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _child_scope(workspace: Path) -> DelegationScope:
    grant = DelegationScope(
        ToolRegistry(()), PermissionManager(), workspace.resolve(), DelegationBudget(8)
    )
    return grant.narrow()


def test_default_context_denies_ambient_secret(tmp_path, monkeypatch):
    monkeypatch.setenv(PLANTED_KEY, PLANTED_VALUE)
    context = ToolContext(tmp_path)
    assert context.inherit_environment is False
    assert PLANTED_KEY not in context.command_environment()


def test_delegated_child_lacks_secret_despite_parent_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv(PLANTED_KEY, PLANTED_VALUE)
    owner = ToolContext.for_interactive_owner(tmp_path)
    assert PLANTED_KEY in owner.command_environment()
    # Exactly how DelegateTaskTool builds the child context.
    child = replace(owner, delegation=_child_scope(tmp_path))
    assert child.inherit_environment is False
    assert PLANTED_KEY not in child.command_environment()


def test_explicit_opt_in_on_delegated_child_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv(PLANTED_KEY, PLANTED_VALUE)
    context = ToolContext(tmp_path, delegation=_child_scope(tmp_path), inherit_environment=True)
    assert context.inherit_environment is False
    assert PLANTED_KEY not in context.command_environment()


def test_owner_opt_in_still_runs_commands(tmp_path, monkeypatch):
    monkeypatch.setenv(PLANTED_KEY, PLANTED_VALUE)
    owner = ToolContext.for_interactive_owner(tmp_path)
    result = RunCommandTool().execute({"command": "echo wb-owner-ok"}, owner)
    assert not result.is_error
    assert "wb-owner-ok" in result.output


def test_foreground_mcp_child_env_excludes_ambient_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv(PLANTED_KEY, PLANTED_VALUE)
    monkeypatch.setenv("REQUESTY_API_KEY", "fake-requesty-key")
    foreground = ForegroundTools(tmp_path)
    try:
        config = ExternalAgentConfig(
            AccessMethod.CODEX_CLI,
            "fixture-client",
            "auto",
            tmp_path,
            10,
            sandbox="read-only",
            approval_policy="trusted_local",
            shared_tool_profile="coding",
            shared_task_id="fixture-task",
        )
        with foreground.invocation(config) as scoped:
            assert scoped.shared_child_env is not None
            assert scoped.shared_token_env is not None
            assert PLANTED_KEY not in scoped.shared_child_env
            assert "REQUESTY_API_KEY" not in scoped.shared_child_env
            assert scoped.shared_child_env[scoped.shared_token_env]
            if "PATH" in os.environ:
                assert scoped.shared_child_env.get("PATH") == os.environ["PATH"]
    finally:
        foreground.close()


def test_acceptance_route_env_carries_only_its_keys():
    module = _acceptance_module()
    assert set(module.ROUTE_ENV_KEYS) == set(module.ROUTES)
    source = {
        "PATH": "/fake/path",
        "REQUESTY_API_KEY": "requesty-secret",
        "ANTIGRAVITY_COMMAND": "antigravity-secret",
        "GITHUB_COPILOT_COMMAND": "copilot-secret",
        "KIRO_COMMAND": "kiro-secret",
        PLANTED_KEY: PLANTED_VALUE,
    }
    for route, keys in module.ROUTE_ENV_KEYS.items():
        environment = module.build_route_env(route, source)
        assert environment["PATH"] == "/fake/path"
        for key in keys:
            assert environment[key] == source[key]
        assert PLANTED_KEY not in environment
        for other_route, other_keys in module.ROUTE_ENV_KEYS.items():
            if other_route != route:
                for other_key in other_keys:
                    assert other_key not in environment
    with pytest.raises(ValueError, match="Unknown acceptance route"):
        module.build_route_env("no/such-route", source)


def test_acceptance_base_env_has_no_credentials():
    module = _acceptance_module()
    source = {
        "PATH": "/fake/path",
        "REQUESTY_API_KEY": "requesty-secret",
        PLANTED_KEY: PLANTED_VALUE,
    }
    assert module.build_base_env(source) == {"PATH": "/fake/path"}


def test_acceptance_children_all_use_explicit_env():
    tree = ast.parse(ACCEPTANCE_SCRIPT.read_text(encoding="utf-8"))
    runs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
    ]
    assert runs
    for node in runs:
        assert any(keyword.arg == "env" for keyword in node.keywords), (
            "every acceptance subprocess.run must pass an explicit env"
        )
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.ctx, ast.Store)
            and ast.unparse(node.value) == "os.environ"
        ):
            pytest.fail("acceptance script must not mutate os.environ")
