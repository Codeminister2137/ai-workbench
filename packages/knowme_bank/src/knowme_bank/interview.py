"""Interview bootstrap: question set answers become bank entries."""

from __future__ import annotations

import argparse
from pathlib import Path

from knowme_bank import KnowMeStore

QUESTIONS: tuple[tuple[str, str, str], ...] = (
    (
        "training",
        "How do you train in a typical week (sports, frequency, intensity)?",
        "interview",
    ),
    (
        "training",
        "Any injuries, limits, or things a coach must never program for you?",
        "interview",
    ),
    (
        "diet",
        "How do you eat on a normal day, and what does 'eating well' mean to you?",
        "interview",
    ),
    (
        "preference",
        "How blunt should coaching advice be, and when should the coach stay quiet?",
        "interview",
    ),
    (
        "note",
        "Anything else the bank should know first (goals, schedule, equipment)?",
        "interview",
    ),
)

DEMO_SEED: tuple[tuple[str, str, str], ...] = (
    ("training", "Demo: runs 3x/week, lifts 2x/week.", "demo"),
    ("training", "Demo: left knee dislikes deep lunges.", "demo"),
    ("diet", "Demo: high-protein breakfast, light dinner.", "demo"),
)


def run_interview(store: KnowMeStore, *, seed_demo: bool = False) -> list[int]:
    """Ask (or seed) and store; returns new entry ids."""
    if seed_demo:
        return [store.add(category, text, source).id for category, text, source in DEMO_SEED]
    ids: list[int] = []
    print("Know-me interview. Blank answer skips a question; Ctrl+C aborts.\n")
    try:
        for category, question, source in QUESTIONS:
            print(question)
            answer = input("> ").strip()
            if answer:
                ids.append(store.add(category, answer, source).id)
    except (KeyboardInterrupt, EOFError):
        print("\nStopped; kept what was answered.")
    print(f"Banked {len(ids)} entries.")
    return ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap the know-me bank.")
    parser.add_argument("--db", type=Path, default=Path("data/knowme.sqlite3"))
    parser.add_argument("--seed-demo", action="store_true")
    args = parser.parse_args(argv)
    run_interview(KnowMeStore(args.db), seed_demo=args.seed_demo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
