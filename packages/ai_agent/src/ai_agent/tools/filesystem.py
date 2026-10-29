"""Filesystem tools for reading, creating, editing, and listing files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_agent.contracts import ToolCall, ToolCategory, ToolDefinition, ToolParameter, ToolResult
from ai_agent.tools.base import BaseTool, ToolContext


class ReadFileTool(BaseTool):
    """Tool for reading file content safely within the workspace."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_file",
            description=(
                "Read content from a file with optional line range (1-indexed). "
                "Omitting bounds returns the entire file and consumes conversation context. "
                "For large files, locate relevant symbols with grep_search first, then "
                "supply start_line and end_line for focused excerpts. "
                "Set line_numbers=False to obtain literal text for exact edit anchors."
            ),
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
                ToolParameter(
                    name="line_numbers",
                    type_name="boolean",
                    description=(
                        "Include line-number prefixes (default: True). False returns literal text."
                    ),
                    required=False,
                    default=True,
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

        if total_lines == 0 and start_line is None and end_line is None:
            return ToolResult(
                name="read_file",
                output="",
                metadata={"path": str(target_path), "lines_read": 0},
            )

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

        if e_idx < s_idx:
            return ToolResult(
                name="read_file",
                output=(
                    f"Error: end_line {e_idx} precedes start_line {s_idx}. "
                    f"Use a nonempty 1-indexed range within 1..{total_lines}, "
                    "or omit the optional line bounds."
                ),
                is_error=True,
            )

        selected_lines = lines[s_idx - 1 : e_idx]
        output = (
            "".join(f"{s_idx + i:4d} | {line}" for i, line in enumerate(selected_lines))
            if arguments.get("line_numbers", True)
            else "".join(selected_lines)
        )

        return ToolResult(
            name="read_file",
            output=output,
            metadata={"path": str(target_path), "lines_read": len(selected_lines)},
        )


class CreateFileTool(BaseTool):
    """Tool for creating a brand new file."""

    def approval_call(self, call: ToolCall) -> ToolCall | None:
        path = call.arguments.get("path")
        if not isinstance(path, str) or not path.strip():
            return None
        return ToolCall(call.name, call.arguments, call.call_id, approval_paths=(path,))

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
            size = target_path.stat().st_size
            return ToolResult(
                name="create_file",
                output=f"Successfully created file {raw_path} ({size} bytes).",
                metadata={"path": str(target_path), "bytes_written": size},
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                name="create_file",
                output=f"Error writing to file {raw_path!r}: {exc}",
                is_error=True,
            )


class EditFileTool(BaseTool):
    """Tool for targeted editing of an existing file via exact string replacement."""

    def approval_call(self, call: ToolCall) -> ToolCall | None:
        path = call.arguments.get("path")
        if not isinstance(path, str) or not path.strip():
            return None
        return ToolCall(call.name, call.arguments, call.call_id, approval_paths=(path,))

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="edit_file",
            description=(
                "Edit an existing file by replacing 'old_text' with 'new_text'. "
                "Both strings are literal file text: preserve indentation and do not add "
                "patch markers, read-output line numbers, or Markdown fences. "
                "To insert text without deleting the anchor, include old_text unchanged "
                "in new_text along with the added text. Retain existing content that "
                "the task requires unchanged. "
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
                    description="Literal replacement text, including its indentation; not a diff.",
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
                    "Read the current range with read_file(line_numbers=False), then "
                    "copy a unique literal anchor with exact indentation and characters."
                ),
                is_error=True,
            )
        if count > 1:
            return ToolResult(
                name="edit_file",
                output=(
                    f"Error: 'old_text' matches {count} occurrences in {raw_path}. "
                    "Read more surrounding context with read_file(line_numbers=False) "
                    "and provide a unique literal anchor."
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

        # Depth 0 or negative depth means nothing should be scanned.
        if max_depth <= 0:
            return ToolResult(
                name="list_dir",
                output="(empty directory)",
                metadata={"path": str(target_path), "count": 0},
            )

        entries: list[Path] = []

        # DFS stack: (current_path, depth_from_root)
        stack: list[tuple[Path, int]] = [(target_path, 0)]
        while stack:
            current, depth = stack.pop()
            try:
                for child in sorted(current.iterdir()):
                    # Skip hidden children or __pycache__ directories.
                    if child.name.startswith(".") or child.name == "__pycache__":
                        continue
                    # Ensure we stay inside the workspace.
                    if not context.is_within_workspace(child):
                        continue

                    rel = child.relative_to(target_path)
                    entries.append(rel)

                    # Recurse into directories if depth allows.
                    if (
                        child.is_dir()
                        and depth + 1 < max_depth
                        and not child.is_symlink()
                        and not child.is_junction()
                    ):
                        stack.append((child, depth + 1))
            except PermissionError:
                # Skip directories that cannot be accessed; continue traversal.
                pass

        # Retain the original global Path ordering across directory levels.
        entries.sort()

        lines = []
        for rel in entries:
            abs_path = target_path / rel
            prefix = "📁 " if abs_path.is_dir() else "📄 "
            indent = "  " * (len(rel.parts) - 1)
            lines.append(f"{indent}{prefix}{rel}")

        output = "\n".join(lines) if lines else "(empty directory)"
        return ToolResult(
            name="list_dir",
            output=output,
            metadata={"path": str(target_path), "count": len(entries)},
        )
