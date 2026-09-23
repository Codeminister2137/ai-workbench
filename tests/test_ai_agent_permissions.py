from __future__ import annotations

from ai_agent import (
    CreateFileTool,
    PermissionAction,
    PermissionManager,
    PermissionPolicy,
    ReadFileTool,
    RunCommandTool,
    ToolCall,
    ToolCategory,
)


def test_permission_policy_presets() -> None:
    permissive = PermissionPolicy.permissive()
    assert permissive.action_for_category(ToolCategory.READ) is PermissionAction.ALLOW
    assert permissive.action_for_category(ToolCategory.WRITE) is PermissionAction.ALLOW
    assert permissive.action_for_category(ToolCategory.SHELL) is PermissionAction.ALLOW

    read_only = PermissionPolicy.read_only()
    assert read_only.action_for_category(ToolCategory.READ) is PermissionAction.ALLOW
    assert read_only.action_for_category(ToolCategory.WRITE) is PermissionAction.DENY
    assert read_only.action_for_category(ToolCategory.SHELL) is PermissionAction.DENY

    interactive = PermissionPolicy.interactive()
    assert interactive.action_for_category(ToolCategory.READ) is PermissionAction.ALLOW
    assert interactive.action_for_category(ToolCategory.WRITE) is PermissionAction.ASK_USER
    assert interactive.action_for_category(ToolCategory.SHELL) is PermissionAction.ASK_USER


def test_permission_manager_interactive_callback() -> None:
    read_tool = ReadFileTool()
    write_tool = CreateFileTool()
    shell_tool = RunCommandTool()

    decisions: list[tuple[str, ToolCategory]] = []

    def mock_approval(call: ToolCall, category: ToolCategory) -> bool:
        decisions.append((call.name, category))
        return call.name != "run_command"

    manager = PermissionManager(
        policy=PermissionPolicy.interactive(),
        approval_callback=mock_approval,
    )

    # Read is auto-allowed
    assert manager.check_and_authorize(read_tool, ToolCall(name="read_file", arguments={})) is True
    assert len(decisions) == 0

    # Write calls approval callback and returns True
    assert (
        manager.check_and_authorize(
            write_tool, ToolCall(name="create_file", arguments={"path": "a.txt"})
        )
        is True
    )
    assert len(decisions) == 1
    assert decisions[0] == ("create_file", ToolCategory.WRITE)

    # Shell calls approval callback and returns False
    assert (
        manager.check_and_authorize(
            shell_tool, ToolCall(name="run_command", arguments={"command": "rm -rf"})
        )
        is False
    )
    assert len(decisions) == 2
    assert decisions[1] == ("run_command", ToolCategory.SHELL)
