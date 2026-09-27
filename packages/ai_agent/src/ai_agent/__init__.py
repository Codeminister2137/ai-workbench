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
    EditFileTool,
    FindFilesTool,
    GrepSearchTool,
    ListDirTool,
    ReadFileTool,
    RunCommandTool,
    ToolContext,
    ToolRegistry,
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
    "CapabilityGrant",
    "CreateFileTool",
    "CredentialLocation",
    "EditFileTool",
    "FindFilesTool",
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
    "ToolResult",
    "default_coding_tools",
]
