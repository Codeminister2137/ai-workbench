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


def test_skills_and_career_categories_accepted(tmp_path) -> None:
    store = KnowMeStore(tmp_path / "bank.sqlite3")
    store.add("skills", "Python, Django, FastAPI.", "import")
    store.add("career", "ZF 2024-2026.", "import")
    assert [entry.category for entry in store.find()] == ["career", "skills"]
    assert store.find(category="skills")[0].text.startswith("Python")


def test_plan_context_formats_entries(tmp_path) -> None:
    from knowme_bank.consumer import plan_context

    store = KnowMeStore(tmp_path / "bank.sqlite3")
    assert "empty" in plan_context(store, "training")
    store.add("training", "Runs 3x/week.", "interview")
    block = plan_context(store, "training")
    assert "[interview] Runs 3x/week." in block


def test_propose_facts_splits_lists() -> None:
    from knowme_bank.ingest import propose_facts

    assert propose_facts("Docker, AWS, Linux.") == ["Docker", "AWS", "Linux."]
    assert propose_facts("Python; Django; FastAPI") == ["Python", "Django", "FastAPI"]
    assert propose_facts("Python\nDjango\n\nFastAPI") == ["Python", "Django", "FastAPI"]
    assert propose_facts("  ") == []
    assert propose_facts("") == []


def test_propose_facts_preserves_context_and_prose() -> None:
    from knowme_bank.ingest import propose_facts

    assert propose_facts("CI/CD (Jenkins, CircleCI)") == ["CI/CD (Jenkins, CircleCI)"]
    assert propose_facts("Skills: Python, Django") == ["Python", "Django"]
    assert propose_facts(": Python, Django") == ["Python", "Django"]
    assert propose_facts("Work: ZF (2020-2022)") == ["ZF (2020-2022)"]
    assert propose_facts("I joined ZF in 2020, and left in 2022.") == [
        "I joined ZF in 2020, and left in 2022."
    ]
    assert propose_facts("Senior Engineer at ZF, 2024-2026") == ["Senior Engineer at ZF, 2024-2026"]


def test_add_roundtrips_provenance(tmp_path) -> None:
    store = KnowMeStore(tmp_path / "bank.sqlite3")
    entry = store.add(
        "skills",
        "Python",
        "import",
        source_file="cv.txt",
        origin_text="Python, Django",
    )
    assert entry.source_file == "cv.txt"
    assert entry.origin_text == "Python, Django"
    reopened = KnowMeStore(tmp_path / "bank.sqlite3")
    found = reopened.find(category="skills")[0]
    assert (found.source_file, found.origin_text) == ("cv.txt", "Python, Django")
    assert reopened.count() == 1


def test_add_rejects_bad_provenance(tmp_path) -> None:
    store = KnowMeStore(tmp_path / "bank.sqlite3")
    with pytest.raises(ValueError, match="source_file"):
        store.add("skills", "Python", "import", source_file="   ")
    with pytest.raises(ValueError, match="source_file"):
        store.add("skills", "Python", "import", source_file=123)
    blank_origin = store.add("skills", "Python", "import", origin_text="  ")
    assert blank_origin.origin_text is None
    assert store.count() == 1


def test_old_database_opens_without_invented_provenance(tmp_path) -> None:
    import sqlite3

    path = tmp_path / "bank.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE entries (id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " category TEXT NOT NULL, text TEXT NOT NULL,"
            " source TEXT NOT NULL, created_at REAL NOT NULL)"
        )
        connection.execute(
            "INSERT INTO entries (category, text, source, created_at)"
            " VALUES ('skills', 'Python, Django.', 'import', 1794076200.0)"
        )
    store = KnowMeStore(path)
    old = store.find()[0]
    assert old.text == "Python, Django."
    assert old.source_file is None
    assert old.origin_text is None
    store.add("skills", "Go", "import", source_file="cv.txt")
    assert store.count() == 2
    assert store.find()[0].source_file == "cv.txt"


def test_import_facts_banks_proposals_with_origin(tmp_path) -> None:
    from knowme_bank.ingest import import_facts

    store = KnowMeStore(tmp_path / "bank.sqlite3")
    entries = import_facts(store, "skills", "Docker, AWS", source_file="cv.txt")
    assert [entry.text for entry in entries] == ["Docker", "AWS"]
    assert all(entry.origin_text == "Docker, AWS" for entry in entries)
    assert all(entry.source_file == "cv.txt" for entry in entries)
    assert store.count() == 2


def test_import_facts_explicit_facts_override_proposals(tmp_path) -> None:
    from knowme_bank.ingest import import_facts

    store = KnowMeStore(tmp_path / "bank.sqlite3")
    entries = import_facts(
        store, "skills", "Docker, AWS", source_file="cv.txt", facts=["Docker + AWS"]
    )
    assert [entry.text for entry in entries] == ["Docker + AWS"]
    assert entries[0].origin_text == "Docker, AWS"


def test_repeat_import_banks_again_without_dedup(tmp_path) -> None:
    from knowme_bank.ingest import import_facts

    store = KnowMeStore(tmp_path / "bank.sqlite3")
    import_facts(store, "skills", "Docker, AWS", source_file="cv.txt")
    import_facts(store, "skills", "Docker, AWS", source_file="cv.txt")
    assert store.count() == 4


def test_plan_context_shows_source_file(tmp_path) -> None:
    from knowme_bank.consumer import plan_context

    store = KnowMeStore(tmp_path / "bank.sqlite3")
    store.add("skills", "Python", "import", source_file="cv.txt")
    block = plan_context(store, "skills")
    assert "[import:cv.txt] Python" in block


def test_interview_banks_list_answer_as_atomic_facts(monkeypatch, tmp_path) -> None:
    store = KnowMeStore(tmp_path / "bank.sqlite3")
    answers = iter(["Running, lifting", "", "", "", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    ids = run_interview(store)
    assert len(ids) == 2
    assert {entry.text for entry in store.find(category="training")} == {
        "Running",
        "lifting",
    }
