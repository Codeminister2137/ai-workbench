"""Named subagent profiles: researcher/coder/reviewer presets for delegate_task."""

from typing import Any

import pytest
from ai_agent.contracts import ToolResult
from ai_agent.delegation_scope import (
    SUBAGENT_PROFILES,
    DelegationBudget,
    DelegationScope,
    resolve_subagent_profile,
)
from ai_agent.permissions import PermissionManager, PermissionPolicy
from ai_agent.tools import default_coding_tools
from ai_agent.tools.base import ToolContext
from ai_agent.tools.delegation import (
    DelegateTaskTool,
    coding_tools_with_delegation,
    unavailable_delegation,
)


def _scope(tmp_path, **overrides: Any) -> DelegationScope:
    base: dict[str, Any] = dict(
        registry=default_coding_tools(),
        permissions=PermissionManager(policy=PermissionPolicy.permissive()),
        workspace=tmp_path,
        budget=DelegationBudget(5),
    )
    base.update(overrides)
    return DelegationScope(**base)


def _capture() -> tuple[list, DelegateTaskTool]:
    seen: list = []

    def runner(task: str, context: ToolContext) -> ToolResult:
        seen.append((task, context.delegation))
        return ToolResult(name="delegate_task", output="child ok")

    return seen, DelegateTaskTool(runner=runner)


@pytest.mark.parametrize(
    ("name", "permission", "must_have", "must_lack"),
    [
        ("researcher", "read_only", {"read_file", "search_web"}, {"edit_file", "fetch_url"}),
        ("coder", "workspace_write", {"edit_file", "run_command"}, {"ask_owner"}),
        ("reviewer", "read_only", {"read_file", "git_diff"}, {"fetch_url"}),
    ],
)
def test_preset_applies_permission_and_tools(tmp_path, name, permission, must_have, must_lack):
    seen, tool = _capture()
    context = ToolContext(workspace_root=tmp_path, delegation=_scope(tmp_path))
    result = tool.execute({"task": "do it", "profile": name}, context)
    assert result.is_error is False
    (task, child), *_ = seen
    assert task == "do it"
    assert child.profile == permission
    assert must_have <= set(child.tools or ())
    assert not (must_lack & set(child.tools or ()))


def test_unknown_profile_is_an_error(tmp_path) -> None:
    seen, tool = _capture()
    context = ToolContext(workspace_root=tmp_path, delegation=_scope(tmp_path))
    result = tool.execute({"task": "do it", "profile": "janitor"}, context)
    assert result.is_error is True
    assert "Unknown subagent profile" in result.output
    assert seen == []


def test_explicit_tools_intersect_preset(tmp_path) -> None:
    seen, tool = _capture()
    context = ToolContext(workspace_root=tmp_path, delegation=_scope(tmp_path))
    result = tool.execute(
        {"task": "do it", "profile": "coder", "allowed_tools": ["read_file", "edit_file"]},
        context,
    )
    assert result.is_error is False
    assert set(seen[0][1].tools or ()) == {"read_file", "edit_file"}


def test_explicit_permission_replaces_preset_default(tmp_path) -> None:
    seen, tool = _capture()
    context = ToolContext(workspace_root=tmp_path, delegation=_scope(tmp_path))
    result = tool.execute(
        {"task": "do it", "profile": "coder", "permission_profile": "read_only"},
        context,
    )
    assert result.is_error is False
    assert seen[0][1].profile == "read_only"


def test_profile_without_scope_is_refused(tmp_path) -> None:
    seen, tool = _capture()
    result = tool.execute({"task": "do it", "profile": "coder"}, ToolContext(tmp_path))
    assert result.is_error is True
    assert "no host-bound parent authority" in result.output
    assert seen == []


def test_preset_never_escapes_parent_grant(tmp_path) -> None:
    seen, tool = _capture()
    parent = _scope(tmp_path, tools=frozenset({"read_file"}))
    context = ToolContext(workspace_root=tmp_path, delegation=parent)
    result = tool.execute({"task": "do it", "profile": "coder"}, context)
    assert result.is_error is False
    assert set(seen[0][1].tools or ()) == {"read_file"}


def test_presets_reference_known_tools_and_permissions() -> None:
    from ai_agent.permissions import PermissionPolicy

    known = {item.name for item in default_coding_tools().list_definitions()}
    known |= {
        item.name
        for item in coding_tools_with_delegation(unavailable_delegation).list_definitions()
    }
    assert set(SUBAGENT_PROFILES) == {"researcher", "coder", "reviewer"}
    for preset in SUBAGENT_PROFILES.values():
        assert set(preset.tools) <= known, preset.name
        PermissionPolicy.from_approval_preset(preset.permission)
    assert resolve_subagent_profile("coder").name == "coder"
    with pytest.raises(ValueError, match="Unknown subagent profile"):
        resolve_subagent_profile("janitor")
