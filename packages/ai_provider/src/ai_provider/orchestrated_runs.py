from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

SCHEMA_VERSION = 1
DEFAULT_ORCHESTRATED_RUN_DB = Path("data") / "repo-assistant-runs.sqlite3"


@dataclass(frozen=True)
class OrchestratedRunRecord:
    """Durable metadata for one foreground orchestrated repo-assistant run."""

    run_id: str
    created_at_utc: str
    updated_at_utc: str
    repo_root: str
    mode: str
    prompt_preview: str
    budget_seconds: float
    approval_policy: str
    status: str
    execution_status: str | None
    primary_route_id: str | None
    primary_provider: str | None
    primary_model: str | None


@dataclass(frozen=True)
class OrchestratedStageRecord:
    """Durable metadata for one planned or completed stage in an orchestrated run."""

    run_id: str
    stage_order: int
    name: str
    route_policy: str
    status: str
    purpose: str
    started_at_utc: str | None = None
    completed_at_utc: str | None = None
    details: dict[str, object] | None = None


@dataclass(frozen=True)
class OrchestratedStagePlanItem:
    """Static stage plan item that can be persisted before stage execution exists."""

    name: str
    route_policy: str
    purpose: str


class SQLiteOrchestratedRunStore:
    """SQLite-backed repository for foreground orchestrated run and stage records."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        """Create the current schema if it does not already exist."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS orchestrated_runs (
                    run_id TEXT PRIMARY KEY,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    repo_root TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    prompt_preview TEXT NOT NULL,
                    budget_seconds REAL NOT NULL,
                    approval_policy TEXT NOT NULL,
                    status TEXT NOT NULL,
                    execution_status TEXT,
                    primary_route_id TEXT,
                    primary_provider TEXT,
                    primary_model TEXT,
                    schema_version INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS orchestrated_run_stages (
                    run_id TEXT NOT NULL,
                    stage_order INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    route_policy TEXT NOT NULL,
                    status TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    started_at_utc TEXT,
                    completed_at_utc TEXT,
                    details_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, name),
                    FOREIGN KEY (run_id) REFERENCES orchestrated_runs(run_id)
                        ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_orchestrated_run_stages_run_order
                ON orchestrated_run_stages(run_id, stage_order)
                """
            )

    def create_run(
        self,
        *,
        repo_root: Path,
        mode: str,
        prompt: str,
        budget_seconds: float,
        approval_policy: str,
        primary_route_id: str | None,
        primary_provider: str | None,
        primary_model: str | None,
        status: str = "planned",
        execution_status: str | None = None,
    ) -> OrchestratedRunRecord:
        """Insert and return one run record."""

        self.initialize()
        now = _utc_now()
        record = OrchestratedRunRecord(
            run_id=str(uuid.uuid4()),
            created_at_utc=now,
            updated_at_utc=now,
            repo_root=str(repo_root),
            mode=mode,
            prompt_preview=_prompt_preview(prompt),
            budget_seconds=budget_seconds,
            approval_policy=approval_policy,
            status=status,
            execution_status=execution_status,
            primary_route_id=primary_route_id,
            primary_provider=primary_provider,
            primary_model=primary_model,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO orchestrated_runs (
                    run_id,
                    created_at_utc,
                    updated_at_utc,
                    repo_root,
                    mode,
                    prompt_preview,
                    budget_seconds,
                    approval_policy,
                    status,
                    execution_status,
                    primary_route_id,
                    primary_provider,
                    primary_model,
                    schema_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.run_id,
                    record.created_at_utc,
                    record.updated_at_utc,
                    record.repo_root,
                    record.mode,
                    record.prompt_preview,
                    record.budget_seconds,
                    record.approval_policy,
                    record.status,
                    record.execution_status,
                    record.primary_route_id,
                    record.primary_provider,
                    record.primary_model,
                    SCHEMA_VERSION,
                ),
            )
        return record

    def replace_stage_plan(
        self,
        run_id: str,
        stages: Sequence[OrchestratedStagePlanItem],
    ) -> tuple[OrchestratedStageRecord, ...]:
        """Replace the planned stage rows for a run."""

        self.initialize()
        records = tuple(
            OrchestratedStageRecord(
                run_id=run_id,
                stage_order=index,
                name=stage.name,
                route_policy=stage.route_policy,
                status="planned",
                purpose=stage.purpose,
                details={},
            )
            for index, stage in enumerate(stages, start=1)
        )
        with self._connect() as connection:
            connection.execute("DELETE FROM orchestrated_run_stages WHERE run_id = ?", (run_id,))
            connection.executemany(
                """
                INSERT INTO orchestrated_run_stages (
                    run_id,
                    stage_order,
                    name,
                    route_policy,
                    status,
                    purpose,
                    started_at_utc,
                    completed_at_utc,
                    details_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        record.run_id,
                        record.stage_order,
                        record.name,
                        record.route_policy,
                        record.status,
                        record.purpose,
                        record.started_at_utc,
                        record.completed_at_utc,
                        json.dumps(record.details or {}, sort_keys=True),
                    )
                    for record in records
                ),
            )
        return records

    def get_run(self, run_id: str) -> OrchestratedRunRecord | None:
        """Return a run record by ID, or None when it does not exist."""

        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    run_id,
                    created_at_utc,
                    updated_at_utc,
                    repo_root,
                    mode,
                    prompt_preview,
                    budget_seconds,
                    approval_policy,
                    status,
                    execution_status,
                    primary_route_id,
                    primary_provider,
                    primary_model
                FROM orchestrated_runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return _run_record_from_row(row)

    def list_stages(self, run_id: str) -> tuple[OrchestratedStageRecord, ...]:
        """Return stage rows for a run in execution order."""

        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    run_id,
                    stage_order,
                    name,
                    route_policy,
                    status,
                    purpose,
                    started_at_utc,
                    completed_at_utc,
                    details_json
                FROM orchestrated_run_stages
                WHERE run_id = ?
                ORDER BY stage_order
                """,
                (run_id,),
            ).fetchall()
        return tuple(_stage_record_from_row(row) for row in rows)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _prompt_preview(prompt: str, *, max_chars: int = 500) -> str:
    normalized = " ".join(prompt.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3] + "..."


def _run_record_from_row(row: sqlite3.Row | tuple[object, ...]) -> OrchestratedRunRecord:
    return OrchestratedRunRecord(
        run_id=str(row[0]),
        created_at_utc=str(row[1]),
        updated_at_utc=str(row[2]),
        repo_root=str(row[3]),
        mode=str(row[4]),
        prompt_preview=str(row[5]),
        budget_seconds=float(cast(Any, row[6])),
        approval_policy=str(row[7]),
        status=str(row[8]),
        execution_status=str(row[9]) if row[9] is not None else None,
        primary_route_id=str(row[10]) if row[10] is not None else None,
        primary_provider=str(row[11]) if row[11] is not None else None,
        primary_model=str(row[12]) if row[12] is not None else None,
    )


def _stage_record_from_row(row: sqlite3.Row | tuple[object, ...]) -> OrchestratedStageRecord:
    return OrchestratedStageRecord(
        run_id=str(row[0]),
        stage_order=int(cast(Any, row[1])),
        name=str(row[2]),
        route_policy=str(row[3]),
        status=str(row[4]),
        purpose=str(row[5]),
        started_at_utc=str(row[6]) if row[6] is not None else None,
        completed_at_utc=str(row[7]) if row[7] is not None else None,
        details=json.loads(str(row[8])),
    )
