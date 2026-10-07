"""Built-in common tool surfaces; profiles select tools without granting permissions."""

from dataclasses import dataclass
from pathlib import Path

from ai_agent.tools import (
    CreateFileTool,
    EditFileTool,
    FindFilesTool,
    GitDiffTool,
    GitStatusTool,
    GrepSearchTool,
    ListDirTool,
    PythonNavigateTool,
    PythonRuntimeTool,
    ReadFileTool,
    RenameApplyTool,
    RenamePlanStore,
    RenamePreviewTool,
    RunCommandTool,
    ToolRegistry,
)


@dataclass(frozen=True)
class SharedToolProfile:
    name: str
    tool_names: tuple[str, ...]


INSPECTION_PROFILE = SharedToolProfile(
    "inspection", ("read_file", "list_dir", "find_files", "grep_search", "git_status", "git_diff")
)
CODING_PROFILE = SharedToolProfile(
    "coding",
    (
        *INSPECTION_PROFILE.tool_names,
        "create_file",
        "edit_file",
        "run_command",
        "fetch_url",
        "python_runtime",
        "python_navigate",
        "rename_preview",
        "rename_apply",
    ),
)


def shared_tool_profile(name: str) -> SharedToolProfile:
    """Refuse unknown profiles rather than silently omit required capabilities."""
    for profile in (INSPECTION_PROFILE, CODING_PROFILE):
        if name == profile.name:
            return profile
    raise ValueError(f"Unsupported shared tool profile: {name}")


def shared_tool_registry(
    name: str,
    workspace: Path | None = None,
    *,
    rename_plans: RenamePlanStore | None = None,
) -> ToolRegistry:
    """Use the same implementations for provider-native execution and MCP."""
    shared_tool_profile(name)
    registry = ToolRegistry(
        tools=(
            ReadFileTool(),
            ListDirTool(),
            FindFilesTool(),
            GrepSearchTool(),
            GitStatusTool(),
            GitDiffTool(),
        )
    )
    if name == "coding":
        from ai_agent.tools.research import FetchURLTool

        for tool in (CreateFileTool(), EditFileTool(), RunCommandTool()):
            registry.register(tool)
        # Provenance is returned to the caller. Coding-session storage keeps the
        # ordinary hashed tool receipt, not fetched text or a separate research log.
        registry.register(FetchURLTool(lambda _event, _receipt: None))
        registry.register(PythonRuntimeTool())
        registry.register(PythonNavigateTool())
        plans = rename_plans or RenamePlanStore(workspace)
        registry.register(RenamePreviewTool(plans))
        registry.register(RenameApplyTool(plans))
    if workspace is not None:
        from ai_agent.ide_bridge import add_ide_tools

        add_ide_tools(registry, workspace)
    return registry
