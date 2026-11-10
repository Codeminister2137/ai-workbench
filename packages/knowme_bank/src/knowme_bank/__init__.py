"""Local-first personal knowledge bank (SQLite, no network)."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

CATEGORIES = ("training", "diet", "preference", "health", "note")
SOURCES = ("interview", "xiaomi", "note", "demo", "import")


@dataclass(frozen=True, slots=True)
class KnowMeEntry:
    """One banked fact about the owner."""

    id: int
    category: str
    text: str
    source: str
    created_at: float


class KnowMeStore:
    """Tiny SQLite store; one file, no migrations yet (v1 schema)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    text TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_entries_category ON entries(category)"
            )

    def add(self, category: str, text: str, source: str) -> KnowMeEntry:
        """Store one entry; validates category/source, rejects blanks."""
        if category not in CATEGORIES:
            raise ValueError(f"Unknown category: {category!r}")
        if source not in SOURCES:
            raise ValueError(f"Unknown source: {source!r}")
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Entry text must not be blank")
        created = time.time()
        with sqlite3.connect(self.path) as connection:
            cursor = connection.execute(
                "INSERT INTO entries (category, text, source, created_at) VALUES (?, ?, ?, ?)",
                (category, cleaned, source, created),
            )
            entry_id = cursor.lastrowid
        assert entry_id is not None
        return KnowMeEntry(
            id=entry_id, category=category, text=cleaned, source=source, created_at=created
        )

    def find(self, category: str | None = None, *, limit: int = 50) -> list[KnowMeEntry]:
        """Newest-first entries, optionally filtered by category."""
        if category is not None and category not in CATEGORIES:
            raise ValueError(f"Unknown category: {category!r}")
        query = "SELECT id, category, text, source, created_at FROM entries"
        params: tuple[object, ...] = ()
        if category is not None:
            query += " WHERE category = ?"
            params = (category,)
        query += " ORDER BY id DESC LIMIT ?"
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(query, (*params, limit)).fetchall()
        return [KnowMeEntry(*row) for row in rows]

    def count(self) -> int:
        """Total entries banked."""
        with sqlite3.connect(self.path) as connection:
            row = connection.execute("SELECT COUNT(*) FROM entries").fetchone()
        return int(row[0])

    def iter_all(self) -> Iterator[KnowMeEntry]:
        """Stream every entry, oldest first (exports, reviews)."""
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                "SELECT id, category, text, source, created_at FROM entries ORDER BY id ASC"
            ).fetchall()
        for row in rows:
            yield KnowMeEntry(*row)
