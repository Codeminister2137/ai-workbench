from __future__ import annotations

from domain import parse_synthesis


def test_parse_full_consensus() -> None:
    verdict = parse_synthesis(
        "AGREED:\n- Ship it\n- Tests first\nDISAGREEMENTS:\nNEXT:\n- Merge\nCONSENSUS: full\n"
    )
    assert verdict.parse_ok is True
    assert verdict.agreed == ("Ship it", "Tests first")
    assert verdict.disagreements == ()
    assert verdict.next_actions == ("Merge",)
    assert verdict.consensus == "full"


def test_parse_partial_with_named_holders() -> None:
    verdict = parse_synthesis(
        "AGREED:\n- Ship it\nDISAGREEMENTS:\n- Alice, Bob: too risky\n"
        "NEXT:\n- Pilot first\nCONSENSUS: partial\n"
    )
    assert verdict.parse_ok is True
    assert verdict.consensus == "partial"
    (disagreement,) = verdict.disagreements
    assert disagreement.holders == ("Alice", "Bob")
    assert disagreement.point == "too risky"


def test_parse_rejects_anonymous_disagreement() -> None:
    verdict = parse_synthesis(
        "AGREED:\n- Ship it\nDISAGREEMENTS:\n- too risky\nNEXT:\n- Ask\nCONSENSUS: partial\n"
    )
    assert verdict.parse_ok is False
    assert verdict.disagreements == ()


def test_parse_rejects_missing_consensus() -> None:
    verdict = parse_synthesis("AGREED:\n- Ship it\nNEXT:\n- Merge\n")
    assert verdict.parse_ok is False
    assert verdict.consensus == "none"


def test_parse_empty_is_not_ok() -> None:
    verdict = parse_synthesis("free prose without sections")
    assert verdict.parse_ok is False
    assert verdict.agreed == ()
