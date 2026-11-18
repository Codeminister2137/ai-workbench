"""Port contract: verdict validation rejects malformed adapter output."""

from __future__ import annotations

from typing import Any

import pytest
from ai_orchestrator.deliberation import request_verdict, validate_verdict


def _valid() -> dict:
    return {
        "agreed": ["Ship it"],
        "disagreements": [{"holders": ["Bob"], "point": "too risky"}],
        "next_actions": ["Pilot"],
        "consensus": "partial",
        "parse_ok": True,
    }


def test_validate_accepts_well_formed_verdict() -> None:
    verdict = validate_verdict(_valid())
    assert verdict["consensus"] == "partial"
    assert verdict["disagreements"][0]["holders"] == ["Bob"]
    assert verdict["parse_ok"] is True


def test_validate_rejects_bad_consensus() -> None:
    payload = _valid()
    payload["consensus"] = "maybe"
    with pytest.raises(ValueError, match="consensus"):
        validate_verdict(payload)


def test_validate_rejects_holderless_disagreement() -> None:
    payload = _valid()
    payload["disagreements"] = [{"holders": "Bob", "point": "x"}]
    with pytest.raises(ValueError, match="holders"):
        validate_verdict(payload)


def test_validate_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="object"):
        validate_verdict([])  # type: ignore[arg-type]


def test_validate_defaults_parse_ok_false() -> None:
    payload = _valid()
    del payload["parse_ok"]
    assert validate_verdict(payload)["parse_ok"] is False


class _FakePort:
    """DeliberationPort double recording its inputs."""

    def __init__(self, verdict: dict[str, Any] | Exception) -> None:
        self._verdict = verdict
        self.calls: list[tuple[str, list, int]] = []

    def deliberate(
        self, question: str, members: list[dict[str, Any]], *, rounds: int = 3
    ) -> dict[str, Any]:
        self.calls.append((question, members, rounds))
        if isinstance(self._verdict, Exception):
            raise self._verdict
        return self._verdict


def test_request_verdict_delegates_and_validates() -> None:
    port = _FakePort(_valid())
    verdict = request_verdict(port, "Ship?", [{"name": "Ann"}], rounds=2)
    assert verdict["consensus"] == "partial"
    assert port.calls == [("Ship?", [{"name": "Ann"}], 2)]


def test_request_verdict_rejects_malformed_adapter_output() -> None:
    payload = _valid()
    payload["consensus"] = "maybe"
    with pytest.raises(ValueError, match="consensus"):
        request_verdict(_FakePort(payload), "Ship?")


def test_request_verdict_passes_through_port_errors() -> None:
    with pytest.raises(RuntimeError, match="no structured verdict"):
        request_verdict(_FakePort(RuntimeError("council returned no structured verdict")), "Ship?")


def test_request_verdict_validates_inputs() -> None:
    port = _FakePort(_valid())
    with pytest.raises(ValueError, match="question"):
        request_verdict(port, "  ")
    with pytest.raises(ValueError, match="round"):
        request_verdict(port, "Ship?", rounds=0)
    assert port.calls == []
