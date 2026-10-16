"""A valid empty file is distinct from a requested range with no valid lines."""

import pytest
from ai_agent import ReadFileTool, ToolCall, ToolContext


@pytest.mark.parametrize("options", [{}, {"line_numbers": True}, {"line_numbers": False}])
def test_unbounded_empty_file_read_succeeds(tmp_path, options):
    target = tmp_path / "empty.py"
    target.write_bytes(b"")
    result = ReadFileTool().run(
        ToolCall("read_file", {"path": "empty.py", **options}, call_id="empty-read"),
        ToolContext(tmp_path),
    )
    assert not result.is_error
    assert result.output == ""
    assert result.metadata == {"path": str(target.resolve()), "lines_read": 0}
    assert result.call_id == "empty-read"
    assert target.read_bytes() == b""


@pytest.mark.parametrize("bounds", [{"start_line": 1}, {"end_line": 1}, {"start_line": 2}])
def test_empty_file_explicit_line_request_remains_invalid(tmp_path, bounds):
    (tmp_path / "empty.py").write_bytes(b"")
    result = ReadFileTool().run(
        ToolCall("read_file", {"path": "empty.py", **bounds}), ToolContext(tmp_path)
    )
    assert result.is_error
    assert "beyond total lines (0)" in result.output
