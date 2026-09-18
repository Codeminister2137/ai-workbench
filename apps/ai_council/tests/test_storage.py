from __future__ import annotations

import sqlite3

import pytest

from storage import ConversationStore


def test_creates_database_parent_directory(tmp_path) -> None:
    db_path = tmp_path / "nested" / "council.sqlite3"

    store = ConversationStore(db_path)
    store.close()

    assert db_path.exists()


def test_persists_messages_across_store_instances(tmp_path) -> None:
    db_path = tmp_path / "council.sqlite3"
    store = ConversationStore(db_path)
    conversation_id = store.get_or_create_conversation("health")
    store.add_message(conversation_id, "user", "Private note")
    store.add_message(
        conversation_id,
        "assistant",
        "Answer",
        member_name="Analyst",
        model="llama3.2",
    )
    store.close()

    reopened = ConversationStore(db_path)
    same_id = reopened.get_or_create_conversation("health")
    messages = reopened.list_messages(same_id)
    reopened.close()

    assert same_id == conversation_id
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["member_name"] == "Analyst"
    assert messages[1]["model"] == "llama3.2"


def test_rejects_unknown_message_roles(tmp_path) -> None:
    store = ConversationStore(tmp_path / "council.sqlite3")
    conversation_id = store.get_or_create_conversation("default")

    with pytest.raises(sqlite3.IntegrityError):
        store.add_message(conversation_id, "system", "Not allowed")

    store.close()


def test_history_survives_model_name_changes(tmp_path) -> None:
    db_path = tmp_path / "council.sqlite3"
    store = ConversationStore(db_path)
    conversation_id = store.get_or_create_conversation("portable")
    store.add_message(
        conversation_id,
        "assistant",
        "Old answer",
        member_name="Analyst",
        model="llama3.2",
    )
    store.add_message(
        conversation_id,
        "assistant",
        "New answer",
        member_name="Analyst",
        model="mistral",
    )

    messages = store.list_messages(conversation_id)
    store.close()

    assert [message["model"] for message in messages] == ["llama3.2", "mistral"]
