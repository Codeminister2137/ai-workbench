"""Read-only Python runtime and workspace-hint tool contracts."""

from __future__ import annotations

import json
import os
import sys
import textwrap
import time
from pathlib import Path

import pytest
from ai_agent.contracts import ToolCall
from ai_agent.tool_profiles import CODING_PROFILE, shared_tool_registry
from ai_agent.tools import PythonRuntimeTool, ToolContext, default_coding_tools
from ai_provider.acceptance_processes import OwnedChild, process_identity
from ai_provider.acceptance_runtime import worker_environment


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


def test_outside_project_resolution_refuses_before_reading_contents(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = workspace / "pyproject.toml"
    project.write_text('[project]\nrequires-python = "PRIVATE_MARKER"\n', encoding="utf-8")
    outside = tmp_path / "private.toml"
    outside.write_bytes(project.read_bytes())
    original_resolve = Path.resolve
    original_read = Path.read_text
    reads = []

    # Model a file-link resolution without requiring Windows symlink privileges.
    # The existing junction/search tests exercise actual reparse-point traversal.
    def resolve(path, *args, **kwargs):
        return outside if path == project else original_resolve(path, *args, **kwargs)

    def read(path, *args, **kwargs):
        reads.append(path)
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    monkeypatch.setattr(Path, "read_text", read)
    result = PythonRuntimeTool().run(ToolCall("python_runtime", {}), ToolContext(workspace))

    assert result.is_error
    assert "outside" in result.output
    assert "PRIVATE_MARKER" not in result.output
    assert project not in reads and outside not in reads


def test_inside_project_link_resolution_retains_workspace_hints(tmp_path, monkeypatch):
    target = tmp_path / "project-settings.toml"
    target.write_text('[project]\nrequires-python = ">=3.13"\n', encoding="utf-8")
    project = tmp_path / "pyproject.toml"
    project.write_bytes(target.read_bytes())
    original_resolve = Path.resolve
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda path, *args, **kwargs: target
        if path == project
        else original_resolve(path, *args, **kwargs),
    )
    result = PythonRuntimeTool().run(ToolCall("python_runtime", {}), ToolContext(tmp_path))

    assert not result.is_error
    assert result.metadata["workspace"]["workspace_requires_python"] == ">=3.13"


def test_tool_is_available_to_native_and_shared_coding_profiles(tmp_path):
    assert "python_runtime" in CODING_PROFILE.tool_names
    assert isinstance(default_coding_tools().get("python_runtime"), PythonRuntimeTool)
    shared = shared_tool_registry("coding", tmp_path).get("python_runtime")
    assert isinstance(shared, PythonRuntimeTool)


@pytest.mark.parametrize("selection", ["default", "explicit"])
def test_standalone_python_validation_ignores_path_and_venv_hints(tmp_path, selection):
    """Run actual pytest without IDE transport, account mocks or a model client."""
    workspace = tmp_path / "workspace with spaces"
    workspace.mkdir()
    (workspace / "pyproject.toml").write_text(
        '[project]\nname = "python-vertical-case"\nrequires-python = ">=3.13"\n',
        encoding="utf-8",
    )
    candidate = workspace / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    candidate.parent.mkdir(parents=True)
    candidate.write_text("This is a hint, never an executable.\n", encoding="utf-8")
    wrong_path = tmp_path / "wrong-path"
    wrong_path.mkdir()
    trap = wrong_path / ("python.exe" if os.name == "nt" else "python")
    trap.write_text("#!/bin/sh\nexit 91\n", encoding="utf-8")
    trap.chmod(0o755)
    (workspace / "expected-python.txt").write_text(sys.executable, encoding="utf-8")
    (workspace / "test_runtime.py").write_text(
        "import json\nimport os\nimport sys\nfrom pathlib import Path\n\n\n"
        "def test_selected_interpreter():\n"
        "    expected = Path('expected-python.txt').read_text(encoding='utf-8')\n"
        "    assert Path(sys.executable).samefile(expected)\n"
        "    Path('actual-runtime.json').write_text(json.dumps(\n"
        "        dict(executable=sys.executable, pid=os.getpid())), encoding='utf-8')\n",
        encoding="utf-8",
    )
    worker = tmp_path / "standalone.py"
    worker.write_text(
        textwrap.dedent("""\
            import json
            import shutil
            import sys
            from dataclasses import asdict
            from pathlib import Path

            def offline(event, arguments):
                if event in {"socket.connect", "socket.bind", "socket.getaddrinfo"}:
                    raise AssertionError("Standalone acceptance cannot contact a host")

            sys.addaudithook(offline)
            from ai_agent.contracts import ToolCall
            from ai_agent.repo_assistant_args import (
                build_argument_parser, DEFAULT_VALIDATION_COMMAND,
            )
            from ai_agent.tools.base import ToolContext
            from ai_agent.tools.python_runtime import PythonRuntimeTool
            from ai_agent.validation import default_validation_python, run_validation_commands

            workspace = Path.cwd()
            selection = sys.argv[1]
            args = build_argument_parser().parse_args(
                ["--validation-python", sys.executable] if selection == "explicit" else []
            )
            runtime = PythonRuntimeTool().run(
                ToolCall("python_runtime", {}), ToolContext(workspace),
            )
            assert not runtime.is_error, runtime.output
            results = run_validation_commands(
                (DEFAULT_VALIDATION_COMMAND,), repo_root=workspace, timeout_seconds=30,
                default_python=default_validation_python(args), progress_callback=lambda _: None,
            )
            # Windows native lookup can differ from shutil.which. Explicit selection
            # makes this negative control independent of the platform search order.
            wrong_args = build_argument_parser().parse_args(["--validation-python", sys.argv[2]])
            control = run_validation_commands(
                (DEFAULT_VALIDATION_COMMAND,), repo_root=workspace, timeout_seconds=10,
                default_python=default_validation_python(wrong_args),
                progress_callback=lambda _: None,
            )
            assert "ai_agent.ide_bridge" not in sys.modules
            assert "ai_agent.mcp_server" not in sys.modules
            Path("receipts.json").write_text(json.dumps(dict(
                runtime=runtime.metadata, path_python=shutil.which("python"),
                results=[asdict(item) for item in results],
                control=[asdict(item) for item in control],
                ide_transport_loaded=False,
            ), indent=2), encoding="utf-8")
        """),
        encoding="utf-8",
    )
    environment = worker_environment()
    environment["PATH"] = str(wrong_path) + os.pathsep + environment.get("PATH", "")
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    events = []
    child = OwnedChild(
        [sys.executable, str(worker), selection, str(trap)],
        cwd=workspace,
        env=environment,
        log=tmp_path / "standalone.log",
        role="standalone-python-validation",
        receipt=events.append,
    )
    try:
        code = child.wait(time.monotonic() + 60)
    finally:
        cleanup = child.stop(5)
        (tmp_path / "ownership.json").write_text(
            json.dumps(dict(events=events, cleanup_verified=cleanup)), encoding="utf-8"
        )
    assert cleanup
    assert process_identity(child.process.pid) != child.birth
    assert code == 0, (tmp_path / "standalone.log").read_text(encoding="utf-8")
    receipts = json.loads((workspace / "receipts.json").read_text(encoding="utf-8"))
    assert Path(receipts["path_python"]).samefile(trap)
    assert Path(receipts["runtime"]["runtime"]["executable"]).samefile(sys.executable)
    assert receipts["runtime"]["workspace"]["workspace_venv_python"] == str(candidate)
    assert receipts["runtime"]["workspace"]["workspace_venv_active"] is False
    result = receipts["results"][0]
    assert result["status"] == "passed" and result["returncode"] == 0
    assert "1 passed" in result["stdout_preview"]
    assert Path(result["executable"]).samefile(sys.executable)
    assert receipts["control"][0]["status"] in {"failed", "failed_to_start"}
    assert Path(receipts["control"][0]["executable"]).samefile(trap)
    actual = json.loads((workspace / "actual-runtime.json").read_text(encoding="utf-8"))
    assert Path(actual["executable"]).samefile(sys.executable)
    assert process_identity(actual["pid"]) is None
