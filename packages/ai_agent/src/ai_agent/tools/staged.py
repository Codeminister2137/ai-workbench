"""Staged file-write tools: agent edits that never touch disk directly.

``StageFileTool`` builds a staged record (via ``stage_file``) for owner
review through the run's staged flow. The record rides back in the tool
result metadata so the executor can attach it to the run; no disk write
happens here. Paths resolve against the tool context workspace, which
the executor binds to the run's project root.
"""

from __future__ import annotations

from typing import Any

from ai_agent.contracts import ToolCategory, ToolDefinition, ToolParameter, ToolResult
from ai_agent.staged_edits import StagedEditError, stage_file
from ai_agent.tools.base import BaseTool, ToolContext


class StageFileTool(BaseTool):
    """Stage a full-file write for owner review instead of writing it."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="stage_file",
            description=(
                "Stage a complete new file version for owner review. "
                "Use this for EVERY project file change instead of writing "
                "directly: staged files are reviewed and applied by the "
                "owner after the run. Provide the full intended content, "
                "not a diff."
            ),
            category=ToolCategory.WRITE,
            parameters=(
                ToolParameter(
                    name="relpath",
                    type_name="string",
                    description="Project-relative path (forward slashes).",
                    required=True,
                ),
                ToolParameter(
                    name="content",
                    type_name="string",
                    description="Full intended file content (UTF-8).",
                    required=True,
                ),
            ),
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        relpath = arguments.get("relpath")
        content = arguments.get("content")
        if not isinstance(relpath, str) or not relpath.strip():
            return ToolResult(
                name="stage_file",
                output="Error: 'relpath' parameter is required.",
                is_error=True,
            )
        if not isinstance(content, str):
            return ToolResult(
                name="stage_file",
                output="Error: 'content' parameter must be a string.",
                is_error=True,
            )
        try:
            record = stage_file(context.workspace_root, relpath, content)
        except StagedEditError as exc:
            return ToolResult(
                name="stage_file",
                output=f"Error: staging refused: {exc}",
                is_error=True,
            )
        label = "new file" if record["base_digest"] is None else "new version"
        return ToolResult(
            name="stage_file",
            output=f"Staged {label} for {relpath} (digest {record['digest'][:12]}).",
            metadata={"staged": record},
        )
