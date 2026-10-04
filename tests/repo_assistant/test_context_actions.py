"""Repo-assistant context actions regression contracts."""

from __future__ import annotations

from pathlib import Path

from .support import (
    _EXAMPLE,
    AssistantAction,
    build_repo_prompt,
    execute_actions,
    extract_actions,
    load_prompt_context,
)


def test_load_prompt_context_loads_default_and_selected_repo_files(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "AGENTS.md").write_text("agent rules", encoding="utf-8")
    (repo_root / "CURRENT_CONTEXT.md").write_text("handoff", encoding="utf-8")
    (repo_root / "src.py").write_text("print('hello')", encoding="utf-8")

    context = load_prompt_context(repo_root, [Path("src.py")])

    assert [item.display_path for item in context] == [
        "AGENTS.md",
        "CURRENT_CONTEXT.md",
        "src.py",
    ]
    assert [item.content for item in context] == ["agent rules", "handoff", "print('hello')"]
    assert all(item.inside_repo for item in context)


def test_load_prompt_context_asks_before_outside_repo_file(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside context", encoding="utf-8")
    prompts: list[str] = []

    context = load_prompt_context(
        repo_root,
        [outside],
        input_func=lambda prompt: prompts.append(prompt) or "yes",
    )

    assert prompts == [f"Read file outside repository? {outside.resolve()} [y/N]: "]
    assert len(context) == 1
    assert context[0].content == "outside context"
    assert context[0].inside_repo is False


def test_load_prompt_context_skips_denied_outside_repo_file(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside context", encoding="utf-8")

    context = load_prompt_context(
        repo_root,
        [outside],
        input_func=lambda prompt: "no",
    )

    assert context == ()


def test_load_prompt_context_applies_total_and_per_file_budgets(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "AGENTS.md").write_text("A" * 100, encoding="utf-8")
    (repo_root / "CURRENT_CONTEXT.md").write_text("B" * 100, encoding="utf-8")
    (repo_root / "src.py").write_text("C" * 100, encoding="utf-8")

    context = load_prompt_context(
        repo_root,
        [Path("src.py")],
        context_budget_chars=80,
        context_file_budget_chars=50,
    )

    assert sum(len(item.content) for item in context) <= 80
    assert len(context[0].content) <= 50
    assert "context truncated" in context[0].content


def test_limit_context_content_preserves_file_edges() -> None:
    content = "HEAD" + ("x" * 100) + "TAIL"

    limited = _EXAMPLE._limit_context_content(content, 40)

    assert limited.startswith("HEAD")
    assert limited.endswith("TAIL")
    assert "context truncated" in limited


def test_context_reports_instruction_truncation_and_budget_omissions(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("required rule\n" * 20)
    (tmp_path / "CURRENT_CONTEXT.md").write_text("handoff")
    warnings: list[str] = []
    loaded = load_prompt_context(
        tmp_path,
        [],
        context_budget_chars=40,
        context_file_budget_chars=40,
        diagnostic=warnings.append,
    )
    assert len(loaded) == 1
    assert warnings[0].startswith("context_file_truncated: AGENTS.md")
    assert warnings[1] == "context_budget_omitted: CURRENT_CONTEXT.md"


def test_selected_file_loads_nested_instructions_in_scope_order(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("root rules")
    package = tmp_path / "package"
    package.mkdir()
    (package / "AGENTS.md").write_text("package rules")
    child = package / "child"
    child.mkdir()
    (child / "AGENTS.md").write_text("child rules")
    source = child / "source.py"
    source.write_text("value = 1")
    loaded = load_prompt_context(tmp_path, [source, source])
    assert [item.path for item in loaded] == [
        tmp_path / "AGENTS.md",
        package / "AGENTS.md",
        child / "AGENTS.md",
        source,
    ]


def test_outside_file_does_not_implicitly_load_its_neighbor_instructions(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("explicitly approved")
    (tmp_path / "AGENTS.md").write_text("outside rules must not be implicitly read")
    loaded = load_prompt_context(root, [outside], allow_outside_files=True)
    assert [item.path for item in loaded] == [outside]


def test_build_repo_prompt_marks_context_boundaries(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    source = repo_root / "src.py"
    source.write_text("print('hello')", encoding="utf-8")
    context = load_prompt_context(repo_root, [source])

    prompt = build_repo_prompt("Explain the code.", context)

    assert "# User request\nExplain the code." in prompt
    assert "## src.py (inside-repo)" in prompt
    assert "print('hello')" in prompt


def test_extract_actions_from_json_block() -> None:
    actions = extract_actions(
        """
Use a tool:

```json
{"actions":[{"type":"read_file","path":"README.md"}]}
```
"""
    )

    assert actions == (AssistantAction(action_type="read_file", args={"path": "README.md"}),)


def test_execute_actions_reads_and_writes_inside_repo(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    source = repo_root / "source.txt"
    source.write_text("source content", encoding="utf-8")

    results = execute_actions(
        (
            AssistantAction(action_type="read_file", args={"path": "source.txt"}),
            AssistantAction(
                action_type="write_file",
                args={"path": "generated.txt", "content": "generated content"},
            ),
        ),
        repo_root,
    )

    assert [result.ok for result in results] == [True, True]
    assert results[0].output == "source content"
    assert (repo_root / "generated.txt").read_text(encoding="utf-8") == "generated content"


def test_execute_actions_asks_before_outside_write(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    outside = tmp_path / "outside.txt"
    prompts: list[str] = []

    results = execute_actions(
        (
            AssistantAction(
                action_type="write_file",
                args={"path": str(outside), "content": "outside content"},
            ),
        ),
        repo_root,
        input_func=lambda prompt: prompts.append(prompt) or "no",
    )

    assert len(prompts) == 1
    assert results[0].ok is False
    assert not outside.exists()


def test_execute_actions_runs_command_in_repo(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    results = execute_actions(
        (
            AssistantAction(
                action_type="run_command",
                args={"command": "python -c \"print('hello')\""},
            ),
        ),
        repo_root,
    )

    assert results[0].ok is True
    assert "hello" in results[0].output


def test_execute_actions_can_be_blocked_by_approval_policy(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    results = execute_actions(
        (
            AssistantAction(
                action_type="write_file",
                args={"path": "generated.txt", "content": "generated content"},
            ),
        ),
        repo_root,
        authorize_action=lambda action: action.action_type != "write_file",
    )

    assert results[0].ok is False
    assert results[0].summary == "Skipped by approval policy: write_file"
    assert not (repo_root / "generated.txt").exists()
