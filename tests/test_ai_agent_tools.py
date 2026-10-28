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


def test_search_skips_sqlite_bytes_and_invalid_utf8_without_losing_unicode(tmp_path):
    import sqlite3

    with sqlite3.connect(tmp_path / "runtime.sqlite3") as connection:
        connection.execute("CREATE TABLE messages(content TEXT)")
        connection.execute("INSERT INTO messages VALUES (?)", ("TARGET_TOKEN runtime payload",))
    (tmp_path / "invalid.dat").write_bytes(b"TARGET_\xffTOKEN fabricated\n")
    (tmp_path / "code.py").write_text("# TARGET_TOKEN caf\u00e9\n", encoding="utf-8")
    result = GrepSearchTool().run(
        ToolCall("grep_search", {"query": "TARGET_TOKEN"}), ToolContext(tmp_path)
    )
    assert not result.is_error
    assert "code.py:1: # TARGET_TOKEN caf\u00e9" in result.output
    assert "runtime.sqlite3" not in result.output and "invalid.dat" not in result.output
    assert result.metadata["matches"] == 1


def test_find_files_recursive_glob_matches_root_and_nested_files_relative_to_base(tmp_path):
    base = tmp_path / "project"
    nested = base / "nested"
    nested.mkdir(parents=True)
    for path in (base / "test_root.py", nested / "test_child.py", tmp_path / "test_outside.py"):
        path.write_text("", encoding="utf-8")
    result = FindFilesTool().run(
        ToolCall("find_files", {"pattern": "**/test_*.py", "path": "project"}),
        ToolContext(tmp_path),
    )
    assert not result.is_error and result.metadata["count"] == 2
    assert "test_root.py" in result.output and "test_child.py" in result.output
    assert "test_outside.py" not in result.output


def test_grep_reports_editor_line_numbers_with_non_newline_separators(tmp_path: Path) -> None:
    # Form feed, U+2028 and CRLF must not shift the reported line numbers the way
    # str.splitlines would; only "\n" ends a line here.
    (tmp_path / "page.py").write_bytes(
        "first\n\x0csecond\u2028third\r\nTARGET_TOKEN\nlast".encode()
    )
    result = GrepSearchTool().run(
        ToolCall("grep_search", {"query": "TARGET_TOKEN"}), ToolContext(tmp_path)
    )
    assert not result.is_error and result.metadata["matches"] == 1
    assert result.output == "page.py:3: TARGET_TOKEN"


def test_search_tools_return_nothing_for_non_positive_limits(tmp_path: Path) -> None:
    (tmp_path / "code.py").write_text("TARGET_TOKEN\n", encoding="utf-8")
    context = ToolContext(tmp_path)
    for limit in (0, -1):
        grep = GrepSearchTool().run(
            ToolCall("grep_search", {"query": "TARGET_TOKEN", "max_matches": limit}), context
        )
        assert not grep.is_error
        assert grep.metadata["matches"] == 0 and "code.py" not in grep.output
        found = FindFilesTool().run(
            ToolCall("find_files", {"pattern": "*.py", "max_results": limit}), context
        )
        assert not found.is_error
        assert found.metadata["count"] == 0 and "code.py" not in found.output


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


def test_shell_preserves_output_and_empty_success(tmp_path, monkeypatch):
    import subprocess

    from ai_agent.tools import shell

    def runner(arguments, **kwargs):
        assert kwargs["cwd"] == tmp_path
        assert kwargs["env"]["SHELL_OVERRIDE"] == "context"
        assert kwargs["env"]["SHELL_INHERITED"] == "parent"
        return subprocess.CompletedProcess(arguments, 9, " out\r\nnext \r", " err \n")

    monkeypatch.setenv("SHELL_OVERRIDE", "parent")
    monkeypatch.setenv("SHELL_INHERITED", "parent")
    monkeypatch.setattr(shell, "run_validation_process", runner)
    result = RunCommandTool().execute(
        {"command": "synthetic"}, ToolContext(tmp_path, env={"SHELL_OVERRIDE": "context"})
    )
    assert result.is_error
    assert result.output == "out\nnext\n\n[STDERR]\nerr\n\n[Process exited with code 9]"
    assert result.metadata == {"command": "synthetic", "exit_code": 9, "cwd": str(tmp_path)}
    monkeypatch.setattr(
        shell,
        "run_validation_process",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "", ""),
    )
    empty = RunCommandTool().execute({"command": "synthetic"}, ToolContext(tmp_path))
    assert not empty.is_error
    assert empty.output == "(No output)"


def test_shell_timeout_progress_is_bounded_and_does_not_render_arguments(tmp_path, monkeypatch):
    import subprocess

    from ai_agent.tools import shell

    def runner(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            ["private-command-argument"],
            1,
            output=b"x" * 20_000 + b"progress",
            stderr="diagnostic",
        )

    monkeypatch.setattr(shell, "run_validation_process", runner)
    result = RunCommandTool().execute(
        {"command": "synthetic", "timeout_seconds": 1}, ToolContext(tmp_path)
    )
    assert result.is_error
    assert len(result.output) < 16_200
    assert "progress" in result.output
    assert "[STDERR]\ndiagnostic" in result.output
    assert "timed out after 1.0 seconds" in result.output
    assert "private-command-argument" not in result.output


def test_shell_interrupt_propagates_and_start_error_hides_command(tmp_path, monkeypatch):
    import pytest
    from ai_agent.tools import shell

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(shell, "run_validation_process", interrupt)
    with pytest.raises(KeyboardInterrupt):
        RunCommandTool().execute({"command": "synthetic"}, ToolContext(tmp_path))

    def failed_start(*args, **kwargs):
        raise OSError("private-command-argument")

    monkeypatch.setattr(shell, "run_validation_process", failed_start)
    result = RunCommandTool().execute({"command": "synthetic"}, ToolContext(tmp_path))
    assert result.is_error
    assert "OSError" in result.output
    assert "private-command-argument" not in result.output


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


def test_create_file_unicode_bytes_count(tmp_path: Path) -> None:
    context = ToolContext(workspace_root=tmp_path)
    create_tool = CreateFileTool()
    content = "αβγ"
    call = ToolCall(
        name="create_file",
        arguments={"path": "unic.txt", "content": content},
        call_id="call-1",
    )
    res = create_tool.run(call, context)
    assert not res.is_error
    expected_bytes = len(content.encode("utf-8"))
    assert res.metadata["bytes_written"] == expected_bytes
    assert f"({expected_bytes} bytes)" in res.output
    actual_size = (tmp_path / "unic.txt").stat().st_size
    assert actual_size == expected_bytes


def test_create_file_overwrite_count(tmp_path: Path) -> None:
    context = ToolContext(workspace_root=tmp_path)
    create_tool = CreateFileTool()
    # initial file
    init_content = "line1\nline2"
    call_init = ToolCall(
        name="create_file",
        arguments={"path": "over.txt", "content": init_content},
        call_id="init-call",
    )
    res_init = create_tool.run(call_init, context)
    assert not res_init.is_error
    # overwrite with different content
    new_content = "new"
    call_over = ToolCall(
        name="create_file",
        arguments={"path": "over.txt", "content": new_content, "overwrite": True},
        call_id="over-call",
    )
    res_over = create_tool.run(call_over, context)
    assert not res_over.is_error
    expected_bytes_new = len(new_content.encode("utf-8"))
    assert res_over.metadata["bytes_written"] == expected_bytes_new
    assert (tmp_path / "over.txt").stat().st_size == expected_bytes_new
    assert (tmp_path / "over.txt").read_text() == new_content


def test_unicode_crlf_and_absent_final_newline(tmp_path: Path) -> None:
    """Verify that a literal range can be used as an edit anchor even with
    Unicode characters, indentation, CRLF line endings and no trailing newline.
    The resulting file should preserve surrounding content and the absence of
    a final newline."""
    # Construct content with CRLF and no trailing newline
    content = "αβγ\r\n    def foo():\r\n        return 1"
    target = tmp_path / "mod.py"
    target.write_bytes(content.encode("utf-8"))

    ctx = ToolContext(workspace_root=tmp_path)
    read_tool = ReadFileTool()
    # Read a literal range that will serve as the edit anchor
    read_res = read_tool.run(
        ToolCall(
            name="read_file",
            arguments={"path": "mod.py", "start_line": 2, "end_line": 3, "line_numbers": False},
        ),
        ctx,
    )
    assert not read_res.is_error
    anchor = read_res.output
    expected_anchor = "    def foo():\n        return 1"
    assert anchor == expected_anchor

    # Edit the anchor: change indentation of second line
    edit_tool = EditFileTool()
    new_text = "    def foo():\n            return 2"  # increased indentation on return line
    edit_res = edit_tool.run(
        ToolCall(
            name="edit_file", arguments={"path": "mod.py", "old_text": anchor, "new_text": new_text}
        ),
        ctx,
    )
    assert not edit_res.is_error

    expected_final = "αβγ\n    def foo():\n            return 2"
    actual = target.read_text(encoding="utf-8")
    assert actual == expected_final


def test_literal_mode_refusals_and_schema_validation(tmp_path: Path) -> None:
    """Verify that read_file rejects missing/invalid inputs and that schema
    validation works for the boolean ``line_numbers`` parameter."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ctx = ToolContext(workspace_root=workspace)
    read_tool = ReadFileTool()

    # Missing file
    res_missing = read_tool.run(
        ToolCall(name="read_file", arguments={"path": "does_not_exist.txt", "line_numbers": False}),
        ctx,
    )
    assert res_missing.is_error
    assert "does_not_exist.txt" in res_missing.output

    # Directory path
    dir_path = workspace / "dir"
    dir_path.mkdir()
    res_dir = read_tool.run(
        ToolCall(name="read_file", arguments={"path": str(dir_path), "line_numbers": False}),
        ctx,
    )
    assert res_dir.is_error
    assert "is a directory" in res_dir.output

    # Outside workspace
    outside = tmp_path / "outside.txt"
    outside.write_text("x")
    res_outside = read_tool.run(
        ToolCall(name="read_file", arguments={"path": str(outside), "line_numbers": False}),
        ctx,
    )
    assert res_outside.is_error
    assert "outside.txt" in res_outside.output

    # Out-of-bounds start line
    target = workspace / "file.txt"
    target.write_text("one\ntwo\nthree", encoding="utf-8")
    res_oob_start = read_tool.run(
        ToolCall(
            name="read_file",
            arguments={"path": "file.txt", "start_line": 5, "end_line": 6, "line_numbers": False},
        ),
        ctx,
    )
    assert res_oob_start.is_error
    assert "beyond total lines" in res_oob_start.output

    # Reversed range
    res_reversed = read_tool.run(
        ToolCall(
            name="read_file",
            arguments={"path": "file.txt", "start_line": 3, "end_line": 2, "line_numbers": False},
        ),
        ctx,
    )
    assert res_reversed.is_error
    assert "precedes start_line" in res_reversed.output

    # Boolean schema validation: pass invalid type for line_numbers via registry.execute
    registry = default_coding_tools()
    bad_call = ToolCall(name="read_file", arguments={"path": "file.txt", "line_numbers": "yes"})
    exec_res = registry.execute(bad_call, ctx)
    assert exec_res.is_error
    assert "Parameter line_numbers must be boolean" in exec_res.output


# New regression tests for newline and overwrite byte count


def test_create_file_newline_byte_count(tmp_path: Path) -> None:
    context = ToolContext(workspace_root=tmp_path)
    create_tool = CreateFileTool()
    import os

    content = "line1\nline2"
    call = ToolCall(
        name="create_file",
        arguments={"path": "newline.txt", "content": content},
        call_id="call-newline",
    )
    res = create_tool.run(call, context)
    assert not res.is_error
    target_path = tmp_path / "newline.txt"
    expected_raw = content.replace("\n", os.linesep).encode("utf-8")
    expected_bytes = len(expected_raw)
    actual_bytes = target_path.stat().st_size
    assert actual_bytes == expected_bytes
    assert res.metadata["bytes_written"] == expected_bytes
    assert f"({expected_bytes} bytes)" in res.output


def test_create_file_overwrite_byte_count(tmp_path: Path) -> None:
    context = ToolContext(workspace_root=tmp_path)
    create_tool = CreateFileTool()
    init_content = "line1\nline2"
    call_init = ToolCall(
        name="create_file",
        arguments={"path": "over.txt", "content": init_content},
        call_id="init-call",
    )
    res_init = create_tool.run(call_init, context)
    assert not res_init.is_error
    import os

    new_content = "newline1\nnewline2"
    call_over = ToolCall(
        name="create_file",
        arguments={"path": "over.txt", "content": new_content, "overwrite": True},
        call_id="over-call",
    )
    res_over = create_tool.run(call_over, context)
    assert not res_over.is_error
    target_path = tmp_path / "over.txt"
    expected_raw = new_content.replace("\n", os.linesep).encode("utf-8")
    expected_bytes = len(expected_raw)
    actual_bytes = target_path.stat().st_size
    assert actual_bytes == expected_bytes
    assert res_over.metadata["bytes_written"] == expected_bytes
    assert f"({actual_bytes} bytes)" in res_over.output


def test_create_file_ascii_overwrite_success_message(tmp_path: Path) -> None:
    context = ToolContext(workspace_root=tmp_path)
    create_tool = CreateFileTool()
    # precreate longer content
    long_content = "long line 1\nlong line 2\nlong line 3"
    call_init = ToolCall(
        name="create_file",
        arguments={"path": "ascii_over.txt", "content": long_content},
        call_id="init-call-ascii",
    )
    res_init = create_tool.run(call_init, context)
    assert not res_init.is_error
    # overwrite with shorter ASCII content
    short_content = "shortline"
    call_over = ToolCall(
        name="create_file",
        arguments={"path": "ascii_over.txt", "content": short_content, "overwrite": True},
        call_id="over-call-ascii",
    )
    res_over = create_tool.run(call_over, context)
    assert not res_over.is_error
    expected_bytes = len(short_content.encode("utf-8"))
    target_path = tmp_path / "ascii_over.txt"
    actual_bytes = target_path.stat().st_size
    assert actual_bytes == expected_bytes
    assert res_over.metadata["bytes_written"] == expected_bytes
    assert f"({expected_bytes} bytes)" in res_over.output
    assert target_path.read_text(encoding="utf-8") == short_content
    assert target_path.read_bytes() == short_content.encode("utf-8")


def test_create_file_newline_raw_bytes(tmp_path: Path) -> None:
    context = ToolContext(workspace_root=tmp_path)
    create_tool = CreateFileTool()
    import os

    content = "α\nβ\ngamma\nδ"
    call = ToolCall(
        name="create_file",
        arguments={"path": "newline_raw.txt", "content": content},
        call_id="call-newline-raw",
    )
    res = create_tool.run(call, context)
    assert not res.is_error
    target_path = tmp_path / "newline_raw.txt"
    expected_raw = content.replace("\n", os.linesep).encode("utf-8")
    actual_bytes = target_path.read_bytes()
    assert actual_bytes == expected_raw
    assert len(expected_raw) == res.metadata["bytes_written"]
    assert f"({len(expected_raw)} bytes)" in res.output


def test_create_file_overwrite_newline_raw_bytes(tmp_path: Path) -> None:
    context = ToolContext(workspace_root=tmp_path)
    create_tool = CreateFileTool()
    import os

    # initial longer content
    init_content = "α\nβ\ngamma\nδ\nε"
    call_init = ToolCall(
        name="create_file",
        arguments={"path": "over_raw.txt", "content": init_content},
        call_id="init-call-over-raw",
    )
    res_init = create_tool.run(call_init, context)
    assert not res_init.is_error
    # overwrite with different shorter content
    new_content = "αβγ\nδε"
    call_over = ToolCall(
        name="create_file",
        arguments={"path": "over_raw.txt", "content": new_content, "overwrite": True},
        call_id="over-call-over-raw",
    )
    res_over = create_tool.run(call_over, context)
    assert not res_over.is_error
    target_path = tmp_path / "over_raw.txt"
    expected_raw = new_content.replace("\n", os.linesep).encode("utf-8")
    actual_bytes = target_path.read_bytes()
    assert actual_bytes == expected_raw
    assert len(expected_raw) == res_over.metadata["bytes_written"]
    assert f"({len(expected_raw)} bytes)" in res_over.output
