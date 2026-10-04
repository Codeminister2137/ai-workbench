"""Built-in common tool surfaces; profiles select tools without granting permissions."""

from dataclasses import dataclass

from ai_agent.tools import (
    FindFilesTool,
    GitDiffTool,
    GitStatusTool,
    GrepSearchTool,
    ListDirTool,
    ReadFileTool,
    ToolRegistry,
)


@dataclass(frozen=True)
class SharedToolProfile:
    name: str
    tool_names: tuple[str, ...]


INSPECTION_PROFILE = SharedToolProfile(
    "inspection", ("read_file", "list_dir", "find_files", "grep_search", "git_status", "git_diff")
)


def shared_tool_profile(name: str) -> SharedToolProfile:
    """Refuse unknown profiles rather than silently omit required capabilities."""
    if name != INSPECTION_PROFILE.name:
        raise ValueError(f"Unsupported shared tool profile: {name}")
    return INSPECTION_PROFILE


def shared_tool_registry(name: str) -> ToolRegistry:
    """Use the same implementations for provider-native execution and MCP."""
    shared_tool_profile(name)
    return ToolRegistry(
        tools=(
            ReadFileTool(),
            ListDirTool(),
            FindFilesTool(),
            GrepSearchTool(),
            GitStatusTool(),
            GitDiffTool(),
        )
    )
