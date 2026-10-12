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


def test_inflight_correction_is_durable_and_not_duplicated_or_replayed(tmp_path: Path):
    from ai_agent.coding_chat_input import CodingChatInput

    chat = controller(tmp_path)
    terminal = CodingChatInput(lambda text: None, chat.stage)
    requests = []

    def execute(request):
        requests.append(request)
        if len(requests) == 1:
            terminal.feed("/steer Correction: keep the provider boundary intact")
        return CodingTurnResult(0, "original turn report", "completed")

    chat.turn("Implement the approved change", execute)
    staged = terminal.read("unused")
    restarted = CodingChatController(chat.store, "conversation", tmp_path, "local_only")
    assert "Correction: keep the provider boundary intact" in restarted.history()
    assert "queued_not_executed" in restarted.history()
    chat.turn(staged, execute)
    assert requests[-1].text == "Correction: keep the provider boundary intact"
    assert "original turn report" in requests[-1].history
    assert "Correction:" not in requests[-1].history
    assert len(chat.store.list_messages("conversation")) == 4
    with pytest.raises(CodingChatInputError, match="already attempted"):
        chat.turn(staged, execute)


def test_inflight_correction_survives_interruption_without_automatic_replay(tmp_path: Path):
    chat = controller(tmp_path)

    def execute(request):
        chat.stage("Do not use an external provider")
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        chat.turn("Inspect the source", execute)
    resumed = CodingChatController(chat.store, "conversation", tmp_path, "local_only")
    assert "Do not use an external provider" in resumed.history()
    assert "queued_not_executed" in resumed.history()
    assert "interrupted" in resumed.history()


def test_queued_input_is_scoped_to_its_conversation(tmp_path: Path):
    first = controller(tmp_path)
    queued = first.stage("Use no new dependencies")
    other = tmp_path / "other"
    other.mkdir()
    second = controller(other)
    with pytest.raises(CodingChatInputError, match="different conversation"):
        second.turn(queued, lambda request: pytest.fail("must not execute"))


def test_multiple_inflight_corrections_use_latest_request_with_all_owner_context(tmp_path):
    from ai_agent.coding_chat_input import CodingChatInput

    chat = controller(tmp_path)
    terminal = CodingChatInput(lambda text: None, chat.stage)
    terminal.feed("Add the dependency")
    terminal.feed("Correction: use the standard library instead")
    requests = []
    chat.turn(
        terminal.read("unused"),
        lambda request: requests.append(request) or CodingTurnResult(0, "done", "completed"),
    )
    assert requests[0].text == "Correction: use the standard library instead"
    assert "Add the dependency" in requests[0].history
    assert not terminal.pending
    assert len(chat.store.list_messages("conversation")) == 3


def test_actual_cli_inflight_steering_is_separate_from_native_tool_approval(tmp_path, monkeypatch):
    import threading

    from ai_agent.coding_chat_input import CodingChatInput
    from ai_provider import (
        AIMessage,
        AIResponse,
        AIToolCall,
        BackendInfo,
        BackendLocation,
        MessageRole,
    )

    queued = threading.Event()
    started = threading.Event()
    sent = []
    terminal = CodingChatInput()

    def write(text):
        if text.startswith("coding_chat_queued"):
            queued.set()

    terminal.write = write

    def poll():
        if started.is_set() and not sent:
            sent.append("correction")
            return "/steer Correction: no edits; only explain the boundary"
        if terminal.ticket and len(sent) == 1:
            sent.append("stale")
            return "/approve stale-ticket yes"
        if terminal.ticket and len(sent) == 2:
            sent.append("deny")
            return f"/approve {terminal.ticket} no"
        return None

    original = terminal.in_flight
    monkeypatch.setattr(terminal, "in_flight", lambda: original(poll))

    def create_terminal(*, stage):
        terminal.stage = stage
        return terminal

    monkeypatch.setattr("ai_agent.coding_chat_cli.CodingChatInput", create_terminal)
    monkeypatch.setattr("builtins.input", lambda prompt: "/exit")
    requests = []

    class Client:
        backend = BackendInfo("ollama", "gpt-oss:20b", BackendLocation.LOCAL)

        def complete(self, request):
            requests.append(request)
            if len(requests) == 1:
                started.set()
                assert queued.wait(2)
                message = AIMessage(
                    MessageRole.ASSISTANT,
                    "",
                    tool_calls=(
                        AIToolCall("edit", "create_file", {"path": "denied.txt", "content": "x"}),
                    ),
                )
            else:
                message = AIMessage(MessageRole.ASSISTANT, "Boundary explanation")
            return AIResponse(message, self.backend)

    monkeypatch.setattr(_EXAMPLE, "create_chat_client", lambda config: Client())
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
            "Make the previously requested edit",
        ]
    )
    assert len(requests) == 3
    assert not (tmp_path / "denied.txt").exists()
    assert "Correction: no edits" in "\n".join(m.content for m in requests[-1].messages)
    assert terminal.closed and terminal.thread is None
    store = SQLiteChatTranscriptStore(tmp_path / "data/repo-assistant-chats.sqlite3")
    session = store.latest_session(repo_root=tmp_path)
    assert session is not None
    messages = store.list_messages(session.session_id)
    assert len(messages) == 4
    assert messages[1].content == "Correction: no edits; only explain the boundary"


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


@pytest.mark.parametrize("turn_limit", [None, 10, 100])
def test_away_allowance_is_fixed_across_turns_and_caps_turn_limits(
    tmp_path, monkeypatch, turn_limit
):
    now = 0.0
    inputs = iter(["Inspect", "Continue", "/exit"])
    monkeypatch.setattr("ai_agent.coding_chat_cli.time.perf_counter", lambda: now)
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))
    seen = []

    def execute(args, config):
        nonlocal now
        seen.append((args._execution_deadline, args.away_minutes))
        now += 4
        args._coding_chat_observer(CodingTurnResult(0, "done", "completed"))
        return 0

    options = ["--away-minutes", "1"]
    if turn_limit is not None:
        options += ["--turn-timeout-seconds", str(turn_limit)]
    assert run_coding_chat(arguments(tmp_path, *options), build_argument_parser(), execute) == 0
    expected = [60, 60] if turn_limit != 10 else [10, 14]
    assert [row[0] for row in seen] == expected
    assert [row[1] for row in seen] == pytest.approx([1, 56 / 60])


def test_away_expiry_stops_queued_turn_and_preserves_staged_input(tmp_path, monkeypatch):
    from ai_agent.coding_chat_input import CodingChatInput

    now = 0.0
    terminals = []

    def create_terminal(*, stage):
        terminal = CodingChatInput(lambda text: None, stage)
        terminals.append(terminal)
        return terminal

    monkeypatch.setattr("ai_agent.coding_chat_cli.time.perf_counter", lambda: now)
    monkeypatch.setattr("ai_agent.coding_chat_cli.CodingChatInput", create_terminal)
    calls = []

    def execute(args, config):
        nonlocal now
        calls.append(args.prompt)
        terminals[0].feed("Continue after this turn")
        now = 61
        args._coding_chat_observer(CodingTurnResult(0, "late success", "completed"))
        return 0

    assert (
        run_coding_chat(
            arguments(tmp_path, "Inspect", "--away-minutes", "1"), build_argument_parser(), execute
        )
        == 1
    )
    assert calls == ["Inspect"]
    assert terminals[0].closed
    store = SQLiteChatTranscriptStore(tmp_path / "data/repo-assistant-chats.sqlite3")
    session = store.latest_session(repo_root=tmp_path)
    assert session is not None
    messages = store.list_messages(session.session_id)
    assert messages[1].content == "Continue after this turn"
    assert messages[1].metadata is not None and messages[-1].metadata is not None
    assert messages[1].metadata["execution_status"] == "queued_not_executed"
    assert messages[-1].metadata["execution_status"] == "failed"
    assert "expired" in messages[-1].content


@pytest.mark.parametrize("grant_fresh", [True, False])
def test_resuming_with_away_minutes_starts_fresh_launch_allowance(
    tmp_path, monkeypatch, grant_fresh
):
    now = 0.0
    deadlines = []
    monkeypatch.setattr("ai_agent.coding_chat_cli.time.perf_counter", lambda: now)
    monkeypatch.setattr("builtins.input", lambda prompt: "/exit")

    def execute(args, config):
        deadlines.append(args._execution_deadline)
        args._coding_chat_observer(CodingTurnResult(0, "done", "completed"))
        return 0

    options = ["Inspect", "--away-minutes", "1"]
    assert run_coding_chat(arguments(tmp_path, *options), build_argument_parser(), execute) == 0
    store = SQLiteChatTranscriptStore(tmp_path / "data/repo-assistant-chats.sqlite3")
    session = store.latest_session(repo_root=tmp_path)
    assert session is not None
    now = 100
    resume_options = options if grant_fresh else ["Inspect"]
    assert (
        run_coding_chat(
            arguments(tmp_path, *resume_options, "--coding-session", session.session_id),
            build_argument_parser(),
            execute,
        )
        == 0
    )
    assert deadlines == [60, 160 if grant_fresh else None]


def test_turn_limit_without_away_does_not_limit_idle_conversation(tmp_path, monkeypatch):
    now = 0.0
    inputs = iter(["Inspect", "Continue", "/exit"])

    def read(prompt):
        nonlocal now
        now += 100
        return next(inputs)

    monkeypatch.setattr("ai_agent.coding_chat_cli.time.perf_counter", lambda: now)
    monkeypatch.setattr("builtins.input", read)
    deadlines = []

    def execute(args, config):
        deadlines.append(args._execution_deadline)
        assert args.away_minutes is None
        args._coding_chat_observer(CodingTurnResult(0, "done", "completed"))
        return 0

    assert (
        run_coding_chat(
            arguments(tmp_path, "--turn-timeout-seconds", "10"), build_argument_parser(), execute
        )
        == 0
    )
    assert deadlines == [110, 210]


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_invalid_turn_timeout_refuses_before_creating_session(tmp_path, value):
    with pytest.raises(SystemExit):
        arguments(tmp_path, "--turn-timeout-seconds", value)
    assert not (tmp_path / "data").exists()


def test_execution_deadline_keeps_shortest_bound_without_resetting(monkeypatch):
    from argparse import Namespace

    now = 100.0
    monkeypatch.setattr(_EXAMPLE.time, "perf_counter", lambda: now)
    args = Namespace(
        away_minutes=1, turn_timeout_seconds=10, timeout_seconds=180, _execution_deadline=130
    )
    assert _EXAMPLE._configure_execution_deadline(args) == 110
    assert args.timeout_seconds == 10
    now = 105
    assert _EXAMPLE._configure_execution_deadline(args) == 110
    assert args.timeout_seconds == 5


@pytest.mark.parametrize("recover", [False, True])
def test_coding_chat_external_sign_in_and_retry_without_competing_terminal_input(
    tmp_path, monkeypatch, capsys, recover
):
    from types import SimpleNamespace

    from ai_agent.coding_chat_input import CodingChatInput
    from ai_orchestrator import AccessMethod
    from ai_provider.agent_readiness import AgentReadiness
    from ai_provider.external_agents import ExternalAgentResult

    terminals = []
    authenticated = False
    deadlines = []
    now = 0.0

    class Terminal(CodingChatInput):
        def read(self, prompt):
            nonlocal authenticated, now
            if recover and not authenticated:
                authenticated = True  # Synthetic external sign-in; no login process.
                now = 5.0
                return "Continue after external sign-in"
            return "/exit"

        def in_flight(self, poll=None):
            terminals.append(self)
            return super().in_flight(lambda: None)

    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(_EXAMPLE.time, "perf_counter", lambda: now)
    monkeypatch.setattr("ai_agent.coding_chat_cli.CodingChatInput", Terminal)
    monkeypatch.setenv("CODEX_COMMAND", "synthetic-codex")
    monkeypatch.setattr(
        "ai_provider.execution_fallback.check_agent_readiness",
        lambda method: AgentReadiness(
            authenticated and method is AccessMethod.CODEX_CLI,
            "synthetic sign-in needed",
            ("fake", "login"),
        ),
    )
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("Competing stdin reader"))
    monkeypatch.setattr(
        "ai_provider.execution_fallback.subprocess.run",
        lambda *args, **kwargs: pytest.fail("Inline login launched"),
    )
    monkeypatch.setattr(
        _EXAMPLE, "create_chat_client", lambda config: pytest.fail("Unauthenticated model request")
    )

    def execute(prompt, config, **kwargs):
        assert authenticated
        deadlines.append(kwargs.get("deadline"))
        return ExternalAgentResult(("synthetic-client",), 0, "Authenticated continuation", "")

    monkeypatch.setattr(_EXAMPLE, "_run_external_agent", execute)
    assert main(
        [
            "Inspect",
            "--mode",
            "coding-chat",
            "--execute",
            "--repo-root",
            str(tmp_path),
            "--route-id",
            "openai-codex-gpt-5-5",
            "--privacy",
            "external_allowed",
            "--cost-policy",
            "allowances_allowed",
            "--skip-prompt-review",
            "--away-minutes",
            "1",
        ]
    ) == (0 if recover else 1)
    output = capsys.readouterr().out
    assert output.count("## **SUMMARY**") == (2 if recover else 1)
    assert "outside coding-chat" in output and "execution_status=failed" in output
    assert "synthetic sign-in needed" in output
    assert terminals and all(t.thread is None and t.closed for t in terminals)
    store = SQLiteChatTranscriptStore(tmp_path / "data/repo-assistant-chats.sqlite3")
    saved = store.latest_session(repo_root=tmp_path)
    assert saved is not None
    messages = store.list_messages(saved.session_id)
    assert messages[-1].metadata is not None
    assert messages[-1].metadata["execution_status"] == ("completed" if recover else "failed")
    assert deadlines == ([60.0] if recover else [])


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


def test_actual_partial_edit_interrupt_requires_reconciliation_and_fresh_denial(
    tmp_path, monkeypatch
):
    from ai_provider import (
        AIMessage,
        AIResponse,
        AIToolCall,
        BackendInfo,
        BackendLocation,
        MessageRole,
    )

    source = tmp_path / "source.py"
    source.write_text("value = 0\n")
    protected = tmp_path / "protected.txt"
    protected.write_text("owner-owned evidence\n")
    database = tmp_path / "session.sqlite3"
    requests, owners, prompts = [], [], []
    phase = "interrupt"
    phase_calls = 0

    class Client:
        backend = BackendInfo("ollama", "gpt-oss:20b", BackendLocation.LOCAL)

        def complete(self, request):
            nonlocal phase_calls
            phase_calls += 1
            requests.append(request)
            owner = ACTIVE_FOREGROUND.get()
            assert owner is not None
            owners.append(owner)
            if phase == "interrupt" and phase_calls == 2:
                assert source.read_text() == "value = 1\n"
                session = ACTIVE_SESSION.get()
                assert session is not None
                CodingChatController(
                    SQLiteChatTranscriptStore(database), session.session_id, tmp_path, "local_only"
                ).stage(
                    "Owner correction: preserve protected.txt; inspect effects before further work"
                )
                raise KeyboardInterrupt
            if phase == "resume" and phase_calls == 1:
                call = AIToolCall("inspect-current", "read_file", {"path": "source.py"})
            elif phase_calls == 1 or (phase == "resume" and phase_calls == 2):
                before, after = (0, 1) if phase == "interrupt" else (1, 2)
                call = AIToolCall(
                    "edit",
                    "edit_file",
                    {
                        "path": "source.py",
                        "old_text": f"value = {before}",
                        "new_text": f"value = {after}",
                    },
                )
            else:
                return AIResponse(
                    AIMessage(
                        MessageRole.ASSISTANT, "Fresh edit denied; original partial effect retained"
                    ),
                    self.backend,
                )
            return AIResponse(
                AIMessage(MessageRole.ASSISTANT, "", tool_calls=(call,)), self.backend
            )

    monkeypatch.setattr(_EXAMPLE, "create_chat_client", lambda config: Client())
    answers = iter(["yes"])

    def read(prompt):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr("builtins.input", read)
    options = [
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
        "--privacy",
        "local_only",
        "--cost-policy",
        "local_only",
        "--approval-policy",
        "interactive",
        "--coding-session-db",
        str(database),
    ]
    assert main([*options, "Change value to 1; preserve protected.txt"]) == 130
    assert source.read_text() == "value = 1\n"
    assert ACTIVE_FOREGROUND.get() is None and ACTIVE_SESSION.get() is None
    store = SQLiteChatTranscriptStore(database)
    session = store.latest_session(repo_root=tmp_path)
    assert session is not None
    original_messages = store.list_messages(session.session_id)
    assert (
        "queued_not_executed"
        in CodingChatController(store, session.session_id, tmp_path, "local_only").history()
    )
    assert main([*options, "--coding-session", session.session_id, "Continue"]) == 1
    assert len(requests) == 2 and source.read_text() == "value = 1\n"
    phase, phase_calls = "resume", 0
    answers = iter(["no", "/exit"])
    assert (
        main(
            [
                *options,
                "--coding-session",
                session.session_id,
                "--coding-session-reconciled",
                "I inspected source.py: value is 1. Read it again before requesting value 2.",
            ]
        )
        == 0
    )
    assert len([prompt for prompt in prompts if "Allow" in prompt]) == 2
    assert owners[0] is not owners[-1]
    assert source.read_text() == "value = 1\n"
    assert protected.read_text() == "owner-owned evidence\n"
    assert store.list_messages(session.session_id)[: len(original_messages)] == original_messages
    assert "Owner correction: preserve protected.txt" in "\n".join(
        message.content for message in requests[-1].messages
    )
    assert ACTIVE_FOREGROUND.get() is None and ACTIVE_SESSION.get() is None


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


def test_native_chat_latest_correction_and_review_reach_ollama_payload(tmp_path, monkeypatch):
    from ai_provider import AIMessage, AIResponse, BackendInfo, BackendLocation, MessageRole
    from ai_provider.adapters.ollama import OllamaChatClient
    from ai_provider.config import BackendConfig, ProviderKind

    initial = "INITIAL_TASK: improve the diagnostic regression tests."
    correction = "LATEST_CORRECTION: preserve fixed stderr and empty stdout assertions."
    review = "LATEST_REVIEW: inspect with tools; review observed results without edits or retries."
    payloads = []
    adapter = OllamaChatClient(BackendConfig(provider=ProviderKind.OLLAMA, model="gpt-oss:20b"))

    class Client:
        backend = BackendInfo("ollama", "gpt-oss:20b", BackendLocation.LOCAL)

        def complete(self, request):
            payloads.append(adapter._chat_payload(request, stream=False))
            return AIResponse(
                AIMessage(MessageRole.ASSISTANT, f"Observed report {len(payloads)}"), self.backend
            )

    (tmp_path / "AGENTS.md").write_text("Preserve existing work and report observed checks.\n")
    (tmp_path / "module.py").write_text("fixture = 1\n")
    monkeypatch.setattr(_EXAMPLE, "create_chat_client", lambda config: Client())
    inputs = iter([correction, review, "/exit"])
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
                initial,
            ]
        )
        == 0
    )
    assert len(payloads) == 3
    for payload, latest in zip(payloads, (initial, correction, review), strict=True):
        current = payload["messages"][-1]
        assert current["role"] == "user"
        request_block = (
            current["content"]
            .split("# User request\n", 1)[1]
            .split("# Repository context", 1)[0]
            .strip()
        )
        assert request_block == latest
        assert current["content"].endswith("# User request\n" + latest)
        assert current["content"].index("Original objective:") < current["content"].index(
            "## Active user turn"
        )
        assert "Preserve existing work" in current["content"]
        assert "fixture = 1" in current["content"]
        assert any(tool["function"]["name"] == "read_file" for tool in payload["tools"])
    final = payloads[-1]["messages"][-1]["content"]
    assert initial in final and correction in final and "Observed report 2" in final
    assert "Original objective:" in final
    read_schema = next(
        tool["function"]["parameters"]
        for tool in payloads[-1]["tools"]
        if tool["function"]["name"] == "read_file"
    )
    assert read_schema["properties"]["start_line"]["type"] == "integer"
    assert read_schema["properties"]["end_line"]["type"] == "integer"


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
    for prompt in requests:
        assert "codex_sandbox: read-only" in prompt
        assert "shared_tool_profile: coding" in prompt
        assert "shared_tool_approval_policy: interactive" in prompt
        assert "a coding profile alone does not authorize edits" in prompt
    assert len(grants) == 2
    assert grants[0][1] != grants[1][1]
    assert all(not host.active(token) for host, token in grants)


@pytest.mark.parametrize("continuation", ["fallback", "stale", "restart"])
def test_semantic_preview_chat_continuation_uses_fresh_scope_and_current_files(
    tmp_path, monkeypatch, continuation
):
    import io
    import json
    import subprocess

    from ai_agent.coding_chat_input import CodingChatInput
    from ai_agent.http_proxy import HttpMcpConnection
    from ai_agent.shared_approvals import TerminalApproval
    from ai_provider.agent_readiness import AgentReadiness
    from ai_provider.external_agents import run_external_agent

    pytest.importorskip("jedi", reason="approved optional rename-preview extra")
    package = tmp_path / "sample_pkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    source = package / "models.py"
    source.write_text("class Widget:\n    pass\n")
    caller = package / "client.py"
    caller.write_text("from .models import Widget\nitem = Widget()\n")
    original_source, original_caller = source.read_bytes(), caller.read_bytes()
    catalog = tmp_path / "catalog.toml"
    catalog.write_text("""[[models]]
route_id = "codex"
provider = "openai"
product = "codex"
model = "test"
location = "external"
access_method = "codex_cli"
auth_method = "chatgpt_sign_in"
billing_source = "chatgpt_subscription_allowance"
cost_policy_tier = "allowances_allowed"
quality = "high"
[models.capabilities]
chat = true
tools = true
[[models]]
route_id = "copilot"
provider = "github"
product = "github_copilot"
model = "auto"
location = "external"
access_method = "copilot_cli"
auth_method = "github_account_sign_in"
billing_source = "github_copilot_subscription_allowance"
cost_policy_tier = "allowances_allowed"
quality = "high"
[models.capabilities]
chat = true
tools = true
""")
    monkeypatch.setenv("CODEX_COMMAND", "synthetic-codex")
    monkeypatch.setenv("GITHUB_COPILOT_COMMAND", "synthetic-copilot")
    monkeypatch.setattr(
        "ai_provider.execution_fallback.check_agent_readiness",
        lambda method: AgentReadiness(True, "synthetic; no account probe"),
    )
    inputs = iter(["/exit"] if continuation == "restart" else ["Apply that exact rename", "/exit"])

    class Tty(io.StringIO):
        def isatty(self):
            return True

    class SyntheticTerminal(CodingChatInput):
        def read(self, prompt):
            return next(inputs)

        def in_flight(self, poll=None):
            return super().in_flight(lambda: None)

    monkeypatch.setattr(sys, "stdin", Tty())
    monkeypatch.setattr("ai_agent.coding_chat_cli.CodingChatInput", SyntheticTerminal)
    plan = {}
    approvals, attempts, receipts, owners = [], [], [], []

    def approve(self, call, category):
        assert call.name == "rename_apply"
        assert call.arguments["complete_diff"] in plan["preview"]
        assert call.arguments["plan_sha256"] == plan["digest"]
        approvals.append((self.run_id, call.arguments))
        return True  # Synthetic exact-diff grant; not physical terminal evidence.

    monkeypatch.setattr(TerminalApproval, "__call__", approve)

    def external(prompt, config, **kwargs):
        attempts.append(config.access_method.value)
        owner = ACTIVE_FOREGROUND.get()
        assert owner is not None
        owners.append(owner)
        if len(attempts) == 2 and continuation != "restart":
            assert plan["id"] in prompt
            if continuation == "stale":
                source.write_bytes(original_source + b"# owner changed the source\n")
            return run_external_agent(
                prompt,
                config,
                runner=lambda command, **options: subprocess.CompletedProcess(
                    command, 1, '{"type":"error","message":"usage_limit_reached"}', ""
                ),
                **kwargs,
            )

        def runner(command, **options):
            assert owner.host is not None
            token_name = next(
                name for name in options["env"] if name.startswith("AI_PROJECTS_MCP_")
            )
            connection = HttpMcpConnection(owner.host.url, options["env"][token_name])
            connection.send({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
            connection.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            tool = "rename_apply" if plan else "rename_preview"
            arguments = (
                {"plan_id": plan["id"]}
                if plan
                else {
                    "path": "sample_pkg/models.py",
                    "line": 1,
                    "column": 7,
                    "new_name": "Gadget",
                }
            )
            try:
                reply = connection.send(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": tool, "arguments": arguments},
                    }
                )
                assert reply is not None
                result = reply["result"]
                metadata = result["structuredContent"]["metadata"]
                receipts.append(metadata["shared_receipt"])
                if tool == "rename_preview":
                    assert not result["isError"]
                    plan["id"] = metadata["plan_id"]
                    plan["preview"] = result["content"][0]["text"]
                    plan["digest"] = metadata["plan_sha256"]
                    assert source.read_bytes() == original_source
                    assert caller.read_bytes() == original_caller
                else:
                    assert result["isError"] == (continuation != "fallback")
                report = (
                    "Preview plan: " + plan["id"] if tool == "rename_preview" else "Apply inspected"
                )
                return subprocess.CompletedProcess(
                    command,
                    0,
                    json.dumps({"type": "final_answer", "content": report}),
                    "",
                )
            finally:
                connection.close()

        return run_external_agent(prompt, config, runner=runner, **kwargs)

    monkeypatch.setattr(_EXAMPLE, "_run_external_agent", external)
    arguments = [
        "--mode",
        "coding-chat",
        "--execute",
        "--repo-root",
        str(tmp_path),
        "--catalog",
        str(catalog),
        "--route-id",
        "codex",
        "--privacy",
        "external_allowed",
        "--cost-policy",
        "allowances_allowed",
        "--approval-policy",
        "interactive",
        "--skip-prompt-review",
        "Preview Widget to Gadget; wait for my next request",
    ]
    assert main(arguments) == 0
    if continuation == "restart":
        inputs = iter(["/exit"])
        store = SQLiteChatTranscriptStore(tmp_path / "data/repo-assistant-chats.sqlite3")
        saved = store.latest_session(repo_root=tmp_path)
        assert saved is not None
        arguments[-1] = "Apply that exact rename"
        assert main([*arguments[:-1], "--coding-session", saved.session_id, arguments[-1]]) == 0
        assert owners[0] is not owners[1]
    else:
        assert owners[0] is owners[1] is owners[2]
        assert attempts == ["codex_cli", "codex_cli", "copilot_cli"]
    assert receipts[0]["task_id"] == receipts[1]["task_id"]
    assert receipts[0]["run_id"] != receipts[1]["run_id"]
    # A stale plan can still display its exact old preview for approval; execution
    # rechecks digests and refuses all writes. Restart cannot resolve that plan.
    assert len(approvals) == (0 if continuation == "restart" else 1)
    if continuation == "fallback":
        assert "Gadget" in source.read_text() and "Widget" not in source.read_text()
        assert caller.read_text() == "from .models import Gadget\nitem = Gadget()\n"
    else:
        assert "class Widget" in source.read_text() and "Gadget" not in source.read_text()
        assert caller.read_bytes() == original_caller
    assert all(owner.host is None or owner.host.closed for owner in owners)
