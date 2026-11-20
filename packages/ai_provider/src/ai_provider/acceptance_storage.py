"""Definitions and additive storage for fixed local acceptance jobs."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ai_orchestrator import AccessMethod, load_model_catalog
from ai_orchestrator.scheduling import ScheduledTaskStatus

from ai_provider import native_admission
from ai_provider.native_admission import native_tool_incompatibility
from ai_provider.orchestrated_runs import (
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
        for name, expected in (
            ("schema_version", 1),
            ("harness_revision", 1),
            ("native_contract_version", native_admission.NATIVE_CONTRACT_VERSION),
        ):
            if type(getattr(self, name)) is not int or getattr(self, name) != expected:
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
        """Validate only the selected record; unrelated stale history cannot block it."""
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT definition_json,definition_sha256,schema_version,status,result_json "
                "FROM scheduled_acceptance_tasks WHERE task_id=?",
                (task_id,),
            ).fetchone()
        if row is None:
            raise KeyError(task_id)
        payload, digest, version, status, result = row
        if version != 1 or hashlib.sha256(payload.encode()).hexdigest() != digest:
            raise ValueError("Unsupported or changed persisted acceptance definition")
        job = AcceptanceJob.from_json(payload)
        if job.task_id != task_id:
            raise ValueError("Persisted acceptance task identity changed")
        return AcceptanceRecord(
            job,
            ScheduledTaskStatus(status),
            json.loads(result) if result is not None else None,
        )

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
