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

    def react(self, conversation, peer_answers):
        names = ",".join(name for name, _ in peer_answers)
        return f"{self.member.name} reacts to {names}"

    def stream_react(self, conversation, peer_answers):
        yield f"{self.member.name} reacts"

    def synthesize(self, conversation, answers):
        return f"synthesis of {len(answers)} positions"

    def stream_synthesize(self, conversation, answers):
        yield "synthesis"


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


def test_ask_isolates_per_member_failures_and_continues(tmp_path, monkeypatch) -> None:
    class FailingFirstAgent(FakeAgent):
        def answer(self, conversation):
            if self.member.name == "Analyst":
                raise RuntimeError("model unavailable")
            return super().answer(conversation)

    config_path = tmp_path / "council.json"
    db_path = tmp_path / "council.sqlite3"
    write_config(config_path)
    config = load_config(config_path)
    store = ConversationStore(db_path)

    monkeypatch.setattr("council.LocalAgent", FailingFirstAgent)
    answers = LocalCouncil(config, store).ask("Question?")

    conversation_id = store.get_or_create_conversation("test-conversation")
    messages = store.list_messages(conversation_id)
    store.close()

    # still returns one entry per member
    assert len(answers) == 2
    assert [a["member"] for a in answers] == ["Analyst", "Skeptic"]

    failed = answers[0]
    assert failed["member"] == "Analyst"
    assert failed["answer"] == ""
    assert "error" in failed
    assert failed["error"] != ""
    assert "model unavailable" in failed["error"]
    # model field is present
    assert "model" in failed

    healthy = answers[1]
    assert healthy["member"] == "Skeptic"
    assert healthy["answer"] != ""
    assert healthy["answer"] == "Skeptic answered after 1 messages"

    # failed answers are NOT stored as assistant messages
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "Question?"
    assert messages[1]["content"] == healthy["answer"]
    assert messages[1]["member_name"] == "Skeptic"


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
        event["type"] == "member_finished" and event["member"] == "Skeptic" for event in events
    )


def _council(tmp_path, monkeypatch, agent=FakeAgent):
    config_path = tmp_path / "council.json"
    db_path = tmp_path / "council.sqlite3"
    write_config(config_path)
    config = load_config(config_path)
    store = ConversationStore(db_path)
    monkeypatch.setattr("council.LocalAgent", agent)
    return LocalCouncil(config, store), store


def test_ask_rounds_two_collects_reactions(tmp_path, monkeypatch) -> None:
    council, store = _council(tmp_path, monkeypatch)
    answers = council.ask("Question?", rounds=2)
    rounds = [item.get("round", "1") for item in answers]
    assert rounds == ["1", "1", "2", "2"]
    assert answers[2]["answer"] == "Analyst reacts to Skeptic"
    messages = store.list_messages(store.get_or_create_conversation("test-conversation"))
    store.close()
    assert [message["round"] for message in messages] == [1, 1, 1, 2, 2]


def test_ask_rounds_three_synthesizes_with_chair(tmp_path, monkeypatch) -> None:
    council, store = _council(tmp_path, monkeypatch)
    answers = council.ask("Question?", rounds=3)
    synthesis = answers[-1]
    assert synthesis["member"] == "Analyst:synthesis"
    assert synthesis["answer"] == "synthesis of 4 positions"
    assert synthesis["round"] == "3"
    store.close()


def test_token_cap_marks_synthesis_partial(tmp_path, monkeypatch) -> None:
    import json

    config_path = tmp_path / "council.json"
    db_path = tmp_path / "council.sqlite3"
    write_config(config_path)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    raw["max_tokens_per_question"] = 1
    config_path.write_text(json.dumps(raw), encoding="utf-8")
    config = load_config(config_path)
    store = ConversationStore(db_path)
    monkeypatch.setattr("council.LocalAgent", FakeAgent)
    answers = LocalCouncil(config, store).ask("Question?", rounds=3)
    store.close()
    assert answers[-1].get("partial") == "token cap reached"


def test_ask_events_emits_round_events(tmp_path, monkeypatch) -> None:
    council, store = _council(tmp_path, monkeypatch)
    events = list(council.ask_events("Question?", rounds=3))
    store.close()
    kinds = [event["type"] for event in events]
    assert kinds.count("round_started") == 2
    assert kinds.count("reaction_finished") == 2
    assert kinds.count("synthesis_finished") == 1
    assert kinds[-1] == "council_finished"


def test_legacy_rows_read_as_round_one(tmp_path, monkeypatch) -> None:
    import sqlite3

    council, store = _council(tmp_path, monkeypatch)
    council.ask("Question?")
    with sqlite3.connect(tmp_path / "council.sqlite3") as connection:
        connection.execute("UPDATE messages SET round = NULL")
        connection.commit()
    messages = store.list_messages(store.get_or_create_conversation("test-conversation"))
    store.close()
    assert {message["round"] for message in messages} == {1}


def test_config_rejects_bad_chair_and_rounds(tmp_path) -> None:
    import json

    import pytest

    config_path = tmp_path / "council.json"
    write_config(config_path)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    raw["chair"] = "Nobody"
    config_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="not a member"):
        load_config(config_path)
    raw["chair"] = None
    raw["max_rounds"] = 9
    config_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="max_rounds"):
        load_config(config_path)
