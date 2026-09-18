from __future__ import annotations

from config import load_config
from council import LocalCouncil
from storage import ConversationStore
from tests.helpers import write_config


class FakeAgent:
    def __init__(self, member, ollama_base_url=None):
        self.member = member
        self.ollama_base_url = ollama_base_url

    def answer(self, conversation):
        return f"{self.member.name} answered after {len(conversation)} messages"

    def stream_answer(self, conversation):
        yield f"{self.member.name} "
        yield "streamed"


def test_ask_collects_one_answer_per_member_and_persists_them(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "council.json"
    db_path = tmp_path / "council.sqlite3"
    write_config(config_path)
    config = load_config(config_path)
    store = ConversationStore(db_path)

    monkeypatch.setattr("council.LocalAgent", FakeAgent)
    answers = LocalCouncil(config, store).ask("Question?")

    conversation_id = store.get_or_create_conversation("test-conversation")
    messages = store.list_messages(conversation_id)
    store.close()

    assert [answer["member"] for answer in answers] == ["Analyst", "Skeptic"]
    assert [message["role"] for message in messages] == ["user", "assistant", "assistant"]
    assert messages[0]["content"] == "Question?"


def test_ask_events_has_stable_streaming_contract(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "council.json"
    db_path = tmp_path / "council.sqlite3"
    write_config(config_path)
    config = load_config(config_path)
    store = ConversationStore(db_path)

    monkeypatch.setattr("council.LocalAgent", FakeAgent)
    events = list(LocalCouncil(config, store).ask_events("Question?"))
    store.close()

    event_types = [event["type"] for event in events]
    assert event_types[0] == "council_started"
    assert event_types[-1] == "council_finished"
    assert event_types.count("member_started") == 2
    assert event_types.count("member_finished") == 2
    assert event_types.count("member_delta") == 4


def test_ask_events_reports_member_error_and_continues(tmp_path, monkeypatch) -> None:
    class FailingFirstAgent(FakeAgent):
        def stream_answer(self, conversation):
            if self.member.name == "Analyst":
                raise RuntimeError("model unavailable")
            yield "ok"

    config_path = tmp_path / "council.json"
    db_path = tmp_path / "council.sqlite3"
    write_config(config_path)
    config = load_config(config_path)
    store = ConversationStore(db_path)

    monkeypatch.setattr("council.LocalAgent", FailingFirstAgent)
    events = list(LocalCouncil(config, store).ask_events("Question?"))
    store.close()

    assert "member_error" in [event["type"] for event in events]
    assert events[-1]["type"] == "council_finished"
    assert any(
        event["type"] == "member_finished" and event["member"] == "Skeptic"
        for event in events
    )
