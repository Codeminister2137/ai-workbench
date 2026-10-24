"""C1-C6 common capabilities remain usable without the PyCharm tool host.

M5 requires the approved capability set to work while PyCharm is only an editor
and viewer. Each test exercises one capability through the shared coding
registry in a workspace that has no IDE configuration. Two further checks prove
the IDE tools are an optional additive surface and that the common surface never
loads the MCP SDK.
"""

import importlib
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from ai_agent import ide_bridge
from ai_agent.contracts import ToolCall, ToolCategory
from ai_agent.ide_bridge import CONFIG_PATH, IDE_TOOL_NAMES
from ai_agent.processes import ProcessSupervisor, ProcessTool
from ai_agent.skills import load_development_skills, skill_prompt
from ai_agent.tool_profiles import CODING_PROFILE, shared_tool_registry
from ai_agent.tools import ToolContext
from ai_agent.tools.research import FetchURLTool
from ai_agent.tools.research_http import FetchedSource
from ai_provider.repo_context import build_repo_prompt, load_prompt_context

SKILLS = Path(__file__).resolve().parents[1] / "packages/ai_agent/skills"

# Entry points the common coding profile must expose for each capability. C2
# reuses the inspection tools its portable skill declares; C6's handle-based
# continuity is host-level and is exercised separately below.
CAPABILITY_TOOLS = {
    "C1": {
        "create_file",
        "edit_file",
        "find_files",
        "git_diff",
        "git_status",
        "grep_search",
        "list_dir",
        "read_file",
    },
    "C2": {"find_files", "git_diff", "git_status", "grep_search", "read_file"},
    "C3": {"python_runtime", "run_command"},
    "C4": {"fetch_url"},
    "C5": {"python_navigate", "rename_apply", "rename_preview"},
    "C6": {"run_command"},
}


@pytest.fixture
def jedi_required():
    try:
        importlib.import_module("jedi")
    except ImportError:
        pytest.skip("install the optional rename-preview extra for Jedi integration tests")


def git(workspace: Path, *arguments: str) -> str:
    return subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=" + str(workspace / "no-hooks"),
            "-c",
            "commit.gpgsign=false",
            "-c",
            "user.name=Offline Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            *arguments,
        ],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout


def execute(registry, name: str, arguments: dict, context: ToolContext):
    result = registry.execute(ToolCall(name, arguments), context)
    assert not result.is_error, result.output
    return result


def test_common_surface_is_complete_and_imports_no_mcp_sdk(tmp_path):
    assert not (tmp_path / CONFIG_PATH).exists()
    registry = shared_tool_registry("coding", tmp_path)
    names = {definition.name for definition in registry.list_definitions()}
    assert names == set(CODING_PROFILE.tool_names)
    assert not names & set(IDE_TOOL_NAMES)
    for capability, required in CAPABILITY_TOOLS.items():
        assert required <= names, capability

    script = (
        "import sys\n"
        "from pathlib import Path\n"
        "from ai_agent.tool_profiles import shared_tool_registry\n"
        "registry = shared_tool_registry('coding', Path(sys.argv[1]))\n"
        "print(len(registry.list_definitions()))\n"
        "print('mcp' in sys.modules)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-B", "-c", script, str(tmp_path)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert completed.stdout.split() == [str(len(CODING_PROFILE.tool_names)), "False"]


def test_ide_tools_are_optional_and_purely_additive(tmp_path):
    common = {item.name for item in shared_tool_registry("coding", tmp_path).list_definitions()}
    config = tmp_path / CONFIG_PATH
    config.parent.mkdir()
    config.write_text(
        json.dumps(
            {
                "type": "streamable-http",
                "url": "http://127.0.0.1:12345/stream",
                "headers": {ide_bridge.PROJECT_HEADER: str(tmp_path)},
            }
        ),
        encoding="utf-8",
    )
    definitions = {
        item.name: item for item in shared_tool_registry("coding", tmp_path).list_definitions()
    }
    assert set(definitions) == common | set(IDE_TOOL_NAMES)
    assert all(definitions[name].category is ToolCategory.READ for name in IDE_TOOL_NAMES)

    config.unlink()
    restored = {item.name for item in shared_tool_registry("coding", tmp_path).list_definitions()}
    assert restored == common


def test_c1_repository_and_git_tools_work_without_ide(tmp_path):
    registry = shared_tool_registry("coding", tmp_path)
    context = ToolContext(tmp_path)
    git(tmp_path, "init", "--template=")
    module = tmp_path / "module.py"
    module.write_text("def total(values):\n    return sum(values)\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("Fixture instructions.\n", encoding="utf-8")
    git(tmp_path, "add", "--", "module.py", "AGENTS.md")
    git(tmp_path, "commit", "-m", "baseline")
    module.write_text("def total(values):\n    return len(values)\n", encoding="utf-8")
    git(tmp_path, "add", "--", "module.py")
    module.write_text("def total(values):\n    return sum(values) + 1\n", encoding="utf-8")
    index_before = git(tmp_path, "write-tree")

    status = execute(registry, "git_status", {}, context)
    assert "MM module.py" in status.output
    staged = execute(registry, "git_diff", {"path": "module.py", "staged": True}, context)
    assert "+    return len(values)" in staged.output
    unstaged = execute(registry, "git_diff", {"path": "module.py"}, context)
    assert "-    return len(values)" in unstaged.output
    assert "+    return sum(values) + 1" in unstaged.output

    read = execute(registry, "read_file", {"path": "module.py"}, context)
    assert "sum(values) + 1" in read.output
    listing = execute(registry, "list_dir", {"path": ".", "max_depth": 1}, context)
    assert "module.py" in listing.output
    found = execute(registry, "find_files", {"pattern": "*.py"}, context)
    assert "module.py" in found.output
    grepped = execute(
        registry, "grep_search", {"query": "sum(values)", "path": "module.py"}, context
    )
    assert grepped.metadata["matches"] == 1

    execute(registry, "create_file", {"path": "extra.py", "content": "value = 1\n"}, context)
    execute(
        registry,
        "edit_file",
        {"path": "extra.py", "old_text": "value = 1", "new_text": "value = 2"},
        context,
    )
    assert (tmp_path / "extra.py").read_text(encoding="utf-8") == "value = 2\n"
    assert git(tmp_path, "write-tree") == index_before


def test_c2_portable_skill_and_instructions_work_without_ide(tmp_path):
    registry = shared_tool_registry("coding", tmp_path)
    available = frozenset(item.name for item in registry.list_definitions())
    assert not set(IDE_TOOL_NAMES) & available
    selected = load_development_skills(["review-repo-change"], [SKILLS], available_tools=available)
    assert len(selected) == 1
    assert selected[0].required_tools <= available

    source = tmp_path / "module.py"
    source.write_text("value = 1\n", encoding="utf-8")
    instructions = tmp_path / "AGENTS.md"
    instructions.write_text("Working instructions: inspect both Git snapshots.\n", encoding="utf-8")
    context = load_prompt_context(tmp_path, [source], context_budget_chars=1)
    prompt = build_repo_prompt("Review the change.", context) + "\n" + skill_prompt(selected)
    assert "inspect both Git snapshots" in prompt
    assert selected[0].instructions in prompt
    assert any(item.required_instruction and item.path == instructions for item in context)


def test_c3_python_runtime_and_validation_work_without_ide(tmp_path):
    registry = shared_tool_registry("coding", tmp_path)
    context = ToolContext(tmp_path)
    runtime = execute(registry, "python_runtime", {}, context)
    assert runtime.metadata["runtime"]["executable"] == str(Path(sys.executable).resolve())

    (tmp_path / "test_sample.py").write_text(
        "import unittest\n\n"
        "class SampleTests(unittest.TestCase):\n"
        "    def test_addition(self):\n"
        "        self.assertEqual(1 + 1, 2)\n",
        encoding="utf-8",
    )
    command = (
        f"& '{sys.executable}' -B -m unittest discover -s . -p 'test_*.py'"
        if sys.platform == "win32"
        else f"'{sys.executable}' -B -m unittest discover -s . -p 'test_*.py'"
    )
    validated = execute(
        registry, "run_command", {"command": command, "timeout_seconds": 60}, context
    )
    assert "Ran 1 test" in validated.output and "OK" in validated.output


def test_c4_public_fetch_preserves_provenance_without_ide(tmp_path):
    registry = shared_tool_registry("coding", tmp_path)
    assert registry.get("fetch_url") is not None
    recorded: list[tuple[str, dict]] = []
    url = "https://example.invalid/public"
    receipt = {
        "requested_url": url,
        "final_url": url,
        "http_status": 200,
        "content_type": "text/html; charset=utf-8",
    }

    def fetcher(_url: str) -> FetchedSource:
        return FetchedSource(
            body=b"<html><body>Public source text</body></html>",
            content_type="text/html",
            charset="utf-8",
            receipt=dict(receipt),
        )

    tool = FetchURLTool(lambda event, payload: recorded.append((event, payload)), fetcher=fetcher)
    result = tool.run(ToolCall("fetch_url", {"url": url}), ToolContext(tmp_path))
    assert not result.is_error, result.output
    assert result.metadata["final_url"] == url
    assert "Public source text" in result.output
    assert recorded == [("fetch_receipts", receipt)]

    guarded = FetchURLTool(lambda _event, _payload: None)
    refused = guarded.run(
        ToolCall("fetch_url", {"url": "http://127.0.0.1/"}), ToolContext(tmp_path)
    )
    assert refused.is_error
    assert "private or non-public" in refused.output


def test_c5_semantic_navigation_and_guarded_rename_work_without_ide(tmp_path, jedi_required):
    package = tmp_path / "sample_pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    models = package / "models.py"
    models.write_text("class Widget:\n    pass\n", encoding="utf-8")
    client = package / "client.py"
    client.write_text("from .models import Widget\n\nitem = Widget()\n", encoding="utf-8")

    registry = shared_tool_registry("coding", tmp_path)
    context = ToolContext(tmp_path)
    definitions = execute(
        registry,
        "python_navigate",
        {
            "path": "sample_pkg/client.py",
            "line": 3,
            "column": 9,
            "operation": "definitions",
        },
        context,
    )
    assert ("sample_pkg/models.py", 1) in {
        (item["path"], item["line"]) for item in definitions.metadata["results"]
    }

    before = {path: path.read_bytes() for path in (models, client)}
    preview = execute(
        registry,
        "rename_preview",
        {
            "path": "sample_pkg/models.py",
            "line": 1,
            "column": 7,
            "new_name": "Gadget",
        },
        context,
    )
    assert all(path.read_bytes() == content for path, content in before.items())
    assert preview.metadata["applied"] is False
    assert set(preview.metadata["files"]) == {"sample_pkg/models.py", "sample_pkg/client.py"}

    applied = execute(registry, "rename_apply", {"plan_id": preview.metadata["plan_id"]}, context)
    assert {item["path"] for item in applied.metadata["applied"]} == {
        "sample_pkg/models.py",
        "sample_pkg/client.py",
    }
    assert "class Gadget" in models.read_text(encoding="utf-8")
    assert "import Gadget" in client.read_text(encoding="utf-8")


def test_c6_process_continuity_works_without_ide(tmp_path):
    supervisor = ProcessSupervisor(tmp_path)
    context = ToolContext(tmp_path)
    try:
        started = ProcessTool(supervisor, "start").run(
            ToolCall(
                "process_start",
                {"argv": [sys.executable, "-B", "-c", "print('child-ok')"]},
            ),
            context,
        )
        assert not started.is_error, started.output
        handle = started.metadata["process_handle"]
        status_tool = ProcessTool(supervisor, "status")
        deadline = time.monotonic() + 30
        while True:
            status = status_tool.run(
                ToolCall("process_status", {"process_handle": handle}), context
            )
            assert not status.is_error, status.output
            if status.metadata["status"] != "running":
                break
            assert time.monotonic() < deadline
            time.sleep(0.05)
        assert status.metadata["status"] == "completed"
        assert "child-ok" in status.metadata["stdout"]
    finally:
        supervisor.close()

    refused = ProcessTool(supervisor, "start").run(
        ToolCall("process_start", {"argv": [sys.executable, "-B", "-c", "pass"]}),
        context,
    )
    assert refused.is_error
    assert "closed" in refused.output
