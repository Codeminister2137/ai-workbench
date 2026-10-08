"""Filesystem containment and invalid-input behavior through real registries."""

import os
import subprocess

import pytest
from ai_agent import (
    CreateFileTool,
    EditFileTool,
    PermissionManager,
    PermissionPolicy,
    ToolCall,
    ToolContext,
)
from ai_agent.tools.base import ToolRegistry
from ai_agent.tools.search import FindFilesTool, GrepSearchTool


@pytest.mark.parametrize(
    "tool,arguments",
    [
        (CreateFileTool(), {"path": "keep.txt", "content": "replacement", "overwrite": "false"}),
        (CreateFileTool(), {"path": "keep.txt", "content": "replacement", "overwrite": 1}),
        (EditFileTool(), {"path": "keep.txt", "new_text": "replacement", "old_text": False}),
        (EditFileTool(), {"path": "keep.txt", "new_text": "replacement", "old_text": 0}),
        (EditFileTool(), {"path": "keep.txt", "new_text": "replacement", "old_text": None}),
    ],
)
def test_invalid_mutation_never_prompts_or_changes_file(tmp_path, tool, arguments):
    target = tmp_path / "keep.txt"
    target.write_text("original")
    approvals = []

    def approve(*args) -> bool:
        approvals.append(args)
        return True

    manager = PermissionManager(PermissionPolicy.interactive(), approve)
    call = ToolCall(tool.definition.name, arguments)
    assert not manager.check_and_authorize(tool, call)
    assert not approvals
    result = ToolRegistry((tool,)).execute(call, ToolContext(tmp_path))
    assert result.is_error
    assert target.read_text() == "original"


@pytest.mark.parametrize("link_kind", ["directory", "file"])
def test_search_never_returns_outside_link_contents(tmp_path, link_kind):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("OUTSIDE_MARKER")
    (workspace / "safe.txt").write_text("INSIDE_MARKER")
    link = workspace / "linked"
    junction = os.name == "nt" and link_kind == "directory"
    if junction:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "New-Item -ItemType Junction -Path $env:TEST_LINK "
                "-Target $env:TEST_TARGET | Out-Null",
            ],
            env={**os.environ, "TEST_LINK": str(link), "TEST_TARGET": str(outside)},
            check=True,
        )
    else:
        try:
            link.symlink_to(
                outside if link_kind == "directory" else secret,
                target_is_directory=link_kind == "directory",
            )
        except OSError as error:
            if os.name == "nt" and getattr(error, "winerror", None) == 1314:
                pytest.skip("Windows file symlinks require developer mode or privilege")
            raise
    try:
        registry = ToolRegistry((GrepSearchTool(), FindFilesTool()))
        context = ToolContext(workspace)
        grep = registry.execute(ToolCall("grep_search", {"query": "MARKER"}), context)
        assert not grep.is_error
        assert "INSIDE_MARKER" in grep.output
        assert "OUTSIDE_MARKER" not in grep.output
        find = registry.execute(ToolCall("find_files", {"pattern": "*"}), context)
        assert "secret.txt" not in find.output
        assert "linked" not in find.output
    finally:
        if junction:
            link.rmdir()
        else:
            link.unlink()
