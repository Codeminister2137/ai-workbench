"""Read-only Python runtime and workspace-hint tool contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ai_agent.contracts import ToolCall
from ai_agent.tool_profiles import CODING_PROFILE, shared_tool_registry
from ai_agent.tools import PythonRuntimeTool, ToolContext, default_coding_tools


def test_reports_active_interpreter_and_workspace_hints_without_running_code(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "fixture"\nrequires-python = ">=3.12"\n', encoding="utf-8"
    )
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    tool = PythonRuntimeTool()

    result = tool.run(ToolCall("python_runtime", {}), ToolContext(tmp_path))

    assert not result.is_error
    metadata = result.metadata
    assert metadata["runtime"]["executable"] == str(Path(sys.executable).resolve())
    assert metadata["runtime"]["version"] == sys.version.split()[0]
    assert metadata["runtime"]["implementation"] == sys.implementation.name
    assert metadata["workspace"] == {
        "workspace_requires_python": ">=3.12",
        "workspace_venv_python": None,
        "uv_lock_present": True,
        "workspace_venv_active": Path(sys.prefix).resolve().is_relative_to(tmp_path.resolve()),
    }
    assert json.loads(result.output) == metadata


def test_reports_workspace_venv_candidate_without_claiming_it_is_selected(tmp_path):
    executable = (
        tmp_path / ".venv" / "Scripts" / "python.exe"
        if sys.platform == "win32"
        else tmp_path / ".venv" / "bin" / "python"
    )
    executable.parent.mkdir(parents=True)
    executable.write_text("fixture", encoding="utf-8")

    result = PythonRuntimeTool().run(ToolCall("python_runtime", {}), ToolContext(tmp_path))

    assert not result.is_error
    assert result.metadata["workspace"]["workspace_venv_python"] == str(executable)


def test_invalid_pyproject_is_reported_explicitly(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project\n", encoding="utf-8")

    result = PythonRuntimeTool().run(ToolCall("python_runtime", {}), ToolContext(tmp_path))

    assert result.is_error
    assert "Cannot read workspace pyproject.toml" in result.output


def test_tool_is_available_to_native_and_shared_coding_profiles(tmp_path):
    assert "python_runtime" in CODING_PROFILE.tool_names
    assert isinstance(default_coding_tools().get("python_runtime"), PythonRuntimeTool)
    shared = shared_tool_registry("coding", tmp_path).get("python_runtime")
    assert isinstance(shared, PythonRuntimeTool)
