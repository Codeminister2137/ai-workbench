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
from ai_agent.tools.search import FindFilesTool, GrepSearchTool
from ai_agent.tools.shell import RunCommandTool


def default_coding_tools() -> ToolRegistry:
    """Create and return a registry populated with default coding and repo tools."""
    return ToolRegistry(
        tools=(
            ReadFileTool(),
            CreateFileTool(),
            EditFileTool(),
            ListDirTool(),
            FindFilesTool(),
            GrepSearchTool(),
            RunCommandTool(),
        )
    )


__all__ = [
    "BaseTool",
    "CreateFileTool",
    "DelegateTaskTool",
    "EditFileTool",
    "FindFilesTool",
    "GrepSearchTool",
    "ListDirTool",
    "ReadFileTool",
    "RunCommandTool",
    "ToolContext",
    "ToolRegistry",
    "coding_tools_with_delegation",
    "default_coding_tools",
]
