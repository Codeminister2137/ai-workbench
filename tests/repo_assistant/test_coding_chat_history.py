"""Deterministic history reduction preserves owner text and observed failures."""

import json

import pytest
from ai_agent.coding_chat import CodingChatController, CodingChatInputError, CodingTurnResult

from .test_coding_chat import controller


def turns(history):
    return json.loads(history[history.index("[") :])


def test_long_history_preserves_all_owner_corrections_outcomes_and_originals(tmp_path):
    chat = controller(tmp_path, budget=0)
    for index in range(10):
        chat.turn(
            f"Owner decision {index}: keep privacy inherited. żółć",
            lambda request: CodingTurnResult(
                1, "old assistant report " * 200, "validation_failed", "test failed"
            ),
        )
    before = chat.store.list_messages("conversation")
    chat.history_budget_chars = 7000
    request = "Correction: no dependency; use the standard library"
    history = chat.history(current_text=request)
    assert len(history) + len(request) <= 7000
    parsed = turns(history)
    assert [t["content"] for t in parsed if t["role"] == "user"] == [
        m.content for m in before if m.role == "user"
    ]
    assert all(
        t["outcome"] == "validation_failed"
        and t["returncode"] == 1
        and t["failure_reason"] == "test failed"
        for t in parsed
        if t["role"] == "assistant"
    )
    assert "not summaries" in history
    assert any(t.get("report_shortened") for t in parsed)
    assert chat.store.list_messages("conversation") == before
    resumed = CodingChatController(
        chat.store, "conversation", tmp_path, "local_only", history_budget_chars=7000
    )
    assert resumed.history(current_text=request) == history


def test_oldest_reports_shorten_first_and_recent_report_stays_complete(tmp_path):
    chat = controller(tmp_path, budget=0)
    for index in range(3):
        chat.turn(
            f"decision {index}",
            lambda request, value=index: CodingTurnResult(0, str(value) * 3000, "completed"),
        )
    chat.history_budget_chars = len(chat.history()) - 1000
    parsed = turns(chat.history())
    reports = [t for t in parsed if t["role"] == "assistant"]
    assert reports[0]["report_shortened"] is True
    assert reports[0]["original_content_chars"] == 3000
    assert len(reports[0]["content"]) < 3000
    assert reports[-1]["content"] == "2" * 3000
    assert "report_shortened" not in reports[-1]


def test_mandatory_owner_overflow_refuses_without_append_or_execution(tmp_path):
    chat = controller(tmp_path, budget=0)
    chat.turn(
        "Keep this owner decision " * 150,
        lambda request: CodingTurnResult(0, "report" * 1000, "completed"),
    )
    before = chat.store.list_messages("conversation")
    chat.history_budget_chars = 1000
    with pytest.raises(CodingChatInputError, match="Mandatory owner messages"):
        chat.turn("Continue", lambda request: pytest.fail("must not execute"))
    assert chat.store.list_messages("conversation") == before


def test_interruption_host_text_survives_reduction_and_queued_correction(tmp_path):
    chat = controller(tmp_path, budget=0)
    chat.turn(
        "Initial decision", lambda request: CodingTurnResult(0, "long report" * 1000, "completed")
    )

    def interrupt(request):
        chat.stage("Correction: inspect effects before any further edit")
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        chat.turn("Act", interrupt)
    host = chat.store.list_messages("conversation")[-1]
    chat.history_budget_chars = 2500
    history = chat.history()
    assert host.content in history
    assert "queued_not_executed" in history
    assert "Correction: inspect effects" in history
    assert "interrupted" in history


def test_zero_budget_preserves_reports_without_reduction(tmp_path):
    chat = controller(tmp_path, budget=0)
    report = '"\\Unicode żółć' * 1000
    chat.turn("Explain", lambda request: CodingTurnResult(0, report, "completed"))
    assert turns(chat.history())[-1]["content"] == report
    assert "report_shortened" not in chat.history()


def test_original_report_retrieval_is_session_scoped_and_never_executes(tmp_path):
    from ai_agent.coding_chat import run_terminal_conversation

    chat = controller(tmp_path)
    report = "Full earlier implementation plan"
    chat.turn("Plan", lambda request: CodingTurnResult(0, report, "completed"))
    identifier = chat.store.list_messages("conversation")[-1].message_id
    prompts = iter(["/history", f"/history {identifier}", "/history wrong-session-id", "/exit"])
    output = []
    before = chat.store.list_messages("conversation")
    assert (
        run_terminal_conversation(
            chat,
            lambda request: pytest.fail("history command must not execute"),
            read=lambda prompt: next(prompts),
            write=output.append,
        )
        == 0
    )
    assert report in output
    assert any(identifier in line for line in output)
    assert "coding_chat_history: message not found in this conversation" in output
    assert chat.store.list_messages("conversation") == before


@pytest.mark.parametrize("restart", [False, True])
def test_actual_native_cli_keeps_required_tools_and_owner_decision_after_reduction(
    tmp_path, monkeypatch, restart
):
    from ai_provider import AIMessage, AIResponse, BackendInfo, BackendLocation, MessageRole
    from ai_provider.chat_transcripts import SQLiteChatTranscriptStore

    from .support import _EXAMPLE, main

    requests = []

    class Client:
        backend = BackendInfo("ollama", "gpt-oss:20b", BackendLocation.LOCAL)

        def complete(self, request):
            requests.append(request)
            content = '"long earlier assistant report\\" ' * 400 if len(requests) == 1 else "done"
            return AIResponse(AIMessage(MessageRole.ASSISTANT, content), self.backend)

    monkeypatch.setattr(_EXAMPLE, "create_chat_client", lambda config: Client())
    correction = "Correction: use standard library; keep the earlier privacy decision"
    inputs = iter(["/exit"] if restart else [correction, "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))
    database = tmp_path / "conversation.sqlite3"
    arguments = [
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
        "--coding-chat-history-budget-chars",
        "2200",
        "--privacy",
        "local_only",
        "--coding-session-db",
        str(database),
    ]
    assert main([*arguments, "Keep privacy inherited. No dependencies."]) == 0
    if restart:
        store = SQLiteChatTranscriptStore(database)
        session = store.latest_session(repo_root=tmp_path)
        assert session is not None
        before = store.list_messages(session.session_id)
        assert len(before[-1].content) > 2200
        monkeypatch.setattr("builtins.input", lambda prompt: "/exit")
        assert main([*arguments, "--coding-session", session.session_id, correction]) == 0
        after = store.list_messages(session.session_id)
        assert after[: len(before)] == before
        assert len(after) == len(before) + 2
    assert len(requests) == 2
    context = "\n".join(m.content for m in requests[-1].messages)
    assert "Keep privacy inherited. No dependencies." in context
    assert "Correction: use standard library" in context
    assert '"report_shortened": true' in context
    assert requests[0].tools and requests[0].tools == requests[1].tools


@pytest.mark.parametrize("continuation", ["next_turn", "restart", "missing_skill"])
def test_actual_cli_refreshes_selected_skill_and_instructions_after_history_reduction(
    tmp_path, monkeypatch, continuation
):
    from ai_provider import AIMessage, AIResponse, BackendInfo, BackendLocation, MessageRole
    from ai_provider.chat_transcripts import SQLiteChatTranscriptStore

    from .support import _EXAMPLE, main

    source = tmp_path / "skills/review-repo-change/SKILL.md"
    source.parent.mkdir(parents=True)
    header = "---\nname: review-repo-change\ndescription: review\n---\n"
    original_skill = header + "Initial skill: inspect before commenting.\n" + "s" * 3000
    refreshed_skill = header + "Refreshed skill: preserve minority findings.\n" + "t" * 3000
    source.write_text(original_skill)
    instructions = tmp_path / "AGENTS.md"
    instructions.write_text("Initial repository rule: preserve privacy inheritance.\n")
    fresh_instructions = "Refreshed repository rule: do not edit protected.txt.\n" + "r" * 3000
    requests = []

    class Client:
        backend = BackendInfo("ollama", "gpt-oss:20b", BackendLocation.LOCAL)

        def complete(self, request):
            requests.append(request)
            if len(requests) == 1:
                instructions.write_text(fresh_instructions)
                if continuation == "missing_skill":
                    source.unlink()
                else:
                    source.write_text(refreshed_skill)
            return AIResponse(
                AIMessage(
                    MessageRole.ASSISTANT,
                    "Earlier report " * 800 if len(requests) == 1 else "Reviewed current inputs",
                ),
                self.backend,
            )

    monkeypatch.setattr(_EXAMPLE, "create_chat_client", lambda config: Client())
    database = tmp_path / "conversation.sqlite3"
    correction = "Owner correction: no changes; explain the current findings."
    inputs = iter(["/exit"] if continuation == "restart" else [correction, "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))
    arguments = [
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
        "--coding-chat-history-budget-chars",
        "2200",
        "--coding-session-db",
        str(database),
        "--skill",
        "review-repo-change",
        "--skill-dir",
        str(tmp_path / "skills"),
    ]
    expected = 1 if continuation == "missing_skill" else 0
    assert main([*arguments, "Owner decision: keep privacy inherited; inspect only."]) == expected
    store = SQLiteChatTranscriptStore(database)
    session = store.latest_session(repo_root=tmp_path)
    assert session is not None
    original_messages = store.list_messages(session.session_id)
    if continuation == "restart":
        monkeypatch.setattr("builtins.input", lambda prompt: "/exit")
        assert main([*arguments, "--coding-session", session.session_id, correction]) == 0
        assert (
            store.list_messages(session.session_id)[: len(original_messages)] == original_messages
        )
    first_context = "\n".join(message.content for message in requests[0].messages)
    assert original_skill in first_context
    assert "Initial repository rule" in first_context
    if continuation == "missing_skill":
        assert len(requests) == 1
        messages = store.list_messages(session.session_id)
        assert messages[-2].content == correction
        assert (messages[-1].metadata or {}).get("execution_status") == "failed"
        return
    assert len(requests) == 2
    context = "\n".join(message.content for message in requests[1].messages)
    assert refreshed_skill in context and fresh_instructions in context
    assert original_skill not in context and "Initial repository rule" not in context
    assert "Owner decision: keep privacy inherited" in context and correction in context
    assert '"report_shortened": true' in context
    assert requests[0].tools == requests[1].tools
