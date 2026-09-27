"""Permission policies and approval management for agent tool executions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from ai_agent.contracts import PermissionAction, ToolCall, ToolCategory
from ai_agent.tools.base import BaseTool

ApprovalCallback = Callable[[ToolCall, ToolCategory], bool]


class ApprovalPolicyPreset(StrEnum):
    """Named approval modes shared across model and executor implementations."""

    READ_ONLY = "read_only"
    INTERACTIVE = "interactive"
    WORKSPACE_WRITE = "workspace_write"
    TRUSTED_LOCAL = "trusted_local"


@dataclass(frozen=True, slots=True)
class PermissionPolicy:
    """Policy mapping each tool category to an approval requirement."""

    read_action: PermissionAction = PermissionAction.ALLOW
    search_action: PermissionAction = PermissionAction.ALLOW
    write_action: PermissionAction = PermissionAction.ASK_USER
    shell_action: PermissionAction = PermissionAction.ASK_USER
    custom_action: PermissionAction = PermissionAction.ASK_USER

    @classmethod
    def permissive(cls) -> PermissionPolicy:
        """Allow all tools to execute without asking."""
        return cls(
            read_action=PermissionAction.ALLOW,
            search_action=PermissionAction.ALLOW,
            write_action=PermissionAction.ALLOW,
            shell_action=PermissionAction.ALLOW,
            custom_action=PermissionAction.ALLOW,
        )

    @classmethod
    def read_only(cls) -> PermissionPolicy:
        """Deny all write and shell tools."""
        return cls(
            read_action=PermissionAction.ALLOW,
            search_action=PermissionAction.ALLOW,
            write_action=PermissionAction.DENY,
            shell_action=PermissionAction.DENY,
            custom_action=PermissionAction.DENY,
        )

    @classmethod
    def workspace_write(cls) -> PermissionPolicy:
        """Allow workspace reads/searches/writes, but ask before shell/custom tools."""
        return cls(
            read_action=PermissionAction.ALLOW,
            search_action=PermissionAction.ALLOW,
            write_action=PermissionAction.ALLOW,
            shell_action=PermissionAction.ASK_USER,
            custom_action=PermissionAction.ASK_USER,
        )

    @classmethod
    def interactive(cls) -> PermissionPolicy:
        """Allow reads and searches, ask for writes and shell commands."""
        return cls(
            read_action=PermissionAction.ALLOW,
            search_action=PermissionAction.ALLOW,
            write_action=PermissionAction.ASK_USER,
            shell_action=PermissionAction.ASK_USER,
            custom_action=PermissionAction.ASK_USER,
        )

    def action_for_category(self, category: ToolCategory) -> PermissionAction:
        """Return the policy action for a given tool category."""
        match category:
            case ToolCategory.READ:
                return self.read_action
            case ToolCategory.SEARCH:
                return self.search_action
            case ToolCategory.WRITE:
                return self.write_action
            case ToolCategory.SHELL:
                return self.shell_action
            case ToolCategory.CUSTOM:
                return self.custom_action

    @classmethod
    def from_approval_preset(cls, preset: ApprovalPolicyPreset | str) -> PermissionPolicy:
        """Return the permission policy for a named approval preset."""
        normalized = ApprovalPolicyPreset(preset)
        match normalized:
            case ApprovalPolicyPreset.READ_ONLY:
                return cls.read_only()
            case ApprovalPolicyPreset.INTERACTIVE:
                return cls.interactive()
            case ApprovalPolicyPreset.WORKSPACE_WRITE:
                return cls.workspace_write()
            case ApprovalPolicyPreset.TRUSTED_LOCAL:
                return cls.permissive()


@dataclass(slots=True)
class PermissionManager:
    """Manages evaluation and interactive approval of tool calls."""

    policy: PermissionPolicy = field(default_factory=PermissionPolicy.interactive)
    approval_callback: ApprovalCallback | None = None

    def check_and_authorize(self, tool: BaseTool, call: ToolCall) -> bool:
        """Check whether a tool call is authorized under the current policy."""
        category = tool.definition.category
        action = self.policy.action_for_category(category)

        if action is PermissionAction.ALLOW:
            return True
        if action is PermissionAction.DENY:
            return False

        # ASK_USER
        if self.approval_callback is not None:
            return self.approval_callback(call, category)
        # If no approval callback is registered, deny by default for safety
        return False
