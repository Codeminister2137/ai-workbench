from __future__ import annotations

from pathlib import Path

from ai_provider import MessageRole, SQLiteChatTranscriptStore
from ai_provider.chat_transcripts import messages_to_ai_messages


def test_sqlite_chat_transcript_store_persists_ordered_provider_neutral_messages(
    tmp_path: Path,
) -> None:
    store = SQLiteChatTranscriptStore(tmp_path / "chats.sqlite3")
    session = store.create_session(
        repo_root=tmp_path,
        title="Explain the selected module.",
        privacy_class="local_only",
    )

    store.append_message(session.session_id, role=MessageRole.SYSTEM, content="system prompt")
    store.append_message(session.session_id, role=MessageRole.USER, content="first question")
    store.append_message(
        session.session_id,
        role=MessageRole.ASSISTANT,
        content="first answer",
        provider="ollama",
        model="qwen2.5-coder:14b",
        metadata={"total_tokens": 12},
    )

    messages = store.list_messages(session.session_id)

    assert [message.message_order for message in messages] == [1, 2, 3]
    assert [message.role for message in messages] == ["system", "user", "assistant"]
    assert messages[2].provider == "ollama"
    assert messages[2].metadata == {"total_tokens": 12}
    assert [message.content for message in messages_to_ai_messages(messages)] == [
        "system prompt",
        "first question",
        "first answer",
    ]


def test_sqlite_chat_transcript_store_can_find_latest_repo_session(tmp_path: Path) -> None:
    store = SQLiteChatTranscriptStore(tmp_path / "chats.sqlite3")
    first = store.create_session(repo_root=tmp_path, title="First", privacy_class="local_only")
    second = store.create_session(repo_root=tmp_path, title="Second", privacy_class="local_only")
    store.append_message(second.session_id, role=MessageRole.USER, content="recent")

    latest = store.latest_session(repo_root=tmp_path)

    assert latest is not None
    assert latest.session_id == second.session_id
    assert [session.session_id for session in store.list_sessions()] == [
        second.session_id,
        first.session_id,
    ]


def test_sqlite_chat_transcript_store_persists_rolling_summary(tmp_path: Path) -> None:
    store = SQLiteChatTranscriptStore(tmp_path / "chats.sqlite3")
    session = store.create_session(
        repo_root=tmp_path,
        title="Summarize chat.",
        privacy_class="local_only",
    )

    summary = store.upsert_rolling_summary(
        session.session_id,
        summary="Earlier turns established the repo assistant context.",
        covered_message_order=4,
        provider="ollama",
        model="qwen2.5-coder:14b",
        metadata={"total_tokens": 42},
    )

    assert summary.session_id == session.session_id
    assert summary.covered_message_order == 4
    persisted = store.get_rolling_summary(session.session_id)
    assert persisted is not None
    assert persisted.summary == "Earlier turns established the repo assistant context."
    assert persisted.provider == "ollama"
    assert persisted.model == "qwen2.5-coder:14b"

    replacement = store.upsert_rolling_summary(
        session.session_id,
        summary="Updated summary.",
        covered_message_order=8,
    )

    assert replacement.covered_message_order == 8
    updated = store.get_rolling_summary(session.session_id)
    assert updated is not None
    assert updated.summary == "Updated summary."
