"""Delegation depth bound: two levels by default, cap enforced twice."""

import pytest
from ai_agent.delegation_runner import build_child_runner
from ai_agent.delegation_scope import DelegationBudget, DelegationScope
from ai_agent.permissions import PermissionManager
from ai_agent.tools.base import ToolRegistry
from ai_agent.tools.delegation import DelegateTaskTool
from ai_agent.tools.filesystem import ReadFileTool


class FakeLoop:
    def __init__(self, client, registry, context, **kwargs):
        self.registry = registry
        self.context = context

    def run(self, prompt: str, **kwargs):
        raise AssertionError("child loop must not run in registry tests")


def _parent_scope(tmp_path, **overrides):
    runner = build_child_runner(loop_factory=FakeLoop)
    registry = ToolRegistry(tools=(ReadFileTool(), DelegateTaskTool(runner=runner)))
    base = dict(
        registry=registry,
        permissions=PermissionManager(),
        workspace=tmp_path,
        budget=DelegationBudget(5),
        approved_client=object(),
    )
    base.update(overrides)
    return DelegationScope(**base)


def _names(scope: DelegationScope) -> set[str]:
    return {item.name for item in scope.child_registry().list_definitions()}


def test_child_below_cap_keeps_delegate_tool(tmp_path) -> None:
    parent = _parent_scope(tmp_path)  # depth 0, default max_depth 2
    assert "delegate_task" in _names(parent)


def test_grandchild_at_cap_loses_delegate_tool(tmp_path) -> None:
    child = _parent_scope(tmp_path).narrow()  # depth 1
    assert child.depth == 1
    assert "delegate_task" not in _names(child)


def test_max_depth_one_preserves_single_level(tmp_path) -> None:
    parent = _parent_scope(tmp_path, max_depth=1)
    assert "delegate_task" not in _names(parent)


def test_narrow_at_cap_refuses_spawn(tmp_path) -> None:
    grandchild = _parent_scope(tmp_path).narrow().narrow()  # depth 2
    assert grandchild.depth == 2
    with pytest.raises(ValueError, match="maximum depth"):
        grandchild.narrow()
