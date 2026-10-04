"""Opt-in coding continuity in the existing application SQLite database.

Observed receipts are recovery evidence, never permission to replay an operation.
Arguments, outputs, credentials and model reasoning are not stored in receipts.
"""

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import closing, contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path

from ai_agent.contracts import ToolDefinition, ToolResult
from ai_agent.processes import ProcessSupervisor
from ai_agent.tools.base import BaseTool, ToolContext, ToolRegistry

ACTIVE_SESSION: ContextVar["CodingSession | None"] = ContextVar("coding_session", default=None)


class CodingSession:
    """Persist explicit objectives/decisions and bounded observed-effect metadata."""

    def __init__(self, database: Path, session_id: str, workspace: Path):
        self.database = database
        self.session_id = session_id
        self.workspace = workspace.resolve()
        self.supervisor = ProcessSupervisor(self.workspace)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.database, timeout=10)) as connection, connection:
            connection.row_factory = sqlite3.Row
            yield connection

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS coding_sessions (
                    session_id TEXT PRIMARY KEY,
                    workspace TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    decisions_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    privacy_class TEXT NOT NULL,
                    cost_policy TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS coding_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    status TEXT NOT NULL,
                    output_sha256 TEXT,
                    created_at_utc TEXT NOT NULL,
                    completed_at_utc TEXT
                );
                CREATE INDEX IF NOT EXISTS coding_receipts_session
                    ON coding_receipts(session_id, created_at_utc);
                CREATE TABLE IF NOT EXISTS coding_processes (
                    session_id TEXT NOT NULL,
                    process_handle TEXT NOT NULL,
                    pid INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    returncode INTEGER,
                    observed_at_utc TEXT NOT NULL,
                    PRIMARY KEY(session_id, process_handle)
                );
            """)

    @classmethod
    def open(
        cls,
        database: Path,
        session_id: str,
        workspace: Path,
        objective: str,
        decisions: list[str],
        *,
        reconciled: bool = False,
        privacy_class: str = "local_only",
        cost_policy: str = "local_only",
    ) -> "CodingSession":
        is_new = session_id == "new"
        session = cls(database, uuid.uuid4().hex if is_new else session_id, workspace)
        session.initialize()
        with session.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM coding_sessions WHERE session_id=?", (session.session_id,)
            ).fetchone()
            if row is None:
                if not is_new:
                    raise ValueError("Coding session does not exist; select 'new' to create one")
                connection.execute(
                    "INSERT INTO coding_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        session.session_id,
                        str(session.workspace),
                        objective,
                        json.dumps(decisions),
                        "running",
                        _now(),
                        privacy_class,
                        cost_policy,
                    ),
                )
            else:
                if row["workspace"] != str(session.workspace):
                    raise ValueError("Coding session belongs to a different workspace")
                if (row["privacy_class"], row["cost_policy"]) != (privacy_class, cost_policy):
                    raise ValueError("Coding session privacy/cost boundaries must remain unchanged")
                uncertain = connection.execute(
                    "SELECT 1 FROM coding_receipts WHERE session_id=? "
                    "AND status IN ('running', 'interrupted') LIMIT 1",
                    (session.session_id,),
                ).fetchone()
                if (row["status"] in {"running", "interrupted"} or uncertain) and not reconciled:
                    raise ValueError(
                        "Session needs effect reconciliation. Inspect files/processes first; "
                        "--coding-session-reconciled acknowledges that inspection. "
                        "Ensure no other CLI owns this session. No actions were replayed."
                    )
                combined = list(dict.fromkeys([*json.loads(row["decisions_json"]), *decisions]))
                connection.execute(
                    "UPDATE coding_sessions SET decisions_json=?, status='running', "
                    "updated_at_utc=? "
                    "WHERE session_id=?",
                    (json.dumps(combined), _now(), session.session_id),
                )
                connection.execute(
                    "UPDATE coding_processes SET status='unknown_after_restart' "
                    "WHERE session_id=? AND status='running'",
                    (session.session_id,),
                )
        return session

    def handoff(self) -> str:
        with self.connection() as connection:
            session = connection.execute(
                "SELECT * FROM coding_sessions WHERE session_id=?", (self.session_id,)
            ).fetchone()
            receipts = connection.execute(
                "SELECT operation,status,output_sha256 FROM coding_receipts WHERE session_id=? "
                "ORDER BY created_at_utc DESC, rowid DESC LIMIT 30",
                (self.session_id,),
            ).fetchall()
        assert session is not None
        return (
            "## Coding-session handoff\nApprovals from earlier invocations have expired. "
            "Inspect uncertain effects; never replay them blindly. Saved output hashes are "
            "observations, not current file state or validation proof.\n"
            f"Original objective: {session['objective']}\n"
            f"Explicit decisions: {session['decisions_json']}\n"
            "Recent receipts: " + json.dumps([dict(row) for row in receipts])
        )

    def status(self, value: str) -> None:
        with self.connection() as connection:
            connection.execute(
                "UPDATE coding_sessions SET status=?, updated_at_utc=? WHERE session_id=?",
                (value, _now(), self.session_id),
            )

    def begin(self, operation: str) -> str:
        receipt_id = uuid.uuid4().hex
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO coding_receipts VALUES (?, ?, ?, 'running', NULL, ?, NULL)",
                (receipt_id, self.session_id, operation, _now()),
            )
        return receipt_id

    def finish(self, receipt_id: str, *, status: str, output: str = "") -> None:
        digest = hashlib.sha256(output.encode()).hexdigest()
        with self.connection() as connection:
            connection.execute(
                "UPDATE coding_receipts SET status=?,output_sha256=?,completed_at_utc=? "
                "WHERE session_id=? AND receipt_id=? AND status='running'",
                (status, digest, _now(), self.session_id, receipt_id),
            )

    def observe_registry(
        self, registry: ToolRegistry, *, operation_prefix: str = ""
    ) -> ToolRegistry:
        return ToolRegistry(
            tuple(
                ObservedTool(tool, self, operation_prefix)
                for definition in registry.list_definitions()
                if (tool := registry.get(definition.name)) is not None
            )
        )

    def observe_process(self, metadata: dict) -> None:
        if not isinstance(metadata.get("process_handle"), str):
            return
        with self.connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO coding_processes VALUES (?, ?, ?, ?, ?, ?)",
                (
                    self.session_id,
                    metadata["process_handle"],
                    metadata["pid"],
                    metadata["status"],
                    metadata["returncode"],
                    _now(),
                ),
            )


class ObservedTool(BaseTool):
    """Persist start/finish around a tool; original category and boundary remain intact."""

    def __init__(self, tool: BaseTool, session: CodingSession, operation_prefix: str = ""):
        self.tool = tool
        self.session = session
        self.operation_prefix = operation_prefix

    @property
    def definition(self) -> ToolDefinition:
        return self.tool.definition

    def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        operation = self.definition.name
        if self.operation_prefix:
            digest = hashlib.sha256(json.dumps(arguments, sort_keys=True).encode()).hexdigest()
            operation = self.operation_prefix + operation + ":" + digest
        receipt = self.session.begin(operation)
        try:
            result = self.tool.execute(arguments, context)
        except Exception:
            self.session.finish(receipt, status="failed")
            raise
        self.session.finish(
            receipt, status="failed" if result.is_error else "completed", output=result.output
        )
        self.session.observe_process(result.metadata)
        return result


def _now() -> str:
    return datetime.now(UTC).isoformat()
