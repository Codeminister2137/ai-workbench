"""Bounded, read-only Git inspection without an arbitrary shell command."""

from __future__ import annotations

import os
import subprocess
from typing import Any

from ai_agent.contracts import ToolCategory, ToolDefinition, ToolParameter, ToolResult
from ai_agent.tools.base import BaseTool, ToolContext

MAX_OUTPUT_CHARS = 30_000
GIT_TIMEOUT_SECONDS = 15.0


def _git_inspect(name: str, arguments: tuple[str, ...], context: ToolContext) -> ToolResult:
    """Run fixed Git arguments against a repository inside the workspace."""
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    env.update({"GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"})
    prefix = (
        "git",
        "--no-pager",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        "-c",
        "status.submoduleSummary=false",
        "-c",
        "diff.submodule=short",
        "-C",
        str(context.workspace_root.resolve()),
    )

    def run(args: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            (*prefix, *args),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
            env=env,
            check=False,
        )

    try:
        root = run(("rev-parse", "--show-toplevel"))
        if root.returncode != 0:
            return ToolResult(
                name=name, output="Error: workspace is not a Git working tree.", is_error=True
            )
        if not context.is_within_workspace(root.stdout.strip()):
            return ToolResult(
                name=name,
                is_error=True,
                output=(
                    "Error: Git repository root is outside the workspace. "
                    "Select its root explicitly."
                ),
            )
        configured_filters = run(
            ("config", "--null", "--name-only", "--get-regexp", r"^filter\..*\.(clean|process)$")
        )
        if configured_filters.returncode not in (0, 1):
            return ToolResult(
                name=name,
                output="Error: Git content filters could not be inspected.",
                is_error=True,
            )
        drivers = {key.rsplit(".", 1)[0] for key in configured_filters.stdout.split("\0") if key}
        if any("=" in driver for driver in drivers):
            return ToolResult(
                name=name,
                output="Error: Git filter names cannot be safely overridden for inspection.",
                is_error=True,
            )
        # Status/diff can run clean/process filters to compare worktree content.
        # Disable their commands for this invocation, without changing configuration.
        filter_options = tuple(
            argument
            for driver in sorted(drivers)
            for setting in ("clean=", "process=", "required=false")
            for argument in ("-c", f"{driver}.{setting}")
        )
        if sum(len(part) + 3 for part in (*prefix, *filter_options, *arguments)) > 30_000:
            return ToolResult(
                name=name,
                output="Error: Git filter overrides exceed the bounded command size.",
                is_error=True,
            )
        prefix = (*prefix, *filter_options)
        completed = run(arguments)
    except FileNotFoundError:
        return ToolResult(name=name, output="Error: Git executable was not found.", is_error=True)
    except subprocess.TimeoutExpired:
        return ToolResult(name=name, output="Error: Git inspection timed out.", is_error=True)
    raw = completed.stdout + ("\n[STDERR]\n" + completed.stderr if completed.stderr else "")
    truncated = len(raw) > MAX_OUTPUT_CHARS
    output = raw[:MAX_OUTPUT_CHARS].strip() or "(No changes)"
    if truncated:
        output += "\n[Git output truncated; narrow the diff path.]"
    if drivers:
        output = "[Content filters disabled; comparing raw worktree content.]\n" + output
    return ToolResult(
        name=name,
        output=output,
        is_error=completed.returncode != 0,
        metadata={
            "exit_code": completed.returncode,
            "truncated": truncated,
            "content_filters_disabled": bool(drivers),
        },
    )


class GitStatusTool(BaseTool):
    """Inspect tracked and ordinary untracked files without refreshing the index."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="git_status",
            category=ToolCategory.READ,
            description="Show workspace Git status without shell or remote operations.",
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        return _git_inspect(
            "git_status",
            ("status", "--porcelain=v1", "--untracked-files=normal", "--ignore-submodules=dirty"),
            context,
        )


class GitDiffTool(BaseTool):
    """Inspect staged or unstaged changes with external helpers disabled."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="git_diff",
            category=ToolCategory.READ,
            description="Show staged or unstaged Git diff, optionally narrowed to a path.",
            parameters=(
                ToolParameter(
                    "path", "string", "Optional workspace path to inspect.", required=False
                ),
                ToolParameter(
                    "staged",
                    "boolean",
                    "Inspect index changes instead of worktree changes.",
                    required=False,
                    default=False,
                ),
            ),
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        staged = arguments.get("staged", False)
        if not isinstance(staged, bool):
            return ToolResult(
                name="git_diff", output="Error: staged must be a boolean.", is_error=True
            )
        path = arguments.get("path")
        path_args: tuple[str, ...] = ()
        if path is not None:
            if not isinstance(path, str) or not path.strip():
                return ToolResult(
                    name="git_diff", output="Error: path must be a nonempty string.", is_error=True
                )
            if not context.is_within_workspace(path):
                return ToolResult(
                    name="git_diff", output="Error: diff path is outside workspace.", is_error=True
                )
            relative = context.resolve_path(path).relative_to(context.workspace_root.resolve())
            path_args = (":(literal)" + relative.as_posix(),)
        return _git_inspect(
            "git_diff",
            (
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--no-color",
                "--ignore-submodules=dirty",
                *(("--cached",) if staged else ()),
                "--",
                *path_args,
            ),
            context,
        )
