"""Governance tiers: per-tool rules, fail-closed approval, sandbox cwd."""

from __future__ import annotations

import pytest
from ai_agent import (
    AgentLoop,
    PermissionManager,
    PermissionPolicy,
    ToolCall,
    ToolContext,
    default_coding_tools,
)
from ai_agent.contracts import PermissionAction, ToolCategory
from ai_agent.repo_assistant_args import build_argument_parser
from ai_agent.repo_coding_assistant import _policy_with_tool_rules
from ai_agent.tools.filesystem import CreateFileTool, ReadFileTool
from ai_agent.tools.shell import RunCommandTool
from ai_provider import (
    AIMessage,
    AIResponse,
    BackendInfo,
    BackendLocation,
    FinishReason,
    MessageRole,
    PrivacyClass,
    UsageMetadata,
)


def test_tool_rule_overrides_category_and_deny_wins() -> None:
    policy = PermissionPolicy(
        tool_rules=(
            ("read_file", PermissionAction.DENY),
            ("run_command", PermissionAction.ALLOW),
            ("run_command", PermissionAction.DENY),
        )
    )
    assert policy.action_for_tool("read_file", ToolCategory.READ) is PermissionAction.DENY
    assert policy.action_for_tool("run_command", ToolCategory.SHELL) is PermissionAction.DENY
    assert policy.action_for_tool("list_dir", ToolCategory.READ) is PermissionAction.ALLOW


def test_last_matching_non_deny_rule_wins() -> None:
    policy = PermissionPolicy(
        tool_rules=(
            ("read_file", PermissionAction.ASK_USER),
            ("read_file", PermissionAction.ALLOW),
        )
    )
    assert policy.action_for_tool("read_file", ToolCategory.READ) is PermissionAction.ALLOW


def test_manager_enforces_tool_rules_without_callback(tmp_path) -> None:
    manager = PermissionManager(
        policy=PermissionPolicy(
            tool_rules=(
                ("create_file", PermissionAction.DENY),
                ("run_command", PermissionAction.ALLOW),
            )
        )
    )
    assert (
        manager.check_and_authorize(
            CreateFileTool(), ToolCall("create_file", {"path": "x", "content": "y"})
        )
        is False
    )
    assert (
        manager.check_and_authorize(
            RunCommandTool(), ToolCall("run_command", {"command": "echo hi"})
        )
        is True
    )
    # Untouched category behavior stays: reads allowed, writes ask (no callback: deny).
    assert manager.check_and_authorize(ReadFileTool(), ToolCall("read_file", {"path": "x"})) is True


def test_approval_timeout_denies_without_raising(tmp_path) -> None:
    from ai_agent.operator_bridge import OperatorBridgeTimeoutError

    def expired(call, category):
        raise OperatorBridgeTimeoutError("External action approval timed out")

    manager = PermissionManager(policy=PermissionPolicy.interactive(), approval_callback=expired)
    assert (
        manager.check_and_authorize(
            CreateFileTool(), ToolCall("create_file", {"path": "x", "content": "y"})
        )
        is False
    )


def test_approval_integrity_errors_still_propagate(tmp_path) -> None:
    from ai_agent.operator_bridge import OperatorBridgeError

    def corrupted(call, category):
        raise OperatorBridgeError("File state changed")

    manager = PermissionManager(policy=PermissionPolicy.interactive(), approval_callback=corrupted)
    with pytest.raises(OperatorBridgeError, match="File state changed"):
        manager.check_and_authorize(
            CreateFileTool(), ToolCall("create_file", {"path": "x", "content": "y"})
        )


class _Client:
    backend = BackendInfo(provider="fake", model="test", location=BackendLocation.LOCAL)

    def __init__(self) -> None:
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        return AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, "Finished"),
            backend=self.backend,
            finish_reason=FinishReason.STOP,
            usage=UsageMetadata(),
        )

    def stream(self, request):
        raise NotImplementedError


def test_denied_tools_hidden_from_model_requests(tmp_path) -> None:
    client = _Client()
    AgentLoop(
        client,
        default_coding_tools(),
        ToolContext(tmp_path),
        permissions=PermissionManager(
            policy=PermissionPolicy(tool_rules=(("run_command", PermissionAction.DENY),))
        ),
        max_iterations=1,
    ).run("Do it", privacy_class=PrivacyClass.LOCAL_ONLY)
    names = {tool.name for tool in client.requests[0].tools}
    assert "run_command" not in names
    assert "read_file" in names


def test_governance_flags_parse() -> None:
    parser = build_argument_parser()
    args = parser.parse_args(
        ["--allow-tool", "read_file", "--deny-tool", "run_command", "--sandbox"]
    )
    assert args.allow_tool == ["read_file"]
    assert args.deny_tool == ["run_command"]
    assert args.ask_tool == []
    assert args.sandbox is True
    defaults = parser.parse_args([])
    assert defaults.allow_tool == [] and defaults.sandbox is False


def test_policy_helper_applies_cli_rules() -> None:
    from argparse import Namespace

    args = Namespace(allow_tool=["read_file"], ask_tool=[], deny_tool=["run_command"])
    policy = _policy_with_tool_rules(PermissionPolicy.interactive(), args)
    assert policy.action_for_tool("run_command", ToolCategory.SHELL) is PermissionAction.DENY
    assert policy.action_for_tool("read_file", ToolCategory.READ) is PermissionAction.ALLOW


def test_sandbox_pins_shell_to_workspace_root(tmp_path) -> None:
    subdir = tmp_path / "inner"
    subdir.mkdir()
    context = ToolContext(tmp_path, sandbox=True)
    result = RunCommandTool().execute({"command": "(Get-Location).Path", "cwd": "inner"}, context)
    assert result.is_error is False
    assert result.output.strip().rstrip("\\/") == str(tmp_path).rstrip("\\/")
