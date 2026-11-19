"""Local-first personal knowledge bank (SQLite, no network)."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

CATEGORIES = ("training", "diet", "preference", "health", "note", "skills", "career")
SOURCES = ("interview", "xiaomi", "note", "demo", "import")


@dataclass(frozen=True, slots=True)
class KnowMeEntry:
    """One banked fact about the owner."""

    id: int
    category: str
    text: str
    source: str
    created_at: float
    source_file: str | None = None
    origin_text: str | None = None


_COLUMNS = "id, category, text, source, created_at, source_file, origin_text"


@contextmanager
def _connected(path: Path) -> Iterator[sqlite3.Connection]:
    """Connect with commit-on-exit AND close-on-exit.

    Bare ``with sqlite3.connect(...)`` commits but never closes, leaking
    a connection per call (ResourceWarnings, Windows locking flakes).
    """
    with closing(sqlite3.connect(path)) as connection:
        with connection:
            yield connection


class KnowMeStore:
    """Tiny SQLite store; v2 adds optional provenance columns (v1 auto-upgrades)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _connected(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    text TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    source_file TEXT,
                    origin_text TEXT
                )
                """
            )
            present = {row[1] for row in connection.execute("PRAGMA table_info(entries)")}
            if "source_file" not in present:
                connection.execute("ALTER TABLE entries ADD COLUMN source_file TEXT")
            if "origin_text" not in present:
                connection.execute("ALTER TABLE entries ADD COLUMN origin_text TEXT")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_entries_category ON entries(category)"
            )

    def add(
        self,
        category: str,
        text: str,
        source: str,
        *,
        source_file: str | None = None,
        origin_text: str | None = None,
    ) -> KnowMeEntry:
        """Store one entry; validates category/source, rejects blanks."""
        if category not in CATEGORIES:
            raise ValueError(f"Unknown category: {category!r}")
        if source not in SOURCES:
            raise ValueError(f"Unknown source: {source!r}")
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Entry text must not be blank")
        if source_file is not None:
            if not isinstance(source_file, str) or not source_file.strip():
                raise ValueError("source_file must be a non-blank string")
            source_file = source_file.strip()
        if origin_text is not None:
            if not isinstance(origin_text, str):
                raise ValueError("origin_text must be a string")
            origin_text = origin_text.strip() or None
        created = time.time()
        with _connected(self.path) as connection:
            cursor = connection.execute(
                "INSERT INTO entries (category, text, source, created_at,"
                " source_file, origin_text) VALUES (?, ?, ?, ?, ?, ?)",
                (category, cleaned, source, created, source_file, origin_text),
            )
            entry_id = cursor.lastrowid
        assert entry_id is not None
        return KnowMeEntry(
            id=entry_id,
            category=category,
            text=cleaned,
            source=source,
            created_at=created,
            source_file=source_file,
            origin_text=origin_text,
        )

    def find(self, category: str | None = None, *, limit: int = 50) -> list[KnowMeEntry]:
        """Newest-first entries, optionally filtered by category."""
        if category is not None and category not in CATEGORIES:
            raise ValueError(f"Unknown category: {category!r}")
        query = f"SELECT {_COLUMNS} FROM entries"
        params: tuple[object, ...] = ()
        if category is not None:
            query += " WHERE category = ?"
            params = (category,)
        query += " ORDER BY id DESC LIMIT ?"
        with _connected(self.path) as connection:
            rows = connection.execute(query, (*params, limit)).fetchall()
        return [KnowMeEntry(*row) for row in rows]

    def count(self) -> int:
        """Total entries banked."""
        with _connected(self.path) as connection:
            row = connection.execute("SELECT COUNT(*) FROM entries").fetchone()
        return int(row[0])

    def iter_all(self) -> Iterator[KnowMeEntry]:
        """Stream every entry, oldest first (exports, reviews)."""
        with _connected(self.path) as connection:
            rows = connection.execute(f"SELECT {_COLUMNS} FROM entries ORDER BY id ASC").fetchall()
        for row in rows:
            yield KnowMeEntry(*row)
