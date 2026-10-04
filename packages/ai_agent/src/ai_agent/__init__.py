"""Agentic tool registry, permissions, and execution loop for coding workflows."""

from __future__ import annotations

from ai_agent.authorization import (
    AuthorizationMethod,
    AuthorizationRegistry,
    AuthorizationState,
    CapabilityGrant,
    CredentialLocation,
    ServiceAuthorization,
)
from ai_agent.codex_authorization import (
    CODEX_SERVICE_ID,
    codex_authorization_from_status,
    codex_authorization_registry,
)
from ai_agent.contracts import (
    PermissionAction,
    ToolCall,
    ToolCategory,
    ToolDefinition,
    ToolParameter,
    ToolResult,
)
from ai_agent.loop import AgentLoop, AgentResult
from ai_agent.permissions import ApprovalPolicyPreset, PermissionManager, PermissionPolicy
from ai_agent.tools import (
    BaseTool,
    CreateFileTool,
    DelegateTaskTool,
    EditFileTool,
    FindFilesTool,
    GitDiffTool,
    GitStatusTool,
    GrepSearchTool,
    ListDirTool,
    ReadFileTool,
    RunCommandTool,
    ToolContext,
    ToolRegistry,
    coding_tools_with_delegation,
    default_coding_tools,
)

__all__ = [
    "AgentLoop",
    "AgentResult",
    "ApprovalPolicyPreset",
    "AuthorizationMethod",
    "AuthorizationRegistry",
    "AuthorizationState",
    "BaseTool",
    "CODEX_SERVICE_ID",
    "CapabilityGrant",
    "CreateFileTool",
    "DelegateTaskTool",
    "CredentialLocation",
    "EditFileTool",
    "FindFilesTool",
    "GitDiffTool",
    "GitStatusTool",
    "GrepSearchTool",
    "ListDirTool",
    "PermissionAction",
    "PermissionManager",
    "PermissionPolicy",
    "ReadFileTool",
    "RunCommandTool",
    "ServiceAuthorization",
    "ToolCall",
    "ToolCategory",
    "ToolContext",
    "ToolDefinition",
    "ToolParameter",
    "ToolRegistry",
    "coding_tools_with_delegation",
    "ToolResult",
    "default_coding_tools",
    "codex_authorization_from_status",
    "codex_authorization_registry",
]
