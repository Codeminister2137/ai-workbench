"""Repo-assistant chat regression contracts."""

from __future__ import annotations

from pathlib import Path

from .support import (
    _EXAMPLE,
    main,
)


def test_chat_mode_persists_and_resumes_local_transcript(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    from ai_provider import (
        AIMessage,
        AIRequest,
        AIResponse,
        BackendInfo,
        BackendLocation,
        MessageRole,
        SQLiteChatTranscriptStore,
    )

    requests: list[AIRequest] = []

    class FakeClient:
        backend = BackendInfo("ollama", "qwen2.5-coder:14b", BackendLocation.LOCAL)

        def complete(self, request: AIRequest) -> AIResponse:
            requests.append(request)
            return AIResponse(
                message=AIMessage(MessageRole.ASSISTANT, f"answer {len(requests)}"),
                backend=self.backend,
            )

    chat_db = tmp_path / "repo-assistant-chats.sqlite3"
    monkeypatch.setattr(_EXAMPLE, "create_chat_client", lambda config: FakeClient())

    first_args = [
        "--repo-root",
        str(tmp_path),
        "--mode",
        "chat",
        "--execute",
        "--provider",
        "ollama",
        "--model",
        "qwen2.5-coder:14b",
        "--skip-prompt-review",
        "--chat-db",
        str(chat_db),
        "Remember this first turn.",
    ]
    assert main(first_args) == 0
    first_output = capsys.readouterr().out
    store = SQLiteChatTranscriptStore(chat_db)
    session = store.latest_session(repo_root=tmp_path.resolve())
    assert session is not None

    second_args = [
        "--repo-root",
        str(tmp_path),
        "--mode",
        "chat",
        "--execute",
        "--provider",
        "ollama",
        "--model",
        "qwen2.5-coder:14b",
        "--skip-prompt-review",
        "--chat-db",
        str(chat_db),
        "--chat-session",
        "last",
        "Use the previous turn.",
    ]
    assert main(second_args) == 0
    second_output = capsys.readouterr().out

    assert f"chat_session_id: {session.session_id}" in first_output
    assert f"chat_session_id: {session.session_id}" in second_output
    for output, response in ((first_output, "answer 1"), (second_output, "answer 2")):
        assert output.count("## **SUMMARY**") == 1
        assert "- Validated: Not run by the CLI" in output
        assert f"### Agent report\n{response}" in output
    assert len(requests) == 2
    assert [message.role for message in requests[1].messages] == [
        MessageRole.SYSTEM,
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.USER,
    ]
    assert "Remember this first turn." in requests[1].messages[1].content
    assert requests[1].messages[2].content == "answer 1"
    assert "Use the previous turn." in requests[1].messages[3].content
    assert "## **SUMMARY**" in requests[0].messages[0].content
    assert [message.role for message in store.list_messages(session.session_id)] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_chat_mode_uses_rolling_summary_when_history_exceeds_budget(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    from ai_provider import (
        AIMessage,
        AIRequest,
        AIResponse,
        BackendInfo,
        BackendLocation,
        MessageRole,
        SQLiteChatTranscriptStore,
    )

    requests: list[AIRequest] = []

    class FakeClient:
        backend = BackendInfo("ollama", "qwen2.5-coder:14b", BackendLocation.LOCAL)

        def complete(self, request: AIRequest) -> AIResponse:
            requests.append(request)
            if request.metadata.get("task_type") == "chat_rolling_summary":
                return AIResponse(
                    message=AIMessage(
                        MessageRole.ASSISTANT,
                        "Earlier turns captured a long requirement.",
                    ),
                    backend=self.backend,
                )
            return AIResponse(
                message=AIMessage(MessageRole.ASSISTANT, "bounded answer"),
                backend=self.backend,
            )

    repo_root = tmp_path.resolve()
    chat_db = tmp_path / "repo-assistant-chats.sqlite3"
    store = SQLiteChatTranscriptStore(chat_db)
    session = store.create_session(
        repo_root=repo_root,
        title="Long chat",
        privacy_class="local_only",
    )
    store.append_message(session.session_id, role=MessageRole.SYSTEM, content="system")
    store.append_message(
        session.session_id,
        role=MessageRole.USER,
        content="old user " + ("x" * 3000),
    )
    store.append_message(
        session.session_id,
        role=MessageRole.ASSISTANT,
        content="old answer " + ("y" * 3000),
    )
    monkeypatch.setattr(_EXAMPLE, "create_chat_client", lambda config: FakeClient())

    assert (
        main(
            [
                "--repo-root",
                str(repo_root),
                "--mode",
                "chat",
                "--execute",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--skip-prompt-review",
                "--chat-db",
                str(chat_db),
                "--chat-session",
                session.session_id,
                "--chat-history-budget-chars",
                "5000",
                "--chat-recent-message-count",
                "1",
                "Use the current request.",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out

    assert len(requests) == 2
    assert requests[0].metadata["task_type"] == "chat_rolling_summary"
    final_messages = requests[1].messages
    assert [message.role for message in final_messages] == [
        MessageRole.SYSTEM,
        MessageRole.SYSTEM,
        MessageRole.USER,
    ]
    assert final_messages[1].content.startswith("Rolling summary of earlier chat turns.")
    assert "Earlier turns captured a long requirement." in final_messages[1].content
    assert "Use the current request." in final_messages[2].content
    assert all("old user" not in message.content for message in final_messages)
    assert "chat_context_summary_used: True" in output
    assert "chat_context_summary_updated: True" in output
    assert "chat_context_omitted_message_count: 2" in output
    summary = store.get_rolling_summary(session.session_id)
    assert summary is not None
    assert summary.covered_message_order == 3
