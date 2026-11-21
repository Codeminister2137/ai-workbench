from __future__ import annotations

import pytest
from config import load_config
from deliberation_port import CouncilDeliberationPort
from storage import ConversationStore

from tests.helpers import write_config


class FakeAgent:
    def __init__(self, member, ollama_base_url=None):
        self.member = member

    def answer(self, conversation):
        return f"{self.member.name} answered"

    def react(self, conversation, peer_answers):
        return f"{self.member.name} reacts"

    def synthesize(self, conversation, answers):
        return (
            "AGREED:\n- Ship it\nDISAGREEMENTS:\n- Bob: too risky\n"
            "NEXT:\n- Pilot\nCONSENSUS: partial\n"
        )


def _port(tmp_path, monkeypatch) -> CouncilDeliberationPort:
    from dataclasses import replace

    config_path = tmp_path / "council.json"
    write_config(config_path)
    monkeypatch.setattr("council.LocalAgent", FakeAgent)
    return CouncilDeliberationPort(
        replace(load_config(config_path), max_rounds=3), ConversationStore(tmp_path / "c.sqlite3")
    )


def test_deliberate_returns_validated_verdict(tmp_path, monkeypatch) -> None:
    port = _port(tmp_path, monkeypatch)
    verdict = port.deliberate("Ship?", [{"name": "Analyst"}, {"name": "Skeptic"}])
    assert verdict["consensus"] == "partial"
    assert verdict["agreed"] == ["Ship it"]
    assert verdict["parse_ok"] is True


def test_deliberate_rejects_unknown_members(tmp_path, monkeypatch) -> None:
    port = _port(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="unknown council members"):
        port.deliberate("Ship?", [{"name": "Mallory"}])


def test_deliberate_without_synthesis_round_fails(tmp_path, monkeypatch) -> None:
    port = _port(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="no structured verdict"):
        port.deliberate("Ship?", [], rounds=1)
