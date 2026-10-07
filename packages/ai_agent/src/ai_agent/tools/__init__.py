"""Built-in coding and execution tools for agent workflows."""

from __future__ import annotations

from ai_agent.tools.base import BaseTool, ToolContext, ToolRegistry
from ai_agent.tools.delegation import DelegateTaskTool, coding_tools_with_delegation
from ai_agent.tools.filesystem import (
    CreateFileTool,
    EditFileTool,
    ListDirTool,
    ReadFileTool,
)
from ai_agent.tools.git import GitDiffTool, GitStatusTool
from ai_agent.tools.python_runtime import PythonRuntimeTool
from ai_agent.tools.refactor import (
    PythonNavigateTool,
    RenameApplyTool,
    RenamePlanStore,
    RenamePreviewTool,
)
from ai_agent.tools.search import FindFilesTool, GrepSearchTool
from ai_agent.tools.shell import RunCommandTool


def default_coding_tools(*, rename_plans: RenamePlanStore | None = None) -> ToolRegistry:
    """Create and return a registry populated with default coding and repo tools."""
    plans = rename_plans or RenamePlanStore()
    return ToolRegistry(
        tools=(
            ReadFileTool(),
            CreateFileTool(),
            EditFileTool(),
            ListDirTool(),
            FindFilesTool(),
            GrepSearchTool(),
            GitStatusTool(),
            GitDiffTool(),
            RunCommandTool(),
            PythonRuntimeTool(),
            PythonNavigateTool(),
            RenamePreviewTool(plans),
            RenameApplyTool(plans),
        )
    )


__all__ = [
    "BaseTool",
    "CreateFileTool",
    "DelegateTaskTool",
    "EditFileTool",
    "FindFilesTool",
    "GrepSearchTool",
    "GitDiffTool",
    "GitStatusTool",
    "ListDirTool",
    "ReadFileTool",
    "PythonRuntimeTool",
    "PythonNavigateTool",
    "RenameApplyTool",
    "RenamePlanStore",
    "RenamePreviewTool",
    "RunCommandTool",
    "ToolContext",
    "ToolRegistry",
    "coding_tools_with_delegation",
    "default_coding_tools",
]
