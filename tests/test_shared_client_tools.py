"""Common inspection preserves tools and narrow grants across native clients."""

import json
import subprocess
from pathlib import Path

import pytest
from ai_agent.contracts import ToolCall
from ai_agent.skills import (
    discover_development_skills,
    load_development_skills,
    skill_prompt,
)
from ai_agent.tool_profiles import INSPECTION_PROFILE, shared_tool_registry
from ai_agent.tools import ToolContext
from ai_orchestrator import AccessMethod
from ai_provider.external_agents import (
    ExternalAgentConfig,
    build_external_agent_command,
    run_external_agent,
)
from ai_provider.repo_context import build_repo_prompt, load_prompt_context


def config(path: Path, method: AccessMethod) -> ExternalAgentConfig:
    return ExternalAgentConfig(
        method,
        "client",
        "auto",
        path,
        10,
        sandbox="read-only",
        approval_policy="read_only",
        shared_tool_profile="inspection",
    )


@pytest.mark.parametrize("method", [AccessMethod.CODEX_CLI, AccessMethod.COPILOT_CLI])
def test_inspection_mapping_has_every_required_tool_and_no_broad_grant(tmp_path, method):
    command = build_external_agent_command(config(tmp_path, method), prompt="review")
    rendered = " ".join(command)
    assert all(tool in rendered for tool in INSPECTION_PROFILE.tool_names)
    assert "--read-search-only" in rendered
    assert "--allow-all" not in command
    assert "--trust-all-tools" not in command
    assert "--dangerously-skip-permissions" not in command
    assert not list(tmp_path.iterdir())


def test_antigravity_shared_inspection_is_explicitly_ineligible(tmp_path):
    with pytest.raises(
        NotImplementedError,
        match=r"headless mode denies MCP tools.*permissions\.allow.*dangerously-skip-permissions",
    ):
        build_external_agent_command(config(tmp_path, AccessMethod.ANTIGRAVITY_CLI))


@pytest.mark.parametrize("failure", [False, True])
def test_kiro_run_scopes_tools_and_cleans_generated_configuration(tmp_path, failure):
    observed = []

    def runner(command, **kwargs):
        path = next((tmp_path / ".kiro/agents").glob("repo-shared-*.json"))
        settings = json.loads(path.read_text())
        observed.append(settings)
        assert settings["tools"] == settings["allowedTools"]
        assert set(settings["tools"]) == {
            "@repo_shared/" + n for n in INSPECTION_PROFILE.tool_names
        }
        assert command[-1] == "inspect"
        assert kwargs["input"] == ""
        if failure:
            raise OSError("client unavailable")
        return subprocess.CompletedProcess(command, 0, "answer", "")

    if failure:
        with pytest.raises(OSError, match="unavailable"):
            run_external_agent("inspect", config(tmp_path, AccessMethod.KIRO_CLI), runner=runner)
    else:
        run_external_agent("inspect", config(tmp_path, AccessMethod.KIRO_CLI), runner=runner)
    assert len(observed) == 1
    assert not (tmp_path / ".kiro").exists()


def test_kiro_cleanup_preserves_existing_config_and_changed_generated_file(tmp_path):
    directory = tmp_path / ".kiro/agents"
    directory.mkdir(parents=True)
    user_file = directory / "human.json"
    user_file.write_text("keep me")

    def runner(command, **kwargs):
        generated = next(directory.glob("repo-shared-*.json"))
        generated.write_text("changed by client")
        return subprocess.CompletedProcess(command, 0, "answer", "")

    run_external_agent("inspect", config(tmp_path, AccessMethod.KIRO_CLI), runner=runner)
    assert user_file.read_text() == "keep me"
    assert next(directory.glob("repo-shared-*.json")).read_text() == "changed by client"


def test_native_registry_and_client_declaration_share_a_contract():
    registry = shared_tool_registry("inspection")
    assert tuple(t.name for t in registry.list_definitions()) == INSPECTION_PROFILE.tool_names
    assert registry.get("run_command") is None
    assert registry.get("edit_file") is None


def test_skill_source_prerequisites_and_duplicate_detection(tmp_path):
    name = "review-repo-change"
    source = tmp_path / name / "SKILL.md"
    source.parent.mkdir()
    source.write_text(f"---\nname: {name}\ndescription: review\n---\nRead the diff.")
    available = frozenset(INSPECTION_PROFILE.tool_names)
    skills = load_development_skills([name, name], [tmp_path], available_tools=available)
    assert len(skills) == 1
    assert "Read the diff" in skill_prompt(skills)
    with pytest.raises(ValueError, match="unavailable tools"):
        load_development_skills([name], [tmp_path], available_tools=available - {"git_diff"})
    other = tmp_path / "other"
    second = other / name / "SKILL.md"
    second.parent.mkdir(parents=True)
    second.write_text(source.read_text())
    with pytest.raises(ValueError, match="found 2"):
        load_development_skills([name], [tmp_path, other], available_tools=available)


def test_skill_discovery_reports_sources_and_missing_prerequisites(tmp_path, monkeypatch):
    name = "review-repo-change"
    source = tmp_path / name / "SKILL.md"
    source.parent.mkdir()
    source.write_text(f"---\nname: {name}\ndescription: review\n---\nRead the diff.")
    monkeypatch.setattr("ai_agent.skills.shutil.which", lambda executable: None)

    skill = discover_development_skills(
        [tmp_path], available_tools=frozenset(INSPECTION_PROFILE.tool_names)
    )[0]
    assert skill.name == name
    assert skill.source == source.resolve()
    assert not skill.available
    assert skill.required_tools == (
        "find_files",
        "git_diff",
        "git_status",
        "grep_search",
        "read_file",
    )
    assert skill.reason == "Skill review-repo-change requires an installed Git executable"

    blocked = discover_development_skills(
        [tmp_path],
        available_tools=frozenset(INSPECTION_PROFILE.tool_names) - {"git_diff"},
    )[0]
    assert not blocked.available
    assert blocked.reason is not None
    assert "requires unavailable tools: git_diff" in blocked.reason


def test_skill_discovery_reports_missing_and_ambiguous_sources(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert not discover_development_skills([first], available_tools=frozenset())[0].available

    for directory in (first, second):
        source = directory / "review-repo-change" / "SKILL.md"
        source.parent.mkdir(parents=True)
        source.write_text("---\nname: review-repo-change\ndescription: review\n---\nRead the diff.")
    ambiguous = discover_development_skills([first, second], available_tools=frozenset())[0]
    assert not ambiguous.available
    assert ambiguous.source is None
    assert ambiguous.reason == "multiple sources found: 2"


def test_skill_selection_refuses_traversal_or_unknown_prerequisites(tmp_path):
    with pytest.raises(ValueError, match="supported prerequisite"):
        load_development_skills(["../private"], [tmp_path], available_tools=frozenset())


def test_skill_selection_refuses_when_git_executable_is_missing(tmp_path, monkeypatch):
    name = "review-repo-change"
    source = tmp_path / name / "SKILL.md"
    source.parent.mkdir()
    source.write_text(f"---\nname: {name}\ndescription: review\n---\nRead the diff.")
    monkeypatch.setattr("ai_agent.skills.shutil.which", lambda executable: None)

    with pytest.raises(ValueError, match="requires an installed Git executable"):
        load_development_skills(
            [name],
            [tmp_path],
            available_tools=frozenset(INSPECTION_PROFILE.tool_names),
        )


def test_portable_review_skill_inspects_actual_git_and_working_instructions(tmp_path):
    workspace = tmp_path / "review workspace"
    workspace.mkdir()

    def git(*arguments):
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
            timeout=10,
        ).stdout

    git("init", "--template=")
    source = workspace / "total.py"
    source.write_text("def total(values):\n    return sum(values)\n", encoding="utf-8")
    instructions = workspace / "AGENTS.md"
    instructions.write_text("Original committed instructions.\n", encoding="utf-8")
    git("add", "--", "total.py", "AGENTS.md")
    git("commit", "-m", "Public synthetic baseline")
    source.write_text("def total(values):\n    return len(values)\n", encoding="utf-8")
    git("add", "--", "total.py")
    source.write_text("def total(values):\n    return sum(values) + 1\n", encoding="utf-8")
    instructions.write_text("Working instructions: inspect both Git snapshots.\n", encoding="utf-8")
    index_before = git("write-tree")
    original_bytes = {path: path.read_bytes() for path in (source, instructions)}
    registry = shared_tool_registry("inspection", workspace)
    available = frozenset(item.name for item in registry.list_definitions())
    skill_directory = Path(__file__).resolve().parents[1] / "packages/ai_agent/skills"
    selected = load_development_skills(
        ["review-repo-change"],
        [skill_directory],
        available_tools=available,
    )
    context = load_prompt_context(workspace, [source], context_budget_chars=1)
    prompt = (
        build_repo_prompt("Inspect the current change.", context) + "\n" + skill_prompt(selected)
    )
    assert instructions.read_text(encoding="utf-8").strip() in prompt
    assert "Original committed instructions." not in prompt
    assert selected[0].instructions in prompt
    assert any(item.required_instruction and item.path == instructions for item in context)
    calls = [
        ToolCall("git_status", {}),
        ToolCall("git_diff", {"path": "total.py", "staged": True}),
        ToolCall("git_diff", {"path": "total.py"}),
        ToolCall("read_file", {"path": "total.py"}),
        ToolCall("find_files", {"pattern": "*.py"}),
        ToolCall("grep_search", {"query": "sum(values)", "path": "total.py"}),
    ]
    results = [registry.execute(call, ToolContext(workspace)) for call in calls]
    assert all(not result.is_error for result in results), results
    assert "MM total.py" in results[0].output
    assert "+    return len(values)" in results[1].output
    assert "+    return sum(values) + 1" in results[2].output
    assert "len(values)" not in results[3].output
    assert "sum(values) + 1" in results[3].output
    assert "total.py" in results[4].output and results[5].metadata["matches"] == 1
    assert git("write-tree") == index_before
    assert all(path.read_bytes() == content for path, content in original_bytes.items())
