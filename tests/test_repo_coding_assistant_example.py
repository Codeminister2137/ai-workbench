from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

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
main = _EXAMPLE.main
build_delegation_context = _EXAMPLE.build_delegation_context
run_local_context_delegation = _EXAMPLE.run_local_context_delegation
_run_native_agent = _EXAMPLE._run_native_agent
_TeeOutput = _EXAMPLE._TeeOutput
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


def test_build_delegation_context_adds_source_line_numbers() -> None:
    context_file = _EXAMPLE.RepoContextFile(
        path=Path("src.py"),
        display_path="src.py",
        content="first\nsecond",
        inside_repo=True,
    )

    context, sources = build_delegation_context((context_file,))

    assert sources == ("src.py",)
    assert "=== SOURCE: src.py ===" in context
    assert "1: first" in context
    assert "2: second" in context


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


def test_cli_help_lists_google_provider() -> None:
    result = __import__("subprocess").run(
        [
            sys.executable,
            str(_EXAMPLE_PATH),
            "--help",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--provider {ollama,openai,requesty,google}" in result.stdout
    assert "--mode {ask,review,implement,plan,diagnose}" in result.stdout


def test_cli_modes_enforce_action_boundaries(capsys) -> None:
    assert main(["--mode", "diagnose"]) == 0
    assert '"system"' in capsys.readouterr().out

    with pytest.raises(SystemExit):
        main(["--mode", "implement", "make a change"])


def test_plan_mode_does_not_create_a_provider_client(capsys, monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("plan mode must not contact a provider")

    monkeypatch.setattr(_EXAMPLE, "create_chat_client", fail_if_called)

    assert (
        main(
            [
                "--mode",
                "plan",
                "Review the selected implementation.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "mode: plan" in output
    assert "status: ready" in output
    assert "delegation: disabled" in output
    assert "execution_status: planned" in output


def test_delegate_context_requires_execution_before_provider_contact(capsys, monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("dry-run delegation must not contact a provider")

    monkeypatch.setattr(_EXAMPLE, "create_chat_client", fail_if_called)

    assert (
        main(
            [
                "--mode",
                "ask",
                "Review the selected implementation.",
                "--delegate-context",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
            ]
        )
        == 0
    )
    assert "delegation: planned: requires --execute" in capsys.readouterr().out


def test_review_mode_rejects_native_tools_before_provider_contact(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("invalid review mode must stop before provider contact")

    monkeypatch.setattr(_EXAMPLE, "create_chat_client", fail_if_called)

    with pytest.raises(SystemExit):
        main(["--mode", "review", "Review code.", "--native-tools"])


def test_stable_ai_assistant_entry_point_loads_cli() -> None:
    from ai_provider.cli import main as stable_main

    assert stable_main(["--mode", "plan", "Review code.", "--provider", "ollama"]) == 0


class _NativeFakeClient:
    def __init__(self) -> None:
        from ai_provider import BackendInfo, BackendLocation

        self.backend = BackendInfo(provider="ollama", model="test", location=BackendLocation.LOCAL)
        self.calls = 0

    def complete(self, request):
        from ai_provider import AIMessage, AIResponse, AIToolCall, FinishReason, MessageRole

        self.calls += 1
        if self.calls == 1:
            message = AIMessage(
                MessageRole.ASSISTANT,
                "",
                tool_calls=(
                    AIToolCall(
                        "call-1",
                        "create_file",
                        {"path": "native.txt", "content": "native"},
                    ),
                ),
            )
        else:
            message = AIMessage(MessageRole.ASSISTANT, "native complete")
        return AIResponse(
            message=message,
            backend=self.backend,
            finish_reason=FinishReason.STOP,
        )

    def stream(self, request):
        raise NotImplementedError


def test_native_agent_mode_executes_provider_tool_calls(tmp_path: Path, monkeypatch) -> None:
    from ai_orchestrator import PrivacyClass as OrchestratorPrivacyClass

    coding_task_profile = _EXAMPLE.coding_task_profile
    from ai_provider import BackendConfig, ProviderKind

    client = _NativeFakeClient()
    monkeypatch.setattr(_EXAMPLE, "create_chat_client", lambda config: client)
    monkeypatch.setattr("builtins.input", lambda prompt: "yes")
    args = type(
        "Args",
        (),
        {
            "start_ollama": False,
            "ollama_command": "ollama",
            "ollama_startup_timeout_seconds": 1.0,
            "system": None,
            "max_action_rounds": 3,
        },
    )()
    profile = coding_task_profile(privacy_class=OrchestratorPrivacyClass.LOCAL_ONLY)
    result = _run_native_agent(
        "Create native.txt",
        BackendConfig(provider=ProviderKind.OLLAMA, model="test"),
        profile,
        args,
        tmp_path,
    )

    assert result.response.message.content == "native complete"
    assert (tmp_path / "native.txt").read_text(encoding="utf-8") == "native"
    assert result.tool_results[0].is_error is False


def test_tee_output_writes_to_terminal_and_transcript() -> None:
    from io import StringIO

    terminal = StringIO()
    transcript = StringIO()
    output = _TeeOutput(terminal, transcript)

    output.write("assistant output\n")
    output.flush()

    assert terminal.getvalue() == "assistant output\n"
    assert transcript.getvalue() == "assistant output\n"
