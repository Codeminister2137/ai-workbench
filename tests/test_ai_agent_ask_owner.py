"""ask_owner: live owner questions on interactive turns, fail-closed elsewhere."""

from collections.abc import Callable
from dataclasses import replace
from typing import Any, cast

import pytest
from ai_agent.delegation_scope import DelegationBudget, DelegationScope
from ai_agent.permissions import PermissionManager
from ai_agent.tool_profiles import CODING_PROFILE, shared_tool_registry
from ai_agent.tools.base import ToolContext, ToolRegistry
from ai_agent.tools.filesystem import ReadFileTool
from ai_agent.tools.owner_tasks import AskOwnerTool, OwnerTaskTool


def _scope(tmp_path, **overrides):
    base: dict[str, Any] = dict(
        registry=ToolRegistry(tools=(ReadFileTool(),)),
        permissions=PermissionManager(),
        workspace=tmp_path,
        budget=DelegationBudget(5),
        approved_client=object(),
    )
    base.update(overrides)
    return DelegationScope(**base)


def test_live_channel_returns_answer(tmp_path) -> None:
    seen = []
    context = ToolContext(
        workspace_root=tmp_path,
        owner_prompt=lambda question: seen.append(question) or "use sqlite",
    )
    result = AskOwnerTool().execute({"question": "Which store?"}, context)
    assert result.is_error is False
    assert result.output == "Owner answer: use sqlite"
    assert seen == ["Which store?"]


def test_missing_channel_fails_closed_with_guidance(tmp_path) -> None:
    result = AskOwnerTool().execute({"question": "Which store?"}, ToolContext(tmp_path))
    assert result.is_error is True
    assert "request_owner_task" in result.output


def test_delegated_child_cannot_prompt(tmp_path) -> None:
    child = _scope(tmp_path).narrow()
    context = ToolContext(
        workspace_root=tmp_path,
        delegation=child,
        owner_prompt=lambda question: "must not be reached",
    )
    assert context.owner_prompt is None  # cleared by fail-closed post-init
    result = AskOwnerTool().execute({"question": "Which store?"}, context)
    assert result.is_error is True
    assert "request_owner_task" in result.output


def test_channel_failure_is_an_error_result(tmp_path) -> None:
    def closed(_question: str) -> str:
        raise EOFError("stdin closed")

    context = ToolContext(workspace_root=tmp_path, owner_prompt=closed)
    result = AskOwnerTool().execute({"question": "Which store?"}, context)
    assert result.is_error is True
    assert "EOFError" in result.output


def test_non_text_answer_is_an_error_result(tmp_path) -> None:
    # Intentionally mistyped channel: the tool must fail closed on non-text.
    mistyped = cast(Callable[[str], str], lambda _q: None)
    context = ToolContext(workspace_root=tmp_path, owner_prompt=mistyped)
    result = AskOwnerTool().execute({"question": "Which store?"}, context)
    assert result.is_error is True
    assert "non-text" in result.output


@pytest.mark.parametrize("question", ["", "   ", "x" * 2001, None, 42])
def test_question_validation(tmp_path, question) -> None:
    context = ToolContext(workspace_root=tmp_path, owner_prompt=lambda _q: "unreached")
    result = AskOwnerTool().execute({"question": question}, context)
    assert result.is_error is True
    assert "1-2000" in result.output


def test_child_registry_never_carries_ask_owner(tmp_path) -> None:
    scope = _scope(
        tmp_path,
        registry=ToolRegistry(tools=(ReadFileTool(), AskOwnerTool(), OwnerTaskTool())),
    )
    names = {item.name for item in scope.child_registry().list_definitions()}
    assert "ask_owner" not in names
    assert "request_owner_task" in names  # async filing stays grantable


def test_coding_profile_exposes_both_owner_tools(tmp_path) -> None:
    assert "ask_owner" in CODING_PROFILE.tool_names
    assert "request_owner_task" in CODING_PROFILE.tool_names
    registry = shared_tool_registry("coding")
    assert registry.get("ask_owner") is not None
    assert registry.get("request_owner_task") is not None


def test_owner_task_still_files_metadata(tmp_path) -> None:
    result = OwnerTaskTool().execute(
        {"title": "Manual check", "body": "Run the installer."}, ToolContext(tmp_path)
    )
    assert result.is_error is False
    assert result.metadata["owner_task"]["title"] == "Manual check"


def test_replace_into_child_clears_channel(tmp_path) -> None:
    parent = ToolContext(workspace_root=tmp_path, owner_prompt=lambda question: "parent answer")
    child = replace(parent, delegation=_scope(tmp_path).narrow())
    assert child.owner_prompt is None
