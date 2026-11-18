"""Port contract: verdict validation rejects malformed adapter output."""

from __future__ import annotations

import pytest
from ai_orchestrator.deliberation import validate_verdict


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
