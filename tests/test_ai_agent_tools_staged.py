"""StageFileTool: staged records for review, never direct disk writes."""

from pathlib import Path

from ai_agent.contracts import ToolCategory
from ai_agent.tools.base import ToolContext
from ai_agent.tools.staged import StageFileTool


def _context(tmp_path: Path) -> ToolContext:
    return ToolContext(workspace_root=tmp_path)


def test_stage_new_file_returns_record_without_writing(tmp_path) -> None:
    tool = StageFileTool()
    assert tool.definition.category is ToolCategory.WRITE
    result = tool.execute({"relpath": "src/new.py", "content": "print('hi')\n"}, _context(tmp_path))
    assert result.is_error is False
    assert "new file" in result.output
    record = result.metadata["staged"]
    assert record["relpath"] == "src/new.py"
    assert record["base_digest"] is None
    assert record["content"] == "print('hi')\n"
    assert not (tmp_path / "src" / "new.py").exists()


def test_stage_existing_file_snapshots_base(tmp_path) -> None:
    (tmp_path / "app.py").write_text("old\n", encoding="utf-8")
    result = StageFileTool().execute({"relpath": "app.py", "content": "new\n"}, _context(tmp_path))
    assert result.is_error is False
    record = result.metadata["staged"]
    assert record["base_digest"] is not None
    assert record["digest"] != record["base_digest"]
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "old\n"


def test_stage_refuses_escape(tmp_path) -> None:
    result = StageFileTool().execute(
        {"relpath": "../outside.py", "content": "x"}, _context(tmp_path)
    )
    assert result.is_error is True
    assert "refused" in result.output
    assert result.metadata == {}


def test_stage_requires_arguments(tmp_path) -> None:
    assert StageFileTool().execute({}, _context(tmp_path)).is_error is True
    assert StageFileTool().execute({"relpath": "a.py"}, _context(tmp_path)).is_error is True
    assert (
        StageFileTool().execute({"relpath": "a.py", "content": 42}, _context(tmp_path)).is_error
        is True
    )
