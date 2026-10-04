from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from ai_agent import GitDiffTool, GitStatusTool, ToolCategory, ToolContext


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


@pytest.fixture
def working_tree(tmp_path: Path) -> Path:
    git(tmp_path, "init", "--quiet")
    (tmp_path / "source.txt").write_text("old\n", encoding="utf-8")
    git(tmp_path, "add", "source.txt")
    return tmp_path


def test_status_preserves_index_and_reports_changes(working_tree: Path) -> None:
    index = working_tree / ".git" / "index"
    before = index.read_bytes()
    (working_tree / "untracked.txt").write_text("new")
    result = GitStatusTool().execute({}, ToolContext(working_tree))
    assert not result.is_error
    assert "source.txt" in result.output and "untracked.txt" in result.output
    assert index.read_bytes() == before
    assert GitStatusTool().definition.category is ToolCategory.READ


def test_diff_separates_staged_and_unstaged_without_external_helpers(working_tree: Path) -> None:
    git(working_tree, "config", "diff.external", "nonexistent-external-diff-helper")
    (working_tree / "source.txt").write_text("new\n", encoding="utf-8")
    context = ToolContext(working_tree)
    unstaged = GitDiffTool().execute({"path": "source.txt"}, context)
    staged = GitDiffTool().execute({"staged": True}, context)
    assert not unstaged.is_error and not staged.is_error
    assert "-old" in unstaged.output and "+new" in unstaged.output
    assert "+old" in staged.output and "+new" not in staged.output


def test_git_rejects_parent_repository_and_outside_diff(working_tree: Path) -> None:
    child = working_tree / "child"
    child.mkdir()
    assert GitStatusTool().execute({}, ToolContext(child)).is_error
    assert GitDiffTool().execute({"path": "../outside"}, ToolContext(working_tree)).is_error


def test_diff_treats_git_pathspec_magic_as_literal(working_tree: Path) -> None:
    file = working_tree / "[special].txt"
    file.write_text("staged\n")
    git(working_tree, "add", "[special].txt")
    file.write_text("changed\n")
    result = GitDiffTool().execute({"path": "[special].txt"}, ToolContext(working_tree))
    assert not result.is_error and "+changed" in result.output


def test_git_ignores_inherited_repository_override(working_tree: Path, monkeypatch) -> None:
    monkeypatch.setenv("GIT_DIR", str(working_tree / "missing-admin-dir"))
    monkeypatch.setenv("GIT_WORK_TREE", str(working_tree.parent))
    assert not GitStatusTool().execute({}, ToolContext(working_tree)).is_error


@pytest.mark.parametrize("tool", [GitStatusTool(), GitDiffTool()])
@pytest.mark.parametrize("helper_kind", ["clean", "process"])
def test_git_inspection_does_not_execute_content_filters(
    working_tree: Path, tool, helper_kind: str
) -> None:
    marker = working_tree / "filter-executed.txt"
    (working_tree / ".gitattributes").write_text("source.txt filter=fixture\n")
    git(
        working_tree,
        "config",
        f"filter.fixture.{helper_kind}",
        f'echo executed > "{marker.as_posix()}"',
    )
    git(working_tree, "config", "filter.fixture.required", "true")
    (working_tree / "source.txt").write_text("new\n")
    index_before = (working_tree / ".git/index").read_bytes()

    result = tool.execute({}, ToolContext(working_tree))

    assert not marker.exists(), "Git inspection executed a configured content helper"
    assert not result.is_error
    assert "source.txt" in result.output
    assert (working_tree / ".git/index").read_bytes() == index_before
    assert result.metadata["content_filters_disabled"]
    assert "comparing raw worktree content" in result.output
    assert git(working_tree, "config", "filter.fixture.required").strip() == "true"


def test_git_refuses_filter_names_that_cannot_be_overridden(working_tree: Path) -> None:
    marker = working_tree / "filter-executed.txt"
    (working_tree / ".gitattributes").write_text("source.txt filter=fixture=value\n")
    git(
        working_tree,
        "config",
        "filter.fixture=value.clean",
        f'echo executed > "{marker.as_posix()}"',
    )
    (working_tree / "source.txt").write_text("changed\n")

    result = GitDiffTool().execute({}, ToolContext(working_tree))

    assert result.is_error
    assert "cannot be safely overridden" in result.output
    assert not marker.exists()


@pytest.mark.parametrize("tool", [GitStatusTool(), GitDiffTool()])
def test_git_inspection_does_not_enter_submodule_content(working_tree: Path, tool) -> None:
    module = working_tree.parent / (working_tree.name + "-module")
    module.mkdir()
    git(module, "init", "--quiet", "--template=")
    (module / "tracked.txt").write_text("original\n")
    git(module, "add", "tracked.txt")
    commit_options = (
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "-c",
        "core.hooksPath=missing-hooks",
    )
    git(module, *commit_options, "commit", "--quiet", "-m", "Fixture baseline")
    git(
        working_tree,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "--quiet",
        str(module),
        "module",
    )
    nested = working_tree / "module"
    marker = working_tree / "nested-filter-executed.txt"
    (nested / ".gitattributes").write_text("tracked.txt filter=nested-fixture\n")
    git(nested, "config", "filter.nested-fixture.clean", f'echo executed > "{marker.as_posix()}"')
    (nested / "tracked.txt").write_text("modified\n")
    git(
        nested,
        *commit_options,
        "-c",
        "filter.nested-fixture.clean=",
        "commit",
        "--allow-empty",
        "--quiet",
        "-m",
        "Fixture pointer change",
    )
    git(working_tree, "config", "diff.submodule", "diff")
    git(working_tree, "config", "status.submoduleSummary", "true")

    result = tool.execute({}, ToolContext(working_tree))

    assert not result.is_error
    assert not marker.exists()
    assert "module" in result.output
    if isinstance(tool, GitDiffTool):
        assert "+Subproject commit" in result.output


def test_git_missing_repository_is_actionable(tmp_path: Path) -> None:
    result = GitStatusTool().execute({}, ToolContext(tmp_path))
    assert result.is_error and "not a Git working tree" in result.output


@pytest.mark.parametrize("arguments", [{"staged": "false"}, {"path": ""}, {"path": 1}])
def test_diff_rejects_invalid_arguments(working_tree: Path, arguments: dict) -> None:
    assert GitDiffTool().execute(arguments, ToolContext(working_tree)).is_error


def test_git_output_is_visibly_truncated(working_tree: Path, monkeypatch) -> None:
    from ai_agent.tools import git as implementation

    monkeypatch.setattr(implementation, "MAX_OUTPUT_CHARS", 12)
    result = GitStatusTool().execute({}, ToolContext(working_tree))
    assert result.metadata["truncated"]
    assert "output truncated" in result.output
