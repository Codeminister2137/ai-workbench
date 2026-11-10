"""Know-me bank: store, validation, interview seed."""

from __future__ import annotations

import pytest
from knowme_bank import KnowMeStore
from knowme_bank.interview import DEMO_SEED, run_interview


def test_round_trip_and_filter(tmp_path) -> None:
    store = KnowMeStore(tmp_path / "bank.sqlite3")
    first = store.add("training", "Runs 3x/week.", "interview")
    store.add("diet", "High-protein breakfast.", "note")
    assert first.id == 1
    assert store.count() == 2
    training = store.find(category="training")
    assert [entry.text for entry in training] == ["Runs 3x/week."]
    assert training[0].source == "interview"
    assert len(store.find()) == 2


def test_rejects_bad_category_source_and_blanks(tmp_path) -> None:
    store = KnowMeStore(tmp_path / "bank.sqlite3")
    with pytest.raises(ValueError, match="category"):
        store.add("nope", "x", "interview")
    with pytest.raises(ValueError, match="source"):
        store.add("training", "x", "nope")
    with pytest.raises(ValueError, match="blank"):
        store.add("training", "   ", "interview")
    with pytest.raises(ValueError, match="category"):
        store.find(category="nope")
    assert store.count() == 0


def test_persists_across_opens(tmp_path) -> None:
    path = tmp_path / "bank.sqlite3"
    KnowMeStore(path).add("preference", "Blunt coaching.", "interview")
    reopened = KnowMeStore(path)
    assert reopened.count() == 1
    assert reopened.find()[0].text == "Blunt coaching."


def test_demo_seed_banks_three(tmp_path) -> None:
    store = KnowMeStore(tmp_path / "bank.sqlite3")
    ids = run_interview(store, seed_demo=True)
    assert len(ids) == len(DEMO_SEED) == 3
    assert store.count() == 3
    assert {entry.source for entry in store.find()} == {"demo"}


def test_interview_skips_blanks(monkeypatch, tmp_path) -> None:
    store = KnowMeStore(tmp_path / "bank.sqlite3")
    answers = iter(["I lift twice a week.", "", "Oats.", "", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    ids = run_interview(store)
    assert len(ids) == 2
    assert store.find(category="training")[0].text == "I lift twice a week."


def test_plan_context_formats_entries(tmp_path) -> None:
    from knowme_bank.consumer import plan_context

    store = KnowMeStore(tmp_path / "bank.sqlite3")
    assert "empty" in plan_context(store, "training")
    store.add("training", "Runs 3x/week.", "interview")
    block = plan_context(store, "training")
    assert "[interview] Runs 3x/week." in block
