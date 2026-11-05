"""OwnerTaskTool: human-task records for inbox filing, store-free."""

from ai_agent.contracts import ToolCategory
from ai_agent.tools.base import ToolContext
from ai_agent.tools.owner_tasks import OwnerTaskTool


def test_files_task_metadata(tmp_path) -> None:
    tool = OwnerTaskTool()
    assert tool.definition.category is ToolCategory.CUSTOM
    result = tool.execute(
        {"title": "Probe the mic", "body": "1. Open chat\n2. Dictate\n3. Report."},
        ToolContext(workspace_root=tmp_path),
    )
    assert result.is_error is False
    assert result.metadata == {
        "owner_task": {"title": "Probe the mic", "body": "1. Open chat\n2. Dictate\n3. Report."}
    }


def test_validates_lengths(tmp_path) -> None:
    context = ToolContext(workspace_root=tmp_path)
    assert OwnerTaskTool().execute({}, context).is_error is True
    assert OwnerTaskTool().execute({"title": "  ", "body": "b"}, context).is_error is True
    assert OwnerTaskTool().execute({"title": "t" * 201, "body": "b"}, context).is_error is True
    assert OwnerTaskTool().execute({"title": "t", "body": "b" * 8001}, context).is_error is True
