from __future__ import annotations

import sqlite3
from pathlib import Path


DEFAULT_DB_PATH = Path("data/council.sqlite3")


class ConversationStore:
    def __init__(self, path: Path = DEFAULT_DB_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._migrate()

    def close(self) -> None:
        self.connection.close()

    def _migrate(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                member_name TEXT,
                model TEXT,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            );
            """
        )
        self.connection.commit()

    def get_or_create_conversation(self, name: str) -> int:
        self.connection.execute(
            "INSERT OR IGNORE INTO conversations(name) VALUES (?)",
            (name,),
        )
        self.connection.commit()
        row = self.connection.execute(
            "SELECT id FROM conversations WHERE name = ?",
            (name,),
        ).fetchone()
        return int(row["id"])

    def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        member_name: str | None = None,
        model: str | None = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO messages(conversation_id, role, member_name, model, content)
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, role, member_name, model, content),
        )
        self.connection.commit()

    def list_messages(self, conversation_id: int) -> list[dict[str, str]]:
        rows = self.connection.execute(
            """
            SELECT role, member_name, model, content
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id
            """,
            (conversation_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_conversations(self) -> list[dict[str, str]]:
        rows = self.connection.execute(
            """
            SELECT c.name, c.created_at, COUNT(m.id) AS message_count
            FROM conversations c
            LEFT JOIN messages m ON m.conversation_id = c.id
            GROUP BY c.id
            ORDER BY c.created_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]
