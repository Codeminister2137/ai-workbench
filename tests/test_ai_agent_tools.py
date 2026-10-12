from __future__ import annotations

from pathlib import Path

from ai_agent import (
    CreateFileTool,
    EditFileTool,
    FindFilesTool,
    GrepSearchTool,
    ReadFileTool,
    RunCommandTool,
    ToolCall,
    ToolContext,
    default_coding_tools,
)


def test_tool_context_path_resolution(tmp_path: Path) -> None:
    context = ToolContext(workspace_root=tmp_path)
    file_path = tmp_path / "sub" / "file.txt"

    assert context.resolve_path("sub/file.txt") == file_path.resolve()
    assert context.is_within_workspace("sub/file.txt") is True
    assert context.is_within_workspace(tmp_path.parent / "outside.txt") is False


def test_create_and_read_file_tool(tmp_path: Path) -> None:
    context = ToolContext(workspace_root=tmp_path)
    create_tool = CreateFileTool()
    read_tool = ReadFileTool()

    # Create file
    call = ToolCall(
        name="create_file",
        arguments={"path": "test.txt", "content": "line 1\nline 2\nline 3\n"},
        call_id="call-1",
    )
    res = create_tool.run(call, context)
    assert res.is_error is False
    assert res.call_id == "call-1"
    assert (tmp_path / "test.txt").read_text() == "line 1\nline 2\nline 3\n"

    # Read file lines 2 to 3
    read_call = ToolCall(
        name="read_file",
        arguments={"path": "test.txt", "start_line": 2, "end_line": 3},
        call_id="call-2",
    )
    read_res = read_tool.run(read_call, context)
    assert read_res.is_error is False
    assert "   2 | line 2" in read_res.output
    assert "   3 | line 3" in read_res.output


def test_read_file_literal_range_can_be_used_as_exact_edit_anchor(tmp_path: Path) -> None:
    context = ToolContext(workspace_root=tmp_path)
    target = tmp_path / "mod.py"
    original = "# header\ndef first():\n    return 1\n\ndef second():\n    return 1\n"
    target.write_text(original, encoding="utf-8")
    read_tool = ReadFileTool()
    raw = read_tool.run(
        ToolCall(
            name="read_file",
            arguments={"path": "mod.py", "start_line": 2, "end_line": 3, "line_numbers": False},
        ),
        context,
    )
    assert not raw.is_error
    assert raw.output == "def first():\n    return 1\n"
    assert raw.metadata == {"path": str(target.resolve()), "lines_read": 2}
    edited = EditFileTool().run(
        ToolCall(
            name="edit_file",
            arguments={
                "path": "mod.py",
                "old_text": raw.output,
                "new_text": "def first():\n    return 2\n",
            },
        ),
        context,
    )
    assert not edited.is_error
    assert target.read_text(encoding="utf-8") == original.replace("return 1", "return 2", 1)


def test_read_file_numbered_default_and_explicit_true_match(tmp_path: Path) -> None:
    context = ToolContext(workspace_root=tmp_path)
    (tmp_path / "mod.py").write_text("one\n    two", encoding="utf-8")
    tool = ReadFileTool()
    for extra in ({}, {"line_numbers": True}):
        result = tool.run(
            ToolCall(name="read_file", arguments={"path": "mod.py", **extra}), context
        )
        assert not result.is_error
        assert result.output == "   1 | one\n   2 |     two"
    parameter = next(item for item in tool.definition.parameters if item.name == "line_numbers")
    assert parameter.type_name == "boolean"
    assert parameter.default is True
    assert parameter.required is False


def test_read_file_refuses_empty_or_reversed_ranges(tmp_path: Path) -> None:
    context = ToolContext(workspace_root=tmp_path)
    target = tmp_path / "lines.txt"
    target.write_text("one\ntwo\nthree\n", encoding="utf-8")
    for start, end in ((1, 0), (2, 1), (1, -1)):
        for numbered in (True, False):
            result = ReadFileTool().run(
                ToolCall(
                    name="read_file",
                    arguments={
                        "path": "lines.txt",
                        "start_line": start,
                        "end_line": end,
                        "line_numbers": numbered,
                    },
                ),
                context,
            )
            assert result.is_error
            assert "nonempty 1-indexed range within 1..3" in result.output
            assert target.read_text(encoding="utf-8") == "one\ntwo\nthree\n"


def test_edit_file_tool_snippet_replacement(tmp_path: Path) -> None:
    context = ToolContext(workspace_root=tmp_path)
    edit_tool = EditFileTool()

    target = tmp_path / "mod.py"
    target.write_text("def hello():\n    return 'old'\n")

    call = ToolCall(
        name="edit_file",
        arguments={
            "path": "mod.py",
            "old_text": "return 'old'",
            "new_text": "return 'new'",
        },
    )
    res = edit_tool.run(call, context)
    assert res.is_error is False
    assert target.read_text() == "def hello():\n    return 'new'\n"


def test_edit_file_tool_fails_on_duplicate_old_text(tmp_path: Path) -> None:
    context = ToolContext(workspace_root=tmp_path)
    edit_tool = EditFileTool()

    target = tmp_path / "mod.py"
    target.write_text("val = 1\nval = 1\n")

    call = ToolCall(
        name="edit_file",
        arguments={
            "path": "mod.py",
            "old_text": "val = 1",
            "new_text": "val = 2",
        },
    )
    res = edit_tool.run(call, context)
    assert res.is_error is True
    assert "matches 2 occurrences" in res.output


def test_find_and_grep_tools(tmp_path: Path) -> None:
    context = ToolContext(workspace_root=tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def run():\n    print('TARGET_TOKEN')\n")
    (tmp_path / "src" / "other.txt").write_text("nothing here\n")

    find_tool = FindFilesTool()
    grep_tool = GrepSearchTool()

    # Find *.py
    find_res = find_tool.run(
        ToolCall(name="find_files", arguments={"pattern": "*.py"}),
        context,
    )
    assert find_res.is_error is False
    assert "src" in find_res.output
    assert "main.py" in find_res.output

    # Grep TARGET_TOKEN
    grep_res = grep_tool.run(
        ToolCall(name="grep_search", arguments={"query": "TARGET_TOKEN"}),
        context,
    )
    assert grep_res.is_error is False
    assert "main.py:2:" in grep_res.output


def test_run_command_tool(tmp_path: Path) -> None:
    context = ToolContext(workspace_root=tmp_path)
    shell_tool = RunCommandTool()

    call = ToolCall(
        name="run_command",
        arguments={"command": "echo hello_agent_cli"},
    )
    res = shell_tool.run(call, context)
    assert res.is_error is False
    assert "hello_agent_cli" in res.output


def test_default_coding_tools_and_json_schemas() -> None:
    registry = default_coding_tools()
    schemas = registry.export_json_schemas()

    names = [s["function"]["name"] for s in schemas]
    assert "read_file" in names
    assert "create_file" in names
    assert "edit_file" in names
    assert "list_dir" in names
    assert "find_files" in names
    assert "grep_search" in names
    assert "git_status" in names
    assert "git_diff" in names
    assert "run_command" in names
