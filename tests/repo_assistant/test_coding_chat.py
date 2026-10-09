"""Continuous coding must retain decisions, observed failures and recovery boundaries."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest
from ai_agent.coding_chat import (
    CodingChatController,
    CodingChatInputError,
    CodingTurnRequest,
    CodingTurnResult,
    run_terminal_conversation,
)
from ai_agent.coding_chat_cli import run_coding_chat
from ai_agent.repo_assistant_args import build_argument_parser
from ai_provider.chat_transcripts import SQLiteChatTranscriptStore
from ai_provider.coding_sessions import ACTIVE_SESSION
from ai_provider.foreground_tools import ACTIVE_FOREGROUND

from .support import _EXAMPLE, main


def controller(tmp_path: Path, budget: int = 64_000) -> CodingChatController:
    store = SQLiteChatTranscriptStore(tmp_path / "conversation.sqlite3")
    CodingChatController.create(store, "conversation", tmp_path, "local_only", "Test")
    return CodingChatController(
        store, "conversation", tmp_path, "local_only", history_budget_chars=budget
    )


def test_followup_preserves_owner_decisions_and_failed_validation(tmp_path: Path) -> None:
    chat = controller(tmp_path)
    requests: list[CodingTurnRequest] = []

    def execute(request: CodingTurnRequest) -> CodingTurnResult:
        requests.append(request)
        return CodingTurnResult(1, "I believe the implementation is correct", "validation_failed")

    chat.turn("Keep privacy inherited. Do not add dependencies.", execute)
    chat.turn("Fix the failing edge case without changing that decision.", execute)
    assert "Keep privacy inherited" in requests[1].history
    assert "Do not add dependencies" in requests[1].history
    assert "validation_failed" in requests[1].history
    assert "not current file state" in requests[1].history
    assert requests[0].message_id != requests[1].message_id
    assert [m.role for m in chat.store.list_messages("conversation")] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_budget_refuses_before_execution_without_losing_history(tmp_path: Path) -> None:
    chat = controller(tmp_path, budget=500)
    chat.turn("A" * 450, lambda request: CodingTurnResult(0, "result", "completed"))
    before = chat.store.list_messages("conversation")
    with pytest.raises(CodingChatInputError, match="No turn was executed"):
        chat.turn("Continue", lambda request: pytest.fail("must not execute over budget"))
    assert chat.store.list_messages("conversation") == before


@pytest.mark.parametrize("failure", [KeyboardInterrupt, RuntimeError, ValueError])
def test_interruption_retains_turn_and_uncertainty(tmp_path: Path, failure: type[BaseException]):
    chat = controller(tmp_path)

    def execute(request: CodingTurnRequest) -> CodingTurnResult:
        (tmp_path / "partial.txt").write_text("partial", encoding="utf-8")
        raise failure()

    with pytest.raises(failure):
        chat.turn("Make the approved edit", execute)
    messages = chat.store.list_messages("conversation")
    assert messages[-1].metadata is not None
    assert messages[-1].metadata["execution_status"] == "interrupted"
    assert "do not replay" in messages[-1].content
    assert (tmp_path / "partial.txt").read_text(encoding="utf-8") == "partial"


def test_terminal_handles_multiline_blank_status_and_eof(tmp_path: Path) -> None:
    chat = controller(tmp_path)
    inputs = iter(["", "/status", "/multiline", "/a/path", "second line", "."])
    requests: list[CodingTurnRequest] = []
    output: list[str] = []

    def read(prompt: str) -> str:
        try:
            return next(inputs)
        except StopIteration as exc:
            raise EOFError from exc

    def execute(request: CodingTurnRequest) -> CodingTurnResult:
        requests.append(request)
        return CodingTurnResult(0, "done", "completed")

    assert run_terminal_conversation(chat, execute, read=read, write=output.append) == 0
    assert [r.text for r in requests] == ["/a/path\nsecond line"]
    assert "coding_session_id: conversation" in output


def test_terminal_does_not_swallow_executor_value_error(tmp_path: Path) -> None:
    chat = controller(tmp_path)

    def execute(request: CodingTurnRequest) -> CodingTurnResult:
        raise ValueError("broken execution contract")

    with pytest.raises(ValueError, match="broken execution"):
        run_terminal_conversation(chat, execute, initial_prompt="Act", write=lambda text: None)


def test_restart_checks_workspace_privacy_and_session_kind(tmp_path: Path) -> None:
    chat = controller(tmp_path)
    chat.turn("Original decision", lambda request: CodingTurnResult(0, "retained", "completed"))
    resumed = CodingChatController(chat.store, "conversation", tmp_path, "local_only")
    assert "Original decision" in resumed.history()
    with pytest.raises(ValueError, match="workspace"):
        CodingChatController(chat.store, "conversation", tmp_path / "other", "local_only")
    with pytest.raises(ValueError, match="privacy"):
        CodingChatController(chat.store, "conversation", tmp_path, "external_allowed")
    ordinary = chat.store.create_session(
        repo_root=tmp_path, title="plain", privacy_class="local_only"
    )
    with pytest.raises(ValueError, match="not a coding"):
        CodingChatController(chat.store, ordinary.session_id, tmp_path, "local_only")


def arguments(tmp_path: Path, *options: str) -> argparse.Namespace:
    return build_argument_parser().parse_args(
        ["--mode", "coding-chat", "--execute", "--repo-root", str(tmp_path), *options]
    )


def test_cli_keeps_one_foreground_owner_fresh_turn_args_and_unique_logs(tmp_path, monkeypatch):
    prompts = iter(["First decision", "Implement with that decision", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(prompts))
    owners = []
    sessions = []
    turns = []

    def execute(args, config):
        owners.append(ACTIVE_FOREGROUND.get())
        sessions.append(ACTIVE_SESSION.get())
        turns.append(args)
        args._coding_chat_observer(CodingTurnResult(0, f"response {len(turns)}", "completed"))
        args.prompt = "executor mutation must not leak"
        return 0

    args = arguments(tmp_path, "--log-file", str(tmp_path / "transcript.txt"))
    assert run_coding_chat(args, build_argument_parser(), execute) == 0
    assert owners[0] is owners[1] and owners[0] is not None
    assert sessions[0] is sessions[1] and sessions[0] is not None
    assert turns[0] is not turns[1]
    assert turns[0].log_file != turns[1].log_file
    assert "First decision" in turns[1]._coding_chat_history
    assert "response 1" in turns[1]._coding_chat_history
    assert args.prompt is None
    assert ACTIVE_FOREGROUND.get() is None
    assert ACTIVE_SESSION.get() is None


@pytest.mark.parametrize(
    "option",
    [
        ["--codex-login"],
        ["--chat-session", "last"],
        ["--no-native-tools"],
        ["--shared-tools", "inspection"],
        ["--coding-chat-history-budget-chars", "-1"],
    ],
)
def test_invalid_chat_configuration_refuses_before_storage_or_execution(tmp_path, option):
    with pytest.raises(SystemExit):
        run_coding_chat(
            arguments(tmp_path, *option),
            build_argument_parser(),
            lambda args, config: pytest.fail("invalid configuration must not execute"),
        )
    assert not (tmp_path / "data").exists()


def test_cli_restart_preserves_history_and_refuses_unreconciled_interruption(tmp_path, monkeypatch):
    def interrupted(args, config):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", lambda prompt: "Edit the file")
    assert run_coding_chat(arguments(tmp_path), build_argument_parser(), interrupted) == 130
    store = SQLiteChatTranscriptStore(tmp_path / "data/repo-assistant-chats.sqlite3")
    session = store.latest_session(repo_root=tmp_path)
    assert session is not None
    assert (
        run_coding_chat(
            arguments(tmp_path, "--coding-session", session.session_id),
            build_argument_parser(),
            lambda args, config: pytest.fail("must not execute unreconciled effects"),
        )
        == 1
    )
    prompts = iter(["Continue after inspecting effects", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(prompts))
    captured = []

    def resumed(args, config):
        captured.append(args._coding_chat_history)
        args._coding_chat_observer(CodingTurnResult(0, "recovered", "completed"))
        return 0

    assert (
        run_coding_chat(
            arguments(
                tmp_path, "--coding-session", session.session_id, "--coding-session-reconciled"
            ),
            build_argument_parser(),
            resumed,
        )
        == 0
    )
    assert "Edit the file" in captured[0]
    assert "interrupted" in captured[0]


def test_actual_cli_native_turns_refresh_files_and_retain_conversation(tmp_path, monkeypatch):
    from ai_provider import AIMessage, AIResponse, BackendInfo, BackendLocation, MessageRole

    source = tmp_path / "module.py"
    source.write_text("before = 1\n", encoding="utf-8")
    requests = []

    class Client:
        backend = BackendInfo("ollama", "gpt-oss:20b", BackendLocation.LOCAL)

        def complete(self, request):
            requests.append(request)
            if len(requests) == 1:
                source.write_text("after = 2\n", encoding="utf-8")
            return AIResponse(
                AIMessage(MessageRole.ASSISTANT, f"Answer {len(requests)}"), self.backend
            )

    monkeypatch.setattr(_EXAMPLE, "create_chat_client", lambda config: Client())
    inputs = iter(["Explain the updated source and remember my constraint", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))
    assert (
        main(
            [
                "--repo-root",
                str(tmp_path),
                "--mode",
                "coding-chat",
                "--execute",
                "--provider",
                "ollama",
                "--model",
                "gpt-oss:20b",
                "--skip-prompt-review",
                "--file",
                "module.py",
                "Do not add dependencies. Explain this source.",
            ]
        )
        == 0
    )
    assert len(requests) == 2
    first = "\n".join(m.content for m in requests[0].messages)
    second = "\n".join(m.content for m in requests[1].messages)
    assert "before = 1" in first
    assert "after = 2" in second
    assert "before = 1" not in second
    assert "Do not add dependencies" in second
    assert "Answer 1" in second


def test_actual_cli_closeout_observation_is_structured_not_console_parsing(tmp_path, monkeypatch):
    inputs = iter(["Follow up", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))
    seen = []

    def executor(argv=None, *, parsed_args=None, user_config_override=None):
        assert parsed_args is not None
        seen.append(parsed_args)
        print("unrelated console diagnostics: status completed")
        _EXAMPLE._print_cli_closeout(
            args=parsed_args,
            response_text="Review says pass",
            status="ready",
            execution_status="validation_failed",
            failure_reason="edge-case test failed",
        )
        return 1

    monkeypatch.setattr(_EXAMPLE, "_main", executor)
    assert (
        main(
            [
                "--repo-root",
                str(tmp_path),
                "--mode",
                "coding-chat",
                "--execute",
                "Fix the bug",
            ]
        )
        == 1
    )
    assert "validation_failed" in seen[1]._coding_chat_history
    assert "edge-case test failed" in seen[1]._coding_chat_history
    assert '"returncode": 1' in seen[1]._coding_chat_history
    assert "unrelated console" not in seen[1]._coding_chat_history


def test_actual_coding_chat_uses_real_tools_and_requires_fresh_approval(tmp_path, monkeypatch):
    from ai_provider import (
        AIMessage,
        AIResponse,
        AIToolCall,
        BackendInfo,
        BackendLocation,
        MessageRole,
    )

    calls = []

    class Client:
        backend = BackendInfo("ollama", "gpt-oss:20b", BackendLocation.LOCAL)

        def complete(self, request):
            calls.append(request)
            if len(calls) in {1, 3}:
                path = "approved.txt" if len(calls) == 1 else "denied.txt"
                message = AIMessage(
                    MessageRole.ASSISTANT,
                    "",
                    tool_calls=(
                        AIToolCall(
                            f"call-{len(calls)}", "create_file", {"path": path, "content": "effect"}
                        ),
                    ),
                )
            else:
                message = AIMessage(MessageRole.ASSISTANT, f"Report {len(calls)}")
            return AIResponse(message, self.backend)

    monkeypatch.setattr(_EXAMPLE, "create_chat_client", lambda config: Client())
    answers = iter(["yes", "Try another edit", "no", "/exit"])
    prompts = []

    def read(prompt):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr("builtins.input", read)
    main(
        [
            "--mode",
            "coding-chat",
            "--execute",
            "--repo-root",
            str(tmp_path),
            "--provider",
            "ollama",
            "--model",
            "gpt-oss:20b",
            "--skip-prompt-review",
            "--approval-policy",
            "interactive",
            "Create the approved file",
        ]
    )
    assert (tmp_path / "approved.txt").read_text(encoding="utf-8") == "effect"
    assert not (tmp_path / "denied.txt").exists()
    assert len([p for p in prompts if "Allow" in p]) == 2
    assert any("approved.txt" in p for p in prompts)
    assert any("denied.txt" in p for p in prompts)
    store = SQLiteChatTranscriptStore(tmp_path / "data/repo-assistant-chats.sqlite3")
    session = store.latest_session(repo_root=tmp_path)
    assert session is not None
    history = CodingChatController(store, session.session_id, tmp_path, "local_only").history()
    assert "Report 2" in history
    messages = store.list_messages(session.session_id)
    assert all("effect" not in m.content for m in messages)
    assert messages[-1].metadata is not None
    assert messages[-1].metadata["execution_status"] == "completed_with_tool_errors"


def test_process_handle_survives_turns_and_exit_terminates_owned_child(tmp_path, monkeypatch):
    inputs = iter(["Start bounded process", "Poll it", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))
    supervisors = []
    handles = []

    def execute(args, config):
        owner = ACTIVE_FOREGROUND.get()
        assert owner is not None
        supervisors.append(owner.supervisor)
        if not handles:
            handles.append(
                owner.supervisor.start([sys.executable, "-c", "import time; time.sleep(60)"])
            )
        else:
            assert owner.supervisor.status(handles[0])["status"] == "running"
        args._coding_chat_observer(CodingTurnResult(0, "process observed", "completed"))
        return 0

    assert run_coding_chat(arguments(tmp_path), build_argument_parser(), execute) == 0
    assert supervisors[0] is supervisors[1]
    assert supervisors[0].processes[handles[0]].process.poll() is not None


def test_session_config_is_frozen_and_failed_return_is_not_hidden(tmp_path, monkeypatch):
    inputs = iter(["Inspect", "Continue", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))
    config_path = tmp_path / "user-config.toml"
    config_path.write_text('[defaults]\nprivacy = "local_only"\n', encoding="utf-8")
    configurations = []

    def execute(args, config):
        configurations.append((config, args.privacy))
        config_path.write_text('[defaults]\nprivacy = "external_allowed"\n', encoding="utf-8")
        args._coding_chat_observer(CodingTurnResult(0, "model claims success", "completed"))
        return 1

    assert run_coding_chat(arguments(tmp_path), build_argument_parser(), execute) == 1
    assert configurations[0][0] is configurations[1][0]
    assert [privacy for config, privacy in configurations] == ["local_only", "local_only"]
    store = SQLiteChatTranscriptStore(tmp_path / "data/repo-assistant-chats.sqlite3")
    session = store.latest_session(repo_root=tmp_path)
    assert session is not None
    metadata = store.list_messages(session.session_id)[-1].metadata
    assert metadata is not None and metadata["returncode"] == 1


def test_interrupted_execution_restores_stdout_and_closes_transcript(tmp_path, monkeypatch):
    original = sys.stdout

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(_EXAMPLE, "load_prompt_context", interrupt)
    args = build_argument_parser().parse_args(
        [
            "--repo-root",
            str(tmp_path),
            "--mode",
            "implement",
            "--execute",
            "--log-file",
            str(tmp_path / "interrupted.log"),
            "Inspect",
        ]
    )
    with pytest.raises(KeyboardInterrupt):
        _EXAMPLE._main(parsed_args=args)
    assert sys.stdout is original
    (tmp_path / "interrupted.log").rename(tmp_path / "closed.log")


def test_provider_chat_cannot_resume_coding_conversation(tmp_path, monkeypatch):
    chat = controller(tmp_path)
    args = build_argument_parser().parse_args(["--chat-session", "conversation"])
    with pytest.raises(KeyError, match="coding-chat"):
        _EXAMPLE._resolve_chat_session(store=chat.store, args=args, repo_root=tmp_path)


def test_official_client_receives_conversation_and_new_run_scope_each_turn(tmp_path, monkeypatch):
    import subprocess

    from ai_provider.agent_readiness import AgentReadiness
    from ai_provider.external_agents import run_external_agent

    requests = []
    configs = []
    grants = []
    monkeypatch.setenv("CODEX_COMMAND", "synthetic-codex-no-live-account")
    monkeypatch.setattr(
        "ai_provider.execution_fallback.check_agent_readiness",
        lambda *args, **kwargs: AgentReadiness(True, "synthetic fixture"),
    )

    def external(prompt, config, **kwargs):
        requests.append(prompt)
        configs.append(config)

        def runner(command, **options):
            owner = ACTIVE_FOREGROUND.get()
            assert owner is not None and owner.host is not None
            environment = options["env"]
            tokens = [
                value for key, value in environment.items() if key.startswith("AI_PROJECTS_MCP_")
            ]
            assert len(tokens) == 1 and owner.host.active(tokens[0])
            grants.append((owner.host, tokens[0]))
            return subprocess.CompletedProcess(
                command,
                0,
                '{"type":"final_answer","content":"Keep that architectural decision"}',
                "",
            )

        return run_external_agent(prompt, config, runner=runner)

    monkeypatch.setattr(_EXAMPLE, "_run_external_agent", external)
    inputs = iter(["Implement the next change with that decision", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))
    assert (
        main(
            [
                "--mode",
                "coding-chat",
                "--execute",
                "--repo-root",
                str(tmp_path),
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--skip-prompt-review",
                "Keep the provider boundary intact",
            ]
        )
        == 0
    )
    assert len(requests) == 2
    assert "Keep the provider boundary intact" in requests[1]
    assert "Keep that architectural decision" in requests[1]
    assert configs[0].shared_task_id == configs[1].shared_task_id
    assert configs[0].shared_run_id != configs[1].shared_run_id
    assert configs[0].shared_tool_profile == configs[1].shared_tool_profile == "coding"
    assert len(grants) == 2
    assert grants[0][1] != grants[1][1]
    assert all(not host.active(token) for host, token in grants)
