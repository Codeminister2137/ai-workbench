"""Filesystem tools for reading, creating, editing, and listing files."""

from __future__ import annotations

from typing import Any

from ai_agent.contracts import ToolCategory, ToolDefinition, ToolParameter, ToolResult
from ai_agent.tools.base import BaseTool, ToolContext


class ReadFileTool(BaseTool):
    """Tool for reading file content safely within the workspace."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_file",
            description="Read content from a file with optional line range (1-indexed).",
            category=ToolCategory.READ,
            parameters=(
                ToolParameter(
                    name="path",
                    type_name="string",
                    description="Path to the file (relative to workspace or absolute).",
                    required=True,
                ),
                ToolParameter(
                    name="start_line",
                    type_name="integer",
                    description="Optional starting line number (1-indexed).",
                    required=False,
                ),
                ToolParameter(
                    name="end_line",
                    type_name="integer",
                    description="Optional ending line number (1-indexed, inclusive).",
                    required=False,
                ),
            ),
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        raw_path = arguments.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return ToolResult(
                name="read_file",
                output="Error: 'path' parameter is required.",
                is_error=True,
            )

        target_path = context.resolve_path(raw_path)
        if not context.is_within_workspace(target_path):
            return ToolResult(
                name="read_file",
                output=f"Error: Path {raw_path!r} is outside the allowed workspace boundary.",
                is_error=True,
            )

        if not target_path.exists():
            return ToolResult(
                name="read_file",
                output=f"Error: File {raw_path!r} does not exist.",
                is_error=True,
            )

        if not target_path.is_file():
            return ToolResult(
                name="read_file",
                output=f"Error: Path {raw_path!r} is a directory, not a file.",
                is_error=True,
            )

        try:
            content = target_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                name="read_file",
                output=f"Error reading file {raw_path!r}: {exc}",
                is_error=True,
            )

        lines = content.splitlines(keepends=True)
        total_lines = len(lines)

        start_line = arguments.get("start_line")
        end_line = arguments.get("end_line")

        s_idx = max(1, int(start_line)) if isinstance(start_line, (int, float)) else 1
        e_idx = (
            min(total_lines, int(end_line)) if isinstance(end_line, (int, float)) else total_lines
        )

        if s_idx > total_lines:
            return ToolResult(
                name="read_file",
                output=f"Error: start_line {s_idx} is beyond total lines ({total_lines}).",
                is_error=True,
            )

        selected_lines = lines[s_idx - 1 : e_idx]
        indexed_output = "".join(
            f"{s_idx + i:4d} | {line}" for i, line in enumerate(selected_lines)
        )

        return ToolResult(
            name="read_file",
            output=indexed_output,
            metadata={"path": str(target_path), "lines_read": len(selected_lines)},
        )


class CreateFileTool(BaseTool):
    """Tool for creating a brand new file."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="create_file",
            description=(
                "Create a new file with specified content. Fails if file exists unless "
                "overwrite is True."
            ),
            category=ToolCategory.WRITE,
            parameters=(
                ToolParameter(
                    name="path",
                    type_name="string",
                    description="Path to the file to create.",
                    required=True,
                ),
                ToolParameter(
                    name="content",
                    type_name="string",
                    description="Content to write into the file.",
                    required=True,
                ),
                ToolParameter(
                    name="overwrite",
                    type_name="boolean",
                    description="Whether to overwrite if file exists (default: False).",
                    required=False,
                    default=False,
                ),
            ),
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        raw_path = arguments.get("path")
        content = arguments.get("content")
        overwrite = bool(arguments.get("overwrite", False))

        if not isinstance(raw_path, str) or not raw_path.strip():
            return ToolResult(
                name="create_file",
                output="Error: 'path' parameter is required.",
                is_error=True,
            )
        if not isinstance(content, str):
            return ToolResult(
                name="create_file",
                output="Error: 'content' parameter is required.",
                is_error=True,
            )

        target_path = context.resolve_path(raw_path)
        if not context.is_within_workspace(target_path):
            return ToolResult(
                name="create_file",
                output=f"Error: Path {raw_path!r} is outside the allowed workspace boundary.",
                is_error=True,
            )

        if target_path.exists() and not overwrite:
            return ToolResult(
                name="create_file",
                output=f"Error: File {raw_path!r} already exists. Set overwrite=True to replace.",
                is_error=True,
            )

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")
            return ToolResult(
                name="create_file",
                output=f"Successfully created file {raw_path} ({len(content)} bytes).",
                metadata={"path": str(target_path), "bytes_written": len(content)},
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                name="create_file",
                output=f"Error writing to file {raw_path!r}: {exc}",
                is_error=True,
            )


class EditFileTool(BaseTool):
    """Tool for targeted editing of an existing file via exact string replacement."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="edit_file",
            description=(
                "Edit an existing file by replacing 'old_text' with 'new_text'. "
                "If old_text is omitted or empty, replaces full file content."
            ),
            category=ToolCategory.WRITE,
            parameters=(
                ToolParameter(
                    name="path",
                    type_name="string",
                    description="Path to the file to edit.",
                    required=True,
                ),
                ToolParameter(
                    name="new_text",
                    type_name="string",
                    description="The new text to insert.",
                    required=True,
                ),
                ToolParameter(
                    name="old_text",
                    type_name="string",
                    description="The snippet of existing code to replace. Must match uniquely.",
                    required=False,
                ),
            ),
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        raw_path = arguments.get("path")
        new_text = arguments.get("new_text")
        old_text = arguments.get("old_text")

        if not isinstance(raw_path, str) or not raw_path.strip():
            return ToolResult(
                name="edit_file",
                output="Error: 'path' parameter is required.",
                is_error=True,
            )
        if not isinstance(new_text, str):
            return ToolResult(
                name="edit_file",
                output="Error: 'new_text' parameter is required.",
                is_error=True,
            )

        target_path = context.resolve_path(raw_path)
        if not context.is_within_workspace(target_path):
            return ToolResult(
                name="edit_file",
                output=f"Error: Path {raw_path!r} is outside the allowed workspace boundary.",
                is_error=True,
            )

        if not target_path.is_file():
            return ToolResult(
                name="edit_file",
                output=f"Error: File {raw_path!r} does not exist.",
                is_error=True,
            )

        try:
            current_content = target_path.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                name="edit_file",
                output=f"Error reading file {raw_path!r}: {exc}",
                is_error=True,
            )

        if not old_text:
            # Full file replacement
            target_path.write_text(new_text, encoding="utf-8")
            return ToolResult(
                name="edit_file",
                output=f"Successfully updated entire content of {raw_path}.",
                metadata={"path": str(target_path), "mode": "full_replace"},
            )

        count = current_content.count(old_text)
        if count == 0:
            return ToolResult(
                name="edit_file",
                output=(
                    f"Error: 'old_text' was not found in {raw_path}. "
                    "Ensure exact indentation and characters match."
                ),
                is_error=True,
            )
        if count > 1:
            return ToolResult(
                name="edit_file",
                output=(
                    f"Error: 'old_text' matches {count} occurrences in {raw_path}. "
                    "Provide more surrounding context to make it unique."
                ),
                is_error=True,
            )

        updated_content = current_content.replace(old_text, new_text, 1)
        target_path.write_text(updated_content, encoding="utf-8")
        return ToolResult(
            name="edit_file",
            output=f"Successfully edited {raw_path}.",
            metadata={"path": str(target_path), "mode": "snippet_replace"},
        )


class ListDirTool(BaseTool):
    """Tool for listing directory entries up to a specified depth."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="list_dir",
            description="List files and directories within a directory up to max_depth.",
            category=ToolCategory.READ,
            parameters=(
                ToolParameter(
                    name="path",
                    type_name="string",
                    description="Directory path (default: workspace root).",
                    required=False,
                    default=".",
                ),
                ToolParameter(
                    name="max_depth",
                    type_name="integer",
                    description="Maximum traversal depth (default: 2).",
                    required=False,
                    default=2,
                ),
            ),
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        raw_path = arguments.get("path", ".")
        max_depth = int(arguments.get("max_depth", 2))

        target_path = context.resolve_path(raw_path)
        if not context.is_within_workspace(target_path):
            return ToolResult(
                name="list_dir",
                output=f"Error: Path {raw_path!r} is outside the allowed workspace boundary.",
                is_error=True,
            )

        if not target_path.exists() or not target_path.is_dir():
            return ToolResult(
                name="list_dir",
                output=f"Error: Directory {raw_path!r} does not exist.",
                is_error=True,
            )

        entries: list[str] = []
        base_depth = len(target_path.parts)

        for item in sorted(target_path.rglob("*")):
            # Skip hidden dirs like .git, .venv, __pycache__
            if any(part.startswith(".") or part == "__pycache__" for part in item.parts):
                continue
            item_depth = len(item.parts) - base_depth
            if item_depth > max_depth:
                continue

            rel_path = item.relative_to(target_path)
            prefix = "📁 " if item.is_dir() else "📄 "
            indent = "  " * (item_depth - 1)
            entries.append(f"{indent}{prefix}{rel_path}")

        return ToolResult(
            name="list_dir",
            output="\n".join(entries) if entries else "(empty directory)",
            metadata={"path": str(target_path), "count": len(entries)},
        )
