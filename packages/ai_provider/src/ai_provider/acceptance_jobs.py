"""Explicit, local-only fixed acceptance jobs in additive application storage."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import math
import sqlite3
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ai_orchestrator import AccessMethod, load_model_catalog
from ai_orchestrator.scheduling import ScheduledTask, ScheduledTaskStatus, admit_task

from ai_provider import native_admission
from ai_provider.native_admission import native_tool_incompatibility
from ai_provider.orchestrated_runs import (
    DEFAULT_ORCHESTRATED_RUN_DB,
    SQLiteOrchestratedRunStore,
    _utc_now,
)

CLEANUP_SECONDS = 15.0


@dataclass(frozen=True, slots=True)
class AcceptanceJob:
    """Immutable v1 payload: no command, prompt, executable or environment fields."""

    schema_version: int
    task_id: str
    job_kind: str
    harness_revision: int
    repo_root: str
    route_id: str
    model: str
    runtime_version: str
    model_digest: str
    native_contract_version: int
    runtime_base_url: str
    required_seconds: float
    request_timeout_seconds: float
    context_tokens: int
    output_tokens: int
    max_iterations: int

    def __post_init__(self) -> None:
        for name in ("schema_version", "harness_revision", "native_contract_version"):
            if type(getattr(self, name)) is not int or getattr(self, name) != 1:
                raise ValueError(f"Unsupported {name}")
        for name in (
            "task_id",
            "repo_root",
            "route_id",
            "model",
            "runtime_version",
            "model_digest",
            "runtime_base_url",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or "\0" in value:
                raise ValueError(f"{name} must be a nonempty string without NUL")
        if self.job_kind != "native_coding_tools_v1":
            raise ValueError("Unsupported fixed acceptance job kind")
        root = Path(self.repo_root)
        if not root.is_absolute() or not root.is_dir():
            raise ValueError("repo_root must be an existing absolute directory")
        endpoint(self.runtime_base_url)
        for name in ("required_seconds", "request_timeout_seconds"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        for name in ("context_tokens", "output_tokens", "max_iterations"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.max_iterations > 4:
            raise ValueError("Harness v1 allows at most four iterations")
        if self.output_tokens + 256 >= self.context_tokens:
            raise ValueError("Output and framing leave no input capacity")
        reason = native_tool_incompatibility(
            self.model,
            model_digest=self.model_digest,
            runtime_version=self.runtime_version,
            contract_version=self.native_contract_version,
        )
        if reason:
            raise ValueError(reason)

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, allow_nan=False)

    @classmethod
    def from_json(cls, payload: str) -> AcceptanceJob:
        value = json.loads(payload)
        if not isinstance(value, dict) or set(value) != {item.name for item in fields(cls)}:
            raise ValueError("Acceptance definition requires exactly the v1 fields")
        return cls(**value)


def endpoint(url: str) -> tuple[str, int]:
    """Allow numeric loopback only, without credentials, paths or URL indirection."""
    parsed = urlsplit(url)
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Runtime endpoint requires a numeric loopback address/port") from exc
    if (
        parsed.scheme != "http"
        or not address.is_loopback
        or port is None
        or port == 0
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Runtime endpoint must be credential-free loopback HTTP with explicit port"
        )
    return str(address), port


def validate_route(job: AcceptanceJob) -> None:
    """Check the existing catalog offline; runtime identity is checked at execution."""
    if job.native_contract_version != native_admission.NATIVE_CONTRACT_VERSION:
        raise ValueError("Planned native contract revision is stale")
    reason = native_tool_incompatibility(
        job.model,
        model_digest=job.model_digest,
        runtime_version=job.runtime_version,
        contract_version=job.native_contract_version,
    )
    if reason:
        raise ValueError(reason)
    catalog = load_model_catalog(
        Path(job.repo_root) / "packages/ai_orchestrator/examples/model_catalog.toml"
    )
    entries = [item for item in catalog if item.backend.route_id == job.route_id]
    if len(entries) != 1:
        raise ValueError("Acceptance requires one explicit catalog route")
    backend = entries[0].backend
    if (
        backend.provider != "ollama"
        or backend.model != job.model
        or backend.access_method is not AccessMethod.LOCAL_RUNTIME
        or backend.location.value != "local"
        or not backend.capabilities.tools
    ):
        raise ValueError("Acceptance requires the explicit local Ollama tool route/model")
    capacity = backend.context_limits.context_window_tokens
    if capacity is None or job.context_tokens > capacity:
        raise ValueError("Acceptance context must fit a known catalog model window")


@dataclass(frozen=True, slots=True)
class AcceptanceRecord:
    job: AcceptanceJob
    status: ScheduledTaskStatus
    result: dict[str, Any] | None


class AcceptanceJobStore(SQLiteOrchestratedRunStore):
    """Add v1 definitions and append-only receipts without changing research rows."""

    def initialize(self) -> None:
        super().initialize()
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS scheduled_acceptance_tasks (
                    task_id TEXT PRIMARY KEY, definition_json TEXT NOT NULL,
                    definition_sha256 TEXT NOT NULL, schema_version INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK(status IN
                        ('planned','running','completed','failed','deferred')),
                    created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
                    result_json TEXT
                );
                CREATE TABLE IF NOT EXISTS acceptance_receipts (
                    receipt_id INTEGER PRIMARY KEY, task_id TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL, schema_version INTEGER NOT NULL,
                    receipt_json TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES scheduled_acceptance_tasks(task_id)
                );
            """)

    def plan(self, job: AcceptanceJob) -> None:
        validate_route(job)
        payload = job.to_json()
        self.initialize()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO scheduled_acceptance_tasks VALUES (?,?,?,?,?,?,?,NULL)",
                (
                    job.task_id,
                    payload,
                    hashlib.sha256(payload.encode()).hexdigest(),
                    1,
                    "planned",
                    _utc_now(),
                    _utc_now(),
                ),
            )

    def list_jobs(self) -> tuple[AcceptanceRecord, ...]:
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT definition_json,definition_sha256,schema_version,status,result_json "
                "FROM scheduled_acceptance_tasks ORDER BY rowid"
            ).fetchall()
        records = []
        for payload, digest, version, status, result in rows:
            if version != 1 or hashlib.sha256(payload.encode()).hexdigest() != digest:
                raise ValueError("Unsupported or changed persisted acceptance definition")
            records.append(
                AcceptanceRecord(
                    AcceptanceJob.from_json(payload),
                    ScheduledTaskStatus(status),
                    json.loads(result) if result is not None else None,
                )
            )
        return tuple(records)

    def get(self, task_id: str) -> AcceptanceRecord:
        for record in self.list_jobs():
            if record.job.task_id == task_id:
                return record
        raise KeyError(task_id)

    def transition(
        self,
        task_id: str,
        expected: ScheduledTaskStatus,
        status: ScheduledTaskStatus,
        result: dict[str, Any] | None = None,
    ) -> None:
        if (expected.value, status.value) not in {
            ("planned", "running"),
            ("planned", "deferred"),
            ("running", "completed"),
            ("running", "failed"),
        }:
            raise ValueError("Unsupported acceptance lifecycle transition")
        self.initialize()
        with self._connect() as connection:
            changed = connection.execute(
                "UPDATE scheduled_acceptance_tasks SET status=?,updated_at_utc=?,result_json=? "
                "WHERE task_id=? AND status=?",
                (
                    status.value,
                    _utc_now(),
                    json.dumps(result, allow_nan=False) if result else None,
                    task_id,
                    expected.value,
                ),
            ).rowcount
            if changed != 1:
                raise ValueError("Acceptance job is no longer in the expected state")

    def receipt(self, task_id: str, value: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO acceptance_receipts "
                "(task_id,created_at_utc,schema_version,receipt_json) VALUES (?,?,1,?)",
                (task_id, _utc_now(), json.dumps(value, allow_nan=False)),
            )


def artifact_directory(job: AcceptanceJob, database: Path) -> Path:
    identity = f"{database.resolve()}\0{job.task_id}".encode()
    return Path(job.repo_root) / "artifacts/acceptance-jobs" / hashlib.sha256(identity).hexdigest()


def execute_sequence(
    store: AcceptanceJobStore,
    task_ids: Sequence[str],
    *,
    explicitly_started: bool,
    local_compute_available: bool,
    available_seconds: float,
    clock: Callable[[], float] = time.monotonic,
    runner: Callable[..., dict[str, Any]] | None = None,
) -> tuple[str, ...]:
    """Claim each selected job once; stop on refusal, failure or uncertain cleanup."""
    if (
        type(available_seconds) not in (int, float)
        or not math.isfinite(available_seconds)
        or available_seconds <= 0
    ):
        raise ValueError("Available window must be positive and finite")
    if not task_ids or len(set(task_ids)) != len(task_ids):
        raise ValueError("Select a nonempty unique ordered sequence")
    if runner is None:
        from ai_provider.acceptance_runtime import run_acceptance_job

        runner = run_acceptance_job
    deadline = clock() + available_seconds
    records = [store.get(task_id) for task_id in task_ids]
    completed = []
    for record in records:
        job = record.job
        validate_route(job)
        admission = admit_task(
            ScheduledTask(job.task_id, job.required_seconds, record.status),
            explicitly_started=explicitly_started,
            window_deadline=deadline,
            now=clock(),
            constraints_satisfied=local_compute_available
            and job.required_seconds > CLEANUP_SECONDS,
        )
        if not admission.admitted:
            raise ValueError(admission.reason)
        store.transition(job.task_id, ScheduledTaskStatus.PLANNED, ScheduledTaskStatus.RUNNING)
        try:
            result = runner(job, store, admission.deadline, clock=clock)
        except BaseException as exc:
            store.transition(
                job.task_id,
                ScheduledTaskStatus.RUNNING,
                ScheduledTaskStatus.FAILED,
                {
                    "passed": False,
                    "reason": type(exc).__name__,
                    "next_action": "Reconcile ownership/effect receipts before re-planning",
                },
            )
            raise
        succeeded = (
            result.get("passed") is True
            and result.get("cleanup_verified") is True
            and clock() <= min(deadline, admission.deadline or deadline)
        )
        store.transition(
            job.task_id,
            ScheduledTaskStatus.RUNNING,
            ScheduledTaskStatus.COMPLETED if succeeded else ScheduledTaskStatus.FAILED,
            result,
        )
        if not succeeded:
            raise ValueError("Acceptance failed; sequence stopped; receipts preserved")
        completed.append(job.task_id)
    return tuple(completed)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--database", type=Path, default=DEFAULT_ORCHESTRATED_RUN_DB)
    commands = parser.add_subparsers(dest="action", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--definition", type=Path, required=True)
    commands.add_parser("list")
    run = commands.add_parser("run")
    run.add_argument("task_ids", nargs="+")
    run.add_argument("--start", action="store_true", required=True)
    run.add_argument("--local-compute-available", action="store_true", required=True)
    run.add_argument("--available-minutes", type=float, required=True)
    for name in ("defer", "fail-interrupted"):
        action = commands.add_parser(name)
        action.add_argument("task_id")
        action.add_argument("--reason", required=True)
        if name == "fail-interrupted":
            action.add_argument("--reconciled", action="store_true", required=True)
    args = parser.parse_args(argv)
    store = AcceptanceJobStore(args.database.resolve())
    try:
        if args.action == "plan":
            with args.definition.open(encoding="utf-8") as source:
                payload = source.read(65537)
            if len(payload) > 65536:
                raise ValueError("Acceptance definition exceeds 64 KiB character limit")
            store.plan(AcceptanceJob.from_json(payload))
        elif args.action == "list":
            for record in store.list_jobs():
                print(
                    json.dumps(
                        {
                            "definition": asdict(record.job),
                            "status": record.status.value,
                            "result": record.result,
                        }
                    )
                )
        elif args.action in ("defer", "fail-interrupted"):
            store.get(args.task_id)
            store.transition(
                args.task_id,
                ScheduledTaskStatus.PLANNED
                if args.action == "defer"
                else ScheduledTaskStatus.RUNNING,
                ScheduledTaskStatus.DEFERRED
                if args.action == "defer"
                else ScheduledTaskStatus.FAILED,
                {
                    "passed": False,
                    "reason": args.reason,
                    "next_action": "Plan a new job after review",
                },
            )
        else:
            print(
                execute_sequence(
                    store,
                    args.task_ids,
                    explicitly_started=args.start,
                    local_compute_available=args.local_compute_available,
                    available_seconds=args.available_minutes * 60,
                )
            )
    except (OSError, ValueError, KeyError, sqlite3.IntegrityError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
