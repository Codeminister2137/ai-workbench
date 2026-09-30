from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ai_provider.contracts import AIMessage, MessageRole

SCHEMA_VERSION = 1
DEFAULT_CHAT_TRANSCRIPT_DB = Path("data") / "repo-assistant-chats.sqlite3"


@dataclass(frozen=True, slots=True)
class ChatSessionRecord:
    """Durable metadata for one local provider-neutral chat transcript."""

    session_id: str
    created_at_utc: str
    updated_at_utc: str
    repo_root: str
    title: str
    privacy_class: str
    status: str


@dataclass(frozen=True, slots=True)
class ChatMessageRecord:
    """One ordered provider-neutral message persisted in a local chat transcript."""

    message_id: str
    session_id: str
    message_order: int
    created_at_utc: str
    role: str
    content: str
    provider: str | None = None
    model: str | None = None
    metadata: dict[str, object] | None = None


class SQLiteChatTranscriptStore:
    """SQLite-backed repository for local chat sessions and ordered messages."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        """Create the current schema if it does not already exist."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    repo_root TEXT NOT NULL,
                    title TEXT NOT NULL,
                    privacy_class TEXT NOT NULL,
                    status TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    message_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    message_order INTEGER NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    provider TEXT,
                    model TEXT,
                    metadata_json TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
                        ON DELETE CASCADE,
                    UNIQUE (session_id, message_order)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session_order
                ON chat_messages(session_id, message_order)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated_at
                ON chat_sessions(updated_at_utc)
                """
            )

    def create_session(
        self,
        *,
        repo_root: Path,
        title: str,
        privacy_class: str,
        status: str = "active",
    ) -> ChatSessionRecord:
        """Insert and return one chat session."""

        self.initialize()
        now = _utc_now()
        record = ChatSessionRecord(
            session_id=str(uuid.uuid4()),
            created_at_utc=now,
            updated_at_utc=now,
            repo_root=str(repo_root),
            title=_title_preview(title),
            privacy_class=privacy_class,
            status=status,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_sessions (
                    session_id,
                    created_at_utc,
                    updated_at_utc,
                    repo_root,
                    title,
                    privacy_class,
                    status,
                    schema_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.session_id,
                    record.created_at_utc,
                    record.updated_at_utc,
                    record.repo_root,
                    record.title,
                    record.privacy_class,
                    record.status,
                    SCHEMA_VERSION,
                ),
            )
        return record

    def get_session(self, session_id: str) -> ChatSessionRecord | None:
        """Return one chat session by ID, if present."""

        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT session_id, created_at_utc, updated_at_utc, repo_root,
                       title, privacy_class, status
                FROM chat_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        return None if row is None else _session_from_row(row)

    def latest_session(self, *, repo_root: Path | None = None) -> ChatSessionRecord | None:
        """Return the most recently updated session, optionally scoped to a repo."""

        self.initialize()
        with self._connect() as connection:
            if repo_root is None:
                row = connection.execute(
                    """
                    SELECT session_id, created_at_utc, updated_at_utc, repo_root,
                           title, privacy_class, status
                    FROM chat_sessions
                    ORDER BY updated_at_utc DESC
                    LIMIT 1
                    """
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT session_id, created_at_utc, updated_at_utc, repo_root,
                           title, privacy_class, status
                    FROM chat_sessions
                    WHERE repo_root = ?
                    ORDER BY updated_at_utc DESC
                    LIMIT 1
                    """,
                    (str(repo_root),),
                ).fetchone()
        return None if row is None else _session_from_row(row)

    def list_sessions(self, *, limit: int = 20) -> tuple[ChatSessionRecord, ...]:
        """Return recent chat sessions newest-first."""

        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT session_id, created_at_utc, updated_at_utc, repo_root,
                       title, privacy_class, status
                FROM chat_sessions
                ORDER BY updated_at_utc DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return tuple(_session_from_row(row) for row in rows)

    def append_message(
        self,
        session_id: str,
        *,
        role: MessageRole | str,
        content: str,
        provider: str | None = None,
        model: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ChatMessageRecord:
        """Append and return one ordered message in a session."""

        self.initialize()
        role_value = role.value if isinstance(role, MessageRole) else role
        now = _utc_now()
        with self._connect() as connection:
            session_exists = connection.execute(
                "SELECT 1 FROM chat_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if session_exists is None:
                raise KeyError(f"chat session does not exist: {session_id}")
            next_order = int(
                connection.execute(
                    """
                    SELECT COALESCE(MAX(message_order), 0) + 1
                    FROM chat_messages
                    WHERE session_id = ?
                    """,
                    (session_id,),
                ).fetchone()[0]
            )
            record = ChatMessageRecord(
                message_id=str(uuid.uuid4()),
                session_id=session_id,
                message_order=next_order,
                created_at_utc=now,
                role=role_value,
                content=content,
                provider=provider,
                model=model,
                metadata=metadata or {},
            )
            connection.execute(
                """
                INSERT INTO chat_messages (
                    message_id,
                    session_id,
                    message_order,
                    created_at_utc,
                    role,
                    content,
                    provider,
                    model,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.message_id,
                    record.session_id,
                    record.message_order,
                    record.created_at_utc,
                    record.role,
                    record.content,
                    record.provider,
                    record.model,
                    json.dumps(record.metadata, sort_keys=True),
                ),
            )
            connection.execute(
                "UPDATE chat_sessions SET updated_at_utc = ? WHERE session_id = ?",
                (now, session_id),
            )
        return record

    def list_messages(self, session_id: str) -> tuple[ChatMessageRecord, ...]:
        """Return all messages for one session in provider order."""

        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT message_id, session_id, message_order, created_at_utc,
                       role, content, provider, model, metadata_json
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY message_order
                """,
                (session_id,),
            ).fetchall()
        return tuple(_message_from_row(row) for row in rows)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def messages_to_ai_messages(messages: tuple[ChatMessageRecord, ...]) -> tuple[AIMessage, ...]:
    """Convert durable chat messages to provider-neutral request messages."""

    return tuple(AIMessage(MessageRole(message.role), message.content) for message in messages)


def _session_from_row(row: sqlite3.Row) -> ChatSessionRecord:
    return ChatSessionRecord(
        session_id=str(row["session_id"]),
        created_at_utc=str(row["created_at_utc"]),
        updated_at_utc=str(row["updated_at_utc"]),
        repo_root=str(row["repo_root"]),
        title=str(row["title"]),
        privacy_class=str(row["privacy_class"]),
        status=str(row["status"]),
    )


def _message_from_row(row: sqlite3.Row) -> ChatMessageRecord:
    metadata = json.loads(str(row["metadata_json"]))
    return ChatMessageRecord(
        message_id=str(row["message_id"]),
        session_id=str(row["session_id"]),
        message_order=int(row["message_order"]),
        created_at_utc=str(row["created_at_utc"]),
        role=str(row["role"]),
        content=str(row["content"]),
        provider=row["provider"],
        model=row["model"],
        metadata=metadata if isinstance(metadata, dict) else {},
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _title_preview(text: str, *, limit: int = 120) -> str:
    normalized = " ".join(text.split())
    if not normalized:
        return "Untitled chat"
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 15)].rstrip() + " ...[truncated]"
