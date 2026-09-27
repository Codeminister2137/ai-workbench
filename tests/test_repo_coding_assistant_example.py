from __future__ import annotations

import importlib.util
import sys
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from ai_provider.codex_mcp import CodexMcpSetupResult

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
parse_external_agent_jsonl = _EXAMPLE.parse_external_agent_jsonl
parse_response_scrutiny_report = _EXAMPLE.parse_response_scrutiny_report


class _AsciiTerminal(StringIO):
    encoding = "ascii"

    def write(self, text: str) -> int:
        text.encode(self.encoding)
        return super().write(text)


def test_tee_output_preserves_utf8_transcript_when_terminal_replaces_unicode() -> None:
    terminal = _AsciiTerminal()
    transcript = StringIO()
    tee = _TeeOutput(terminal, transcript)

    assert tee.write("Understand ↓ Inspect") == len("Understand ↓ Inspect")

    assert transcript.getvalue() == "Understand ↓ Inspect"
    assert terminal.getvalue() == "Understand ? Inspect"


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
    assert "--scrutinize-response" in result.stdout
    assert "--codex-search" in result.stdout
    assert "--codex-mcp-setup" in result.stdout
    assert "--codex-mcp-register-global" in result.stdout


def test_repo_assistant_script_uses_stable_package_entrypoint() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "repo-assistant.ps1"
    text = script.read_text(encoding="utf-8")

    assert "python -m uv run ai-assistant" in text
    assert "examples\\repo_coding_assistant.py" not in text
    assert "Add-DefaultLogFile" in text
    assert "repo-assistant-$timestamp.log" in text


def test_broad_analysis_script_keeps_canonical_manual_workflow() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "repo-assistant-broad-analysis.ps1"
    text = script.read_text(encoding="utf-8")

    assert '"--mode", "ask"' in text
    assert '"--execute"' in text
    assert '"--start-ollama"' in text
    assert '"--scrutinize-response"' in text
    assert '"--log-full-prompt"' in text
    assert "repo-assistant-broad-analysis-$timestamp.log" in text
    assert "ollama-broad-analysis-$timestamp.log" in text
    assert '"--log-file", $LogFile' in text
    assert '"--ollama-log-file", $OllamaLogFile' in text
    assert 'repo-assistant.ps1") @cliArgs' in text


def test_cli_modes_enforce_action_boundaries(capsys) -> None:
    assert main(["--mode", "diagnose"]) == 0
    diagnose_output = capsys.readouterr().out
    assert '"system"' in diagnose_output
    assert '"external_agents"' in diagnose_output

    with pytest.raises(SystemExit):
        main(["--mode", "implement", "make a change"])


def test_cli_can_setup_project_codex_mcp_without_prompt(
    tmp_path: Path,
    capsys,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()

    assert main(["--repo-root", str(repo_root), "--codex-mcp-setup"]) == 0

    output = capsys.readouterr().out
    config_file = repo_root / ".codex" / "config.toml"
    text = config_file.read_text(encoding="utf-8")
    assert "=== Codex MCP setup ===" in output
    assert f"repo_root: {repo_root.resolve()}" in output
    assert f"codex_mcp_config: {config_file}" in output
    assert "codex_mcp_server: repo_assistant_tools" in output
    assert "codex_mcp_enabled_tools_json:" in output
    assert "codex_mcp_global_registered: False" in output
    assert "[mcp_servers.repo_assistant_tools]" in text
    assert "ai-agent-mcp" in text
    assert "run_command" not in text


def test_cli_can_setup_and_register_codex_mcp_when_explicitly_requested(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()

    def fake_setup_project_codex_mcp(repo_root_arg: Path, *, register_global: bool):
        assert repo_root_arg == repo_root.resolve()
        assert register_global is True
        return CodexMcpSetupResult(
            config_path=repo_root / ".codex" / "config.toml",
            server_name="repo_assistant_tools",
            command="python",
            args=("-m", "uv", "run", "ai-agent-mcp"),
            enabled_tools=("read_file", "list_dir", "find_files", "grep_search"),
            created=True,
            global_registered=True,
            global_add_stdout="Added global MCP server.",
        )

    monkeypatch.setattr(_EXAMPLE, "setup_project_codex_mcp", fake_setup_project_codex_mcp)

    assert (
        main(["--repo-root", str(repo_root), "--codex-mcp-setup", "--codex-mcp-register-global"])
        == 0
    )

    output = capsys.readouterr().out
    assert "codex_mcp_global_registered: True" in output
    assert "codex_mcp_add_stdout: Added global MCP server." in output


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


def test_cli_log_file_captures_invocation_and_transcript(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("plan mode must not contact a provider")

    monkeypatch.setattr(_EXAMPLE, "create_chat_client", fail_if_called)
    log_file = tmp_path / "repo-assistant.log"

    assert (
        main(
            [
                "--mode",
                "plan",
                "Review CLI logging.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--log-file",
                str(log_file),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    text = log_file.read_text(encoding="utf-8")

    assert "=== CLI invocation ===" in text
    assert "timestamp_utc:" in text
    assert "cwd:" in text
    assert "Review CLI logging." in text
    assert '"--mode", "plan"' in text
    assert '"--log-file"' in text
    assert "=== Repo Coding Assistant ===" in text
    assert "execution_status: planned" in text
    assert "=== Run metrics ===" in text
    assert "total_wall_seconds:" in text
    assert "process_cpu_seconds:" in text
    assert "python_memory_peak_bytes:" in text
    assert "primary_elapsed_seconds:" in text
    assert "primary_usage_source: unavailable" in text
    assert "scrutiny_usage_source: unavailable" in text
    assert "=== Primary model input ===" not in text
    assert output == text


def test_cli_log_full_prompt_captures_assembled_model_input(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("plan mode must not contact a provider")

    monkeypatch.setattr(_EXAMPLE, "create_chat_client", fail_if_called)
    log_file = tmp_path / "repo-assistant.log"

    assert (
        main(
            [
                "--mode",
                "plan",
                "Review CLI full-prompt logging.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--log-file",
                str(log_file),
                "--log-full-prompt",
            ]
        )
        == 0
    )
    text = log_file.read_text(encoding="utf-8")

    assert "=== Primary model input ===" in text
    assert "system_prompt:" in text
    assert "user_prompt:" in text
    assert "# User request" in text
    assert "Review CLI full-prompt logging." in text
    assert "# Repository context" in text
    assert "AGENTS.md" in text
    assert capsys.readouterr().out == text


def test_log_full_prompt_requires_log_file() -> None:
    with pytest.raises(SystemExit):
        main(["--mode", "plan", "Review logging.", "--log-full-prompt"])


def test_cli_plans_codex_external_agent_route(capsys, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_COMMAND", "codex-test")

    assert (
        main(
            [
                "--mode",
                "plan",
                "Review this repository.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--skip-prompt-review",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "route_id: openai-codex-gpt-5-5" in output
    assert "access_method: codex_cli" in output
    assert "external_agent_command: codex-test" in output
    assert "external_agent_command_line_json:" in output
    assert "execution_status: planned" in output


def test_cli_executes_codex_external_agent_route(capsys, monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return _EXAMPLE.subprocess.CompletedProcess(
            args[0],
            0,
            "\n".join(
                [
                    '{"type":"command.started","command":"git status --short"}',
                    '{"type":"tool.completed","name":"read_file"}',
                    '{"type":"item.completed","item":{"type":"web_search","query":"OpenAI"}}',
                    '{"type":"file_change","path":"example.py"}',
                    '{"type":"turn.completed","usage":{"input_tokens":12,"output_tokens":3}}',
                    '{"type":"final_answer","content":"codex done"}',
                ]
            )
            + "\n",
            "",
        )

    monkeypatch.setenv("CODEX_COMMAND", "codex-test")
    monkeypatch.setattr(_EXAMPLE.subprocess, "run", fake_run)

    assert (
        main(
            [
                "--mode",
                "ask",
                "Review this repository.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--execute",
                "--skip-prompt-review",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "external_agent_returncode: 0" in output
    assert "external_agent_jsonl_events: parsed" in output
    assert "external_agent_command_event_count: 1" in output
    assert "external_agent_tool_event_count: 1" in output
    assert "external_agent_web_search_event_count: 1" in output
    assert "external_agent_file_change_event_count: 1" in output
    assert "external_agent_usage_json:" in output
    assert "codex done" in output
    assert "execution_status: completed" in output
    command = calls[0]["args"][0]
    assert command[:2] == ("codex-test", "exec")
    assert "--json" in command
    assert "--ask-for-approval" not in command
    assert "--sandbox" in command
    assert "workspace-write" in command
    assert calls[0]["kwargs"]["input"].startswith("# User request")
    assert calls[0]["kwargs"]["encoding"] == "utf-8"
    assert calls[0]["kwargs"]["errors"] == "replace"
    assert "# Repository context" in calls[0]["kwargs"]["input"]


def test_cli_can_plan_persistent_codex_session(capsys, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_COMMAND", "codex-test")

    assert (
        main(
            [
                "--mode",
                "plan",
                "Start a persistent Codex session.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--skip-prompt-review",
                "--codex-persist-session",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "external_agent_ephemeral: False" in output
    assert "--ephemeral" not in output
    assert "external_agent_command_line_json:" in output


def test_cli_can_plan_codex_resume_last(capsys, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_COMMAND", "codex-test")

    assert (
        main(
            [
                "--mode",
                "plan",
                "Resume Codex.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--skip-prompt-review",
                "--codex-resume",
                "last",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "external_agent_resume: last" in output
    assert '"resume", "--model", "gpt-5.5", "--json", "--last", "-"' in output
    assert "--ephemeral" not in output


def test_codex_persist_and_resume_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "--mode",
                "plan",
                "Invalid flags.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--skip-prompt-review",
                "--codex-persist-session",
                "--codex-resume",
                "last",
            ]
        )


def test_codex_session_flags_require_codex_route() -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "--mode",
                "plan",
                "Invalid route.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--codex-resume",
                "last",
            ]
        )


def test_external_agent_jsonl_parser_extracts_failure_and_final_answer() -> None:
    events = parse_external_agent_jsonl(
        "\n".join(
            [
                '{"type":"agent_message","role":"assistant","content":"intermediate"}',
                '{"type":"item.completed","item":{"type":"web_search","query":"OpenAI"}}',
                '{"type":"turn.failed","error":{"message":"sandbox denied"}}',
                '{"type":"final_answer","content":"last answer"}',
                "not-json",
            ]
        )
    )

    assert events.final_answer == "last answer"
    assert events.failure_reason == "sandbox denied"
    assert len(events.web_search_events) == 1
    assert events.parse_errors


def test_cli_does_not_print_raw_jsonl_when_codex_fails(capsys, monkeypatch) -> None:
    raw_jsonl = '{"type":"turn.failed","error":{"message":"unsupported model"}}\n'

    def fake_run(*args, **kwargs):
        return _EXAMPLE.subprocess.CompletedProcess(args[0], 1, raw_jsonl, "")

    monkeypatch.setenv("CODEX_COMMAND", "codex-test")
    monkeypatch.setattr(_EXAMPLE.subprocess, "run", fake_run)

    assert (
        main(
            [
                "--mode",
                "ask",
                "Review this repository.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--execute",
                "--skip-prompt-review",
            ]
        )
        == 1
    )

    output = capsys.readouterr().out
    assert "external_agent_failure_reason: unsupported model" in output
    assert "external_agent_final_answer: unavailable" in output
    assert raw_jsonl.strip() not in output


def test_external_agent_stderr_is_bounded() -> None:
    stderr = _EXAMPLE._format_external_agent_stderr("x" * 2500, limit=100)

    assert stderr.startswith("x" * 100)
    assert "external agent stderr truncated: 2400 characters omitted" in stderr
    assert len(stderr) < 200


def test_cli_preserves_raw_codex_jsonl_in_transcript_only(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    raw_jsonl = '{"type":"final_answer","content":"transcript answer"}\n'

    def fake_run(*args, **kwargs):
        return _EXAMPLE.subprocess.CompletedProcess(args[0], 0, raw_jsonl, "")

    monkeypatch.setenv("CODEX_COMMAND", "codex-test")
    monkeypatch.setattr(_EXAMPLE.subprocess, "run", fake_run)
    log_file = tmp_path / "codex.log"

    assert (
        main(
            [
                "--mode",
                "ask",
                "Review this repository.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--execute",
                "--skip-prompt-review",
                "--log-file",
                str(log_file),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    transcript = log_file.read_text(encoding="utf-8")
    assert "transcript answer" in output
    assert "=== External agent raw JSONL ===" not in output
    assert "=== External agent raw JSONL ===" in transcript
    assert raw_jsonl.strip() in transcript


def test_cli_can_use_codex_output_last_message_file(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    def fake_run(*args, **kwargs):
        output_index = args[0].index("--output-last-message") + 1
        Path(args[0][output_index]).write_text("last-message answer", encoding="utf-8")
        return _EXAMPLE.subprocess.CompletedProcess(
            args[0],
            0,
            '{"type":"turn.completed"}\n',
            "",
        )

    monkeypatch.setenv("CODEX_COMMAND", "codex-test")
    monkeypatch.setattr(_EXAMPLE.subprocess, "run", fake_run)
    output_file = tmp_path / "codex" / "last.txt"

    assert (
        main(
            [
                "--mode",
                "ask",
                "Review this repository.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--execute",
                "--skip-prompt-review",
                "--codex-output-last-message",
                str(output_file),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "external_agent_output_last_message:" in output
    assert "last-message answer" in output
    assert output_file.read_text(encoding="utf-8") == "last-message answer"


def test_cli_can_plan_codex_output_schema(capsys, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEX_COMMAND", "codex-test")
    schema_file = tmp_path / "answer.schema.json"
    schema_file.write_text('{"type":"object"}', encoding="utf-8")

    assert (
        main(
            [
                "--mode",
                "plan",
                "Return structured output.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--skip-prompt-review",
                "--codex-output-schema",
                str(schema_file),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "external_agent_output_schema:" in output
    assert "--output-schema" in output
    assert str(schema_file) in output


def test_cli_can_plan_codex_search(capsys, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_COMMAND", "codex-test")

    assert (
        main(
            [
                "--mode",
                "plan",
                "Search for current documentation.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--skip-prompt-review",
                "--codex-search",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "external_agent_web_search: True" in output
    assert '"codex-test", "--search", "exec"' in output
    assert '"exec", "--search"' not in output


def test_codex_output_schema_requires_codex_route(tmp_path: Path) -> None:
    schema_file = tmp_path / "answer.schema.json"
    schema_file.write_text('{"type":"object"}', encoding="utf-8")

    with pytest.raises(SystemExit):
        main(
            [
                "--mode",
                "plan",
                "Invalid route.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--codex-output-schema",
                str(schema_file),
            ]
        )


def test_codex_search_requires_codex_route() -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "--mode",
                "plan",
                "Invalid route.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--codex-search",
            ]
        )


def test_codex_capability_status_reports_expected_diagnostics(monkeypatch) -> None:
    def fake_run(command, *args, **kwargs):
        joined = tuple(command)
        if joined[1:] == ("--version",):
            return _EXAMPLE.subprocess.CompletedProcess(joined, 0, "codex-cli 0.137.0\n", "")
        if joined[1:] == ("login", "status"):
            return _EXAMPLE.subprocess.CompletedProcess(joined, 0, "Logged in using ChatGPT\n", "")
        if joined[1:] == ("exec", "--help"):
            return _EXAMPLE.subprocess.CompletedProcess(joined, 0, "--json\n", "")
        if joined[1:] == ("mcp", "list"):
            return _EXAMPLE.subprocess.CompletedProcess(
                joined,
                0,
                "No MCP servers configured yet.\n",
                "",
            )
        if joined[1:] == ("plugin", "list"):
            return _EXAMPLE.subprocess.CompletedProcess(
                joined,
                0,
                "\n".join(
                    [
                        "Marketplace `openai-curated`",
                        "C:\\codex\\marketplace.json",
                        "PLUGIN                 STATUS         VERSION  PATH",
                        "linear@openai-curated  not installed           C:\\codex\\plugins\\linear",
                        "github@openai-curated  installed, enabled  1.2.3    "
                        "C:\\codex\\plugins\\github",
                    ]
                ),
                "",
            )
        raise AssertionError(joined)

    monkeypatch.setattr(_EXAMPLE.subprocess, "run", fake_run)
    monkeypatch.delenv("CODEX_HOME", raising=False)

    status = _EXAMPLE._codex_capability_status("C:/codex/bin/codex.exe")

    assert status["version"] == "codex-cli 0.137.0"
    assert status["login_status"] == "Logged in using ChatGPT"
    assert status["exec_json_supported"] is True
    assert status["mcp_list"]["stdout"] == "No MCP servers configured yet."
    assert "linear@openai-curated" in status["plugin_list"]["stdout"]
    assert status["plugin_summary"]["marketplaces"] == ["openai-curated"]
    assert status["plugin_summary"]["available_count"] == 2
    assert status["plugin_summary"]["installed_count"] == 1
    assert status["plugin_summary"]["plugins"][0]["status"] == "not installed"
    assert status["plugin_summary"]["plugins"][1]["status"] == "installed, enabled"
    assert status["config_path"] == "C:\\codex\\config.toml"


def test_cli_can_install_codex_plugins_when_explicitly_executed(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, ...]] = []
    plugin_installed = False

    def fake_run(command, *args, **kwargs):
        nonlocal plugin_installed
        joined = tuple(command)
        calls.append(joined)
        if joined[1:] == ("plugin", "list"):
            row = (
                "github@openai-curated  installed, enabled  1.2.3    C:\\codex\\plugins\\github"
                if plugin_installed
                else "github@openai-curated  not installed           C:\\codex\\plugins\\github"
            )
            return _EXAMPLE.subprocess.CompletedProcess(
                joined,
                0,
                "\n".join(
                    [
                        "Marketplace `openai-curated`",
                        "C:\\codex\\marketplace.json",
                        "PLUGIN                 STATUS         VERSION  PATH",
                        row,
                    ]
                ),
                "",
            )
        if joined[1:] == ("plugin", "add", "github@openai-curated"):
            return _EXAMPLE.subprocess.CompletedProcess(joined, 0, "installed\n", "")
        raise AssertionError(joined)

    monkeypatch.setenv("CODEX_COMMAND", "codex")
    monkeypatch.setattr(_EXAMPLE.subprocess, "run", fake_run)

    def fake_plugin_operation(command, *, action, selector, timeout_seconds=60.0):
        nonlocal plugin_installed
        plugin_command = (command, "plugin", action, selector)
        calls.append(plugin_command)
        plugin_installed = action == "add"
        return SimpleNamespace(
            ok=True,
            returncode=0,
            stdout="installed",
            stderr="",
        )

    monkeypatch.setattr(_EXAMPLE, "run_codex_plugin_operation", fake_plugin_operation)

    exit_code = main(
        [
            "--repo-root",
            str(tmp_path),
            "--codex-plugin-install",
            "github@openai-curated",
            "--execute",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert ("codex", "plugin", "add", "github@openai-curated") in calls
    assert "codex_plugin_auth_boundary: install/remove only; no OAuth" in output
    assert "codex_plugin_expected_status_json:" in output
    assert "codex_plugin_next_step: start a new Codex CLI session" in output
    assert "execution_status: completed" in output


def test_cli_can_scrutinize_completed_response(capsys, monkeypatch) -> None:
    from dataclasses import replace

    from ai_provider import (
        AIMessage,
        AIResponse,
        BackendInfo,
        MessageRole,
    )
    from ai_provider import (
        BackendLocation as ProviderBackendLocation,
    )

    catalog = _EXAMPLE.load_model_catalog(
        Path("packages/ai_orchestrator/examples/model_catalog.toml")
    )
    prepared = _EXAMPLE.run_coding_prompt(
        "Investigate the next action for this repository.",
        _EXAMPLE.coding_task_profile(model_override="qwen2.5-coder:14b"),
        catalog,
    )
    primary = replace(
        prepared,
        response=AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, "primary answer"),
            backend=BackendInfo(
                provider="ollama",
                model="qwen2.5-coder:14b",
                location=ProviderBackendLocation.LOCAL,
            ),
        ),
    )
    scrutiny = replace(
        primary,
        response=AIResponse(
            message=AIMessage(
                MessageRole.ASSISTANT,
                "\n".join(
                    [
                        "VERDICT: needs_revision",
                        "SCORE: 4",
                        "STRENGTHS: names the relevant command",
                        "ISSUES: generic answer",
                        "RECOMMENDED_NEXT_ACTION: revise the answer",
                        "REVISED_RESPONSE:",
                        "Use the canonical command and inspect its logs.",
                    ]
                ),
            ),
            backend=BackendInfo(
                provider="ollama",
                model="qwen2.5-coder:14b",
                location=ProviderBackendLocation.LOCAL,
            ),
        ),
    )
    calls: list[tuple[str, bool, str | None]] = []

    def fake_run(prompt, profile, catalog, **kwargs):
        calls.append((prompt, kwargs["execute"], kwargs.get("system_prompt")))
        return primary if len(calls) == 1 else scrutiny

    monkeypatch.setattr(_EXAMPLE, "run_coding_prompt", fake_run)

    assert (
        main(
            [
                "--mode",
                "ask",
                "Investigate the next action for this repository.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--execute",
                "--scrutinize-response",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "=== Assistant response ===" in output
    assert "primary answer" in output
    assert "=== Response scrutiny ===" in output
    assert "VERDICT: needs_revision" in output
    assert "scrutiny_verdict: needs_revision" in output
    assert "scrutiny_score: 4" in output
    assert "scrutiny_status: completed" in output
    assert "execution_status: completed_with_scrutiny_findings" in output
    assert len(calls) == 2
    assert calls[1][1] is True
    assert "Candidate assistant response:\nprimary answer" in calls[1][0]
    assert calls[1][2] == _EXAMPLE._RESPONSE_SCRUTINY_SYSTEM_PROMPT


def test_parse_response_scrutiny_report_validates_required_shape() -> None:
    report = parse_response_scrutiny_report(
        "\n".join(
            [
                "### **Verdict:** PASS",
                "### **SCORE:** 8",
                "### **STRENGTHS:**",
                "Grounded.",
                "### **ISSUES:**",
                "None.",
                "### **RECOMMENDED NEXT ACTION:** Keep answer.",
                "### **REVISED RESPONSE:**",
                "Original answer is acceptable.",
            ]
        )
    )

    assert report.verdict == "pass"
    assert report.score == 8
    assert report.strengths == "Grounded."
    assert report.issues == "None."
    assert report.revised_response == "Original answer is acceptable."


def test_parse_response_scrutiny_report_accepts_fenced_json_object() -> None:
    report = parse_response_scrutiny_report(
        """```json
{
  "VERDICT": "pass",
  "SCORE": 9,
  "STRENGTHS": ["names concrete files"],
  "ISSUES": ["needs one more validation step"],
  "RECOMMENDED_NEXT_ACTION": [{"type": "run_command", "command": "pytest"}],
  "REVISED_RESPONSE": null
}
```"""
    )

    assert report.verdict == "pass"
    assert report.score == 9
    assert "names concrete files" in report.strengths
    assert "run_command" in report.recommended_next_action
    assert report.revised_response == ""


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("VERDICT: pass\nSCORE: 5", "missing scrutiny heading"),
        (
            "\n".join(
                [
                    "VERDICT: maybe",
                    "SCORE: 5",
                    "STRENGTHS:",
                    "ISSUES:",
                    "RECOMMENDED_NEXT_ACTION:",
                    "REVISED_RESPONSE:",
                ]
            ),
            "invalid scrutiny verdict",
        ),
        (
            "\n".join(
                [
                    "VERDICT: pass",
                    "SCORE: 11",
                    "STRENGTHS:",
                    "ISSUES:",
                    "RECOMMENDED_NEXT_ACTION:",
                    "REVISED_RESPONSE:",
                ]
            ),
            "scrutiny score out of range",
        ),
    ],
)
def test_parse_response_scrutiny_report_rejects_invalid_reports(
    content: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        parse_response_scrutiny_report(content)


def test_cli_marks_malformed_scrutiny_as_scrutiny_error(capsys, monkeypatch) -> None:
    from dataclasses import replace

    from ai_provider import (
        AIMessage,
        AIResponse,
        BackendInfo,
        MessageRole,
    )
    from ai_provider import (
        BackendLocation as ProviderBackendLocation,
    )

    catalog = _EXAMPLE.load_model_catalog(
        Path("packages/ai_orchestrator/examples/model_catalog.toml")
    )
    prepared = _EXAMPLE.run_coding_prompt(
        "Investigate the next action for this repository.",
        _EXAMPLE.coding_task_profile(model_override="qwen2.5-coder:14b"),
        catalog,
    )
    primary = replace(
        prepared,
        response=AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, "primary answer"),
            backend=BackendInfo(
                provider="ollama",
                model="qwen2.5-coder:14b",
                location=ProviderBackendLocation.LOCAL,
            ),
        ),
    )
    scrutiny = replace(
        primary,
        response=AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, "VERDICT: pass\nSCORE: 8"),
            backend=BackendInfo(
                provider="ollama",
                model="qwen2.5-coder:14b",
                location=ProviderBackendLocation.LOCAL,
            ),
        ),
    )
    calls = 0

    def fake_run(prompt, profile, catalog, **kwargs):
        nonlocal calls
        calls += 1
        return primary if calls == 1 else scrutiny

    monkeypatch.setattr(_EXAMPLE, "run_coding_prompt", fake_run)

    assert (
        main(
            [
                "--mode",
                "ask",
                "Investigate the next action for this repository.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--execute",
                "--scrutinize-response",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "scrutiny_status: invalid" in output
    assert "scrutiny_failure_reason: missing scrutiny heading" in output
    assert "execution_status: completed_with_scrutiny_errors" in output


def test_scrutiny_requires_executing_ask_or_review() -> None:
    with pytest.raises(SystemExit):
        main(["--mode", "ask", "Review code.", "--scrutinize-response"])

    with pytest.raises(SystemExit):
        main(["--mode", "plan", "Review code.", "--execute", "--scrutinize-response"])


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


@pytest.mark.parametrize(
    ("delegation_status", "expected_output"),
    [
        ("accepted: ollama-qwen2.5-coder:14b", "delegation: accepted: ollama-qwen2.5-coder:14b"),
        ("rejected: unsuitable task", "delegation: rejected: unsuitable task"),
    ],
)
def test_cli_reports_delegation_decision(
    delegation_status: str,
    expected_output: str,
    capsys,
    monkeypatch,
) -> None:
    from dataclasses import replace

    from ai_provider import (
        AIMessage,
        AIResponse,
        BackendInfo,
        MessageRole,
    )
    from ai_provider import (
        BackendLocation as ProviderBackendLocation,
    )

    catalog = _EXAMPLE.load_model_catalog(
        Path("packages/ai_orchestrator/examples/model_catalog.toml")
    )
    prepared = _EXAMPLE.run_coding_prompt(
        "Review the selected implementation.",
        _EXAMPLE.coding_task_profile(model_override="qwen2.5-coder:14b"),
        catalog,
    )
    prepared = replace(
        prepared,
        response=AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, "review complete"),
            backend=BackendInfo(
                provider="ollama",
                model="qwen2.5-coder:14b",
                location=ProviderBackendLocation.LOCAL,
            ),
        ),
    )
    monkeypatch.setattr(
        _EXAMPLE,
        "run_local_context_delegation",
        lambda *args, **kwargs: ("delegated facts", delegation_status),
    )
    monkeypatch.setattr(_EXAMPLE, "run_coding_prompt", lambda *args, **kwargs: prepared)

    assert (
        main(
            [
                "--mode",
                "review",
                "Review the selected implementation.",
                "--delegate-context",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--execute",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert expected_output in output
    assert "execution_status: completed" in output


def test_review_mode_rejects_native_tools_before_provider_contact(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("invalid review mode must stop before provider contact")

    monkeypatch.setattr(_EXAMPLE, "create_chat_client", fail_if_called)

    with pytest.raises(SystemExit):
        main(["--mode", "review", "Review code.", "--native-tools"])


def test_stable_ai_assistant_entry_point_loads_cli() -> None:
    from ai_provider.cli import main as stable_main

    assert stable_main(["--mode", "plan", "Review code.", "--provider", "ollama"]) == 0


def test_stable_cli_reports_provider_failures(capsys, monkeypatch) -> None:
    from ai_provider import ProviderError
    from ai_provider import repo_coding_assistant as stable_cli

    def fail_request(*args, **kwargs):
        raise ProviderError("provider unavailable")

    monkeypatch.setattr(stable_cli, "run_coding_prompt", fail_request)

    assert (
        stable_cli.main(
            [
                "--mode",
                "ask",
                "Review code.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--execute",
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    assert "status: failed" in output
    assert "failure_reason: provider unavailable" in output
    assert "execution_status: failed" in output


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
