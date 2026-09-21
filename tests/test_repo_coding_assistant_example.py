from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_EXAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "packages"
    / "ai_provider"
    / "examples"
    / "repo_coding_assistant.py"
)
sys.path.insert(0, str(_EXAMPLE_PATH.parent))
_SPEC = importlib.util.spec_from_file_location("repo_coding_assistant_example", _EXAMPLE_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_EXAMPLE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _EXAMPLE
_SPEC.loader.exec_module(_EXAMPLE)
build_repo_prompt = _EXAMPLE.build_repo_prompt
execute_actions = _EXAMPLE.execute_actions
extract_actions = _EXAMPLE.extract_actions
load_prompt_context = _EXAMPLE.load_prompt_context
AssistantAction = _EXAMPLE.AssistantAction


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
