from __future__ import annotations

from evals.score import aggregate, score_question


def test_perfect_verdict_scores_one() -> None:
    verdict = {
        "agreed": ["Ship it"],
        "disagreements": [{"holders": ["Bob"], "point": "too risky"}],
        "next_actions": ["Pilot now"],
        "consensus": "partial",
        "parse_ok": True,
    }
    scores = score_question(verdict, ["Alice", "Bob"], ["ship", "pilot"])
    assert scores == {
        "parse_ok": 1.0,
        "holders_valid": 1.0,
        "calibrated": 1.0,
        "recall": 1.0,
        "overall": 1.0,
    }


def test_unknown_holder_fails_attribution() -> None:
    verdict = {
        "agreed": [],
        "disagreements": [{"holders": ["Mallory"], "point": "no"}],
        "next_actions": [],
        "consensus": "partial",
        "parse_ok": True,
    }
    scores = score_question(verdict, ["Alice"], [])
    assert scores["holders_valid"] == 0.0
    assert scores["overall"] == 0.75


def test_full_with_dissent_is_miscalibrated() -> None:
    verdict = {
        "agreed": ["Ship it"],
        "disagreements": [{"holders": ["Bob"], "point": "too risky"}],
        "next_actions": [],
        "consensus": "full",
        "parse_ok": True,
    }
    assert score_question(verdict, ["Alice", "Bob"], [])["calibrated"] == 0.0


def test_none_with_agreement_is_miscalibrated() -> None:
    verdict = {
        "agreed": ["Ship it"],
        "disagreements": [],
        "next_actions": [],
        "consensus": "none",
        "parse_ok": True,
    }
    assert score_question(verdict, ["Alice"], [])["calibrated"] == 0.0


def test_recall_counts_reference_hits() -> None:
    verdict = {
        "agreed": ["Ship the thing"],
        "disagreements": [],
        "next_actions": ["Unrelated"],
        "consensus": "partial",
        "parse_ok": True,
    }
    assert score_question(verdict, ["Alice"], ["ship", "pilot"])["recall"] == 0.5


def test_aggregate_means_metrics() -> None:
    per_question = {
        "q1": {
            "parse_ok": 1.0,
            "holders_valid": 1.0,
            "calibrated": 1.0,
            "recall": 1.0,
            "overall": 1.0,
        },
        "q2": {
            "parse_ok": 0.0,
            "holders_valid": 1.0,
            "calibrated": 1.0,
            "recall": 0.0,
            "overall": 0.5,
        },
    }
    totals = aggregate(per_question)
    assert totals == {
        "parse_ok": 0.5,
        "holders_valid": 1.0,
        "calibrated": 1.0,
        "recall": 0.5,
        "overall": 0.75,
    }
    assert aggregate({})["overall"] == 0.0
