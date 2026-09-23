"""Search tools for file patterns and code content."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any

from ai_agent.contracts import ToolCategory, ToolDefinition, ToolParameter, ToolResult
from ai_agent.tools.base import BaseTool, ToolContext


class FindFilesTool(BaseTool):
    """Tool for locating files by glob pattern."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="find_files",
            description="Find files matching a glob pattern (e.g. '*.py' or '*catalog*').",
            category=ToolCategory.SEARCH,
            parameters=(
                ToolParameter(
                    name="pattern",
                    type_name="string",
                    description="Glob pattern to search for.",
                    required=True,
                ),
                ToolParameter(
                    name="path",
                    type_name="string",
                    description="Base directory to search in (default: workspace root).",
                    required=False,
                    default=".",
                ),
                ToolParameter(
                    name="max_results",
                    type_name="integer",
                    description="Maximum number of matches to return (default: 50).",
                    required=False,
                    default=50,
                ),
            ),
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        pattern = arguments.get("pattern")
        raw_path = arguments.get("path", ".")
        max_results = int(arguments.get("max_results", 50))

        if not isinstance(pattern, str) or not pattern.strip():
            return ToolResult(
                name="find_files",
                output="Error: 'pattern' parameter is required.",
                is_error=True,
            )

        target_path = context.resolve_path(raw_path)
        if not context.is_within_workspace(target_path):
            return ToolResult(
                name="find_files",
                output=f"Error: Path {raw_path!r} is outside the allowed workspace boundary.",
                is_error=True,
            )

        if not target_path.exists():
            return ToolResult(
                name="find_files",
                output=f"Error: Directory {raw_path!r} does not exist.",
                is_error=True,
            )

        matches: list[str] = []
        for item in target_path.rglob("*"):
            if any(part.startswith(".") or part == "__pycache__" for part in item.parts):
                continue
            if fnmatch.fnmatch(item.name, pattern):
                try:
                    rel = item.relative_to(context.workspace_root)
                    matches.append(str(rel))
                except ValueError:
                    matches.append(str(item))

            if len(matches) >= max_results:
                break

        if not matches:
            return ToolResult(
                name="find_files",
                output=f"No files matching pattern {pattern!r} found in {raw_path}.",
                metadata={"pattern": pattern, "count": 0},
            )

        return ToolResult(
            name="find_files",
            output="\n".join(matches),
            metadata={"pattern": pattern, "count": len(matches)},
        )


class GrepSearchTool(BaseTool):
    """Tool for searching code content using regular expressions or text matching."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="grep_search",
            description="Search for exact text or regex patterns across workspace files.",
            category=ToolCategory.SEARCH,
            parameters=(
                ToolParameter(
                    name="query",
                    type_name="string",
                    description="Search query or regex pattern.",
                    required=True,
                ),
                ToolParameter(
                    name="path",
                    type_name="string",
                    description="Directory or file path to search in (default: workspace root).",
                    required=False,
                    default=".",
                ),
                ToolParameter(
                    name="is_regex",
                    type_name="boolean",
                    description="Whether to treat query as regex (default: False).",
                    required=False,
                    default=False,
                ),
                ToolParameter(
                    name="max_matches",
                    type_name="integer",
                    description="Maximum total line matches to return (default: 50).",
                    required=False,
                    default=50,
                ),
            ),
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        query = arguments.get("query")
        raw_path = arguments.get("path", ".")
        is_regex = bool(arguments.get("is_regex", False))
        max_matches = int(arguments.get("max_matches", 50))

        if not isinstance(query, str) or not query:
            return ToolResult(
                name="grep_search",
                output="Error: 'query' parameter is required.",
                is_error=True,
            )

        target_path = context.resolve_path(raw_path)
        if not context.is_within_workspace(target_path):
            return ToolResult(
                name="grep_search",
                output=f"Error: Path {raw_path!r} is outside the allowed workspace boundary.",
                is_error=True,
            )

        if not target_path.exists():
            return ToolResult(
                name="grep_search",
                output=f"Error: Path {raw_path!r} does not exist.",
                is_error=True,
            )

        try:
            regex = (
                re.compile(query, re.IGNORECASE)
                if is_regex
                else re.compile(re.escape(query), re.IGNORECASE)
            )
        except re.error as exc:
            return ToolResult(
                name="grep_search",
                output=f"Error: Invalid regular expression {query!r}: {exc}",
                is_error=True,
            )

        files_to_search: list[Path] = []
        if target_path.is_file():
            files_to_search.append(target_path)
        else:
            for p in target_path.rglob("*"):
                if p.is_file() and not any(
                    part.startswith(".") or part == "__pycache__" for part in p.parts
                ):
                    files_to_search.append(p)

        results: list[str] = []
        match_count = 0

        for file_path in files_to_search:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:  # noqa: BLE001
                continue

            try:
                rel_path = file_path.relative_to(context.workspace_root)
            except ValueError:
                rel_path = file_path

            for line_no, line in enumerate(content.splitlines(), start=1):
                if regex.search(line):
                    results.append(f"{rel_path}:{line_no}: {line.strip()}")
                    match_count += 1
                    if match_count >= max_matches:
                        break
            if match_count >= max_matches:
                break

        if not results:
            return ToolResult(
                name="grep_search",
                output=f"No matches found for query {query!r}.",
                metadata={"query": query, "matches": 0},
            )

        return ToolResult(
            name="grep_search",
            output="\n".join(results),
            metadata={"query": query, "matches": match_count},
        )
