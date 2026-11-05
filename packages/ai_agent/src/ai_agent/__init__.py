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
from ai_agent.completion import CompletionRequirement
from ai_agent.contracts import (
    PermissionAction,
    ToolCall,
    ToolCategory,
    ToolDefinition,
    ToolParameter,
    ToolResult,
)
from ai_agent.delegation_runner import build_child_runner
from ai_agent.loop import AgentLoop, AgentResult, ToolExecutionEvent
from ai_agent.permissions import ApprovalPolicyPreset, PermissionManager, PermissionPolicy
from ai_agent.recovery import RecoveryState
from ai_agent.supervisor_drain import RunDrain, TerminalHook
from ai_agent.supervisor_threads import SupervisorThreads
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
    OwnerTaskTool,
    ReadFileTool,
    RunCommandTool,
    StageFileTool,
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
    "CompletionRequirement",
    "CreateFileTool",
    "DelegateTaskTool",
    "CredentialLocation",
    "EditFileTool",
    "FindFilesTool",
    "GitDiffTool",
    "GitStatusTool",
    "GrepSearchTool",
    "ListDirTool",
    "OwnerTaskTool",
    "PermissionAction",
    "PermissionManager",
    "PermissionPolicy",
    "ReadFileTool",
    "RecoveryState",
    "RunCommandTool",
    "RunDrain",
    "StageFileTool",
    "TerminalHook",
    "build_child_runner",
    "ServiceAuthorization",
    "SupervisorThreads",
    "ToolCall",
    "ToolCategory",
    "ToolContext",
    "ToolDefinition",
    "ToolExecutionEvent",
    "ToolParameter",
    "ToolRegistry",
    "coding_tools_with_delegation",
    "ToolResult",
    "default_coding_tools",
    "codex_authorization_from_status",
    "codex_authorization_registry",
]
