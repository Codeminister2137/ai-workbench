"""Explicit foreground scheduling of supervised, local, uncharged research jobs."""

from __future__ import annotations

import argparse
import hashlib
import math
import sqlite3
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ai_orchestrator.scheduling import ScheduledTask, ScheduledTaskStatus, admit_task

from ai_provider.orchestrated_runs import (
    DEFAULT_ORCHESTRATED_RUN_DB,
    SQLiteOrchestratedRunStore,
    _utc_now,
)
from ai_provider.research_runner import supervise_research


@dataclass(frozen=True)
class ResearchTask:
    task_id: str
    repo_root: Path
    prompt: str
    model: str
    required_seconds: float
    status: ScheduledTaskStatus = ScheduledTaskStatus.PLANNED
    exit_code: int | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        ScheduledTask(self.task_id, self.required_seconds, self.status)
        if not self.prompt.strip() or not self.model.strip():
            raise ValueError("Research prompt and local model must not be empty")


class ResearchTaskStore(SQLiteOrchestratedRunStore):
    """Additive task storage in the application's existing run database.

    Definitions are immutable. A conditional state transition claims a planned
    task once; an interrupted process leaves it running for explicit recovery.
    Full prompts are stored locally to make definitions executable, not logged.
    """

    def plan(self, task: ResearchTask) -> None:
        if task.status is not ScheduledTaskStatus.PLANNED or task.exit_code is not None:
            raise ValueError("New definitions must be planned and have no execution result")
        self.initialize()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO scheduled_research_tasks
                (task_id, created_at_utc, updated_at_utc, repo_root, prompt, model,
                 required_seconds, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task.task_id,
                    _utc_now(),
                    _utc_now(),
                    str(task.repo_root.resolve()),
                    task.prompt,
                    task.model,
                    task.required_seconds,
                    task.status.value,
                ),
            )

    def list_tasks(self) -> tuple[ResearchTask, ...]:
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT task_id, repo_root, prompt, model, required_seconds,
                status, exit_code, reason FROM scheduled_research_tasks ORDER BY rowid"""
            ).fetchall()
        return tuple(
            ResearchTask(
                row[0],
                Path(row[1]),
                row[2],
                row[3],
                row[4],
                ScheduledTaskStatus(row[5]),
                row[6],
                row[7],
            )
            for row in rows
        )

    def get_task(self, task_id: str) -> ResearchTask:
        for task in self.list_tasks():
            if task.task_id == task_id:
                return task
        raise KeyError(f"Scheduled task does not exist: {task_id}")

    def transition(
        self,
        task_id: str,
        *,
        expected: ScheduledTaskStatus,
        status: ScheduledTaskStatus,
        exit_code: int | None = None,
        reason: str | None = None,
    ) -> None:
        allowed = {
            (ScheduledTaskStatus.PLANNED, ScheduledTaskStatus.RUNNING),
            (ScheduledTaskStatus.PLANNED, ScheduledTaskStatus.DEFERRED),
            (ScheduledTaskStatus.RUNNING, ScheduledTaskStatus.COMPLETED),
            (ScheduledTaskStatus.RUNNING, ScheduledTaskStatus.FAILED),
        }
        if (expected, status) not in allowed:
            raise ValueError("Unsupported task lifecycle transition")
        self.initialize()
        with self._connect() as connection:
            changed = connection.execute(
                """UPDATE scheduled_research_tasks SET status = ?, updated_at_utc = ?,
                exit_code = ?, reason = ? WHERE task_id = ? AND status = ?""",
                (status.value, _utc_now(), exit_code, reason, task_id, expected.value),
            ).rowcount
            if changed != 1:
                raise ValueError(f"Task {task_id} is no longer {expected.value}; no task started")


def research_command(task: ResearchTask, database: Path) -> list[str]:
    """Construct fixed research flags; definitions cannot supply arbitrary commands."""
    # IDs are opaque labels, never path segments. Include the database identity
    # so independent queues do not write the same report for an identical ID.
    identity = f"{database.resolve()}\0{task.task_id}".encode()
    report = (
        Path("artifacts")
        / "scheduled-research"
        / hashlib.sha256(identity).hexdigest()
        / "report.md"
    )
    return [
        sys.executable,
        "-m",
        "ai_provider.repo_coding_assistant",
        "--repo-root",
        str(task.repo_root),
        "--mode",
        "implement",
        "--execute",
        "--orchestrated",
        "--away-minutes",
        str(task.required_seconds / 60),
        "--away-run-db",
        str(database.resolve()),
        "--tool-profile",
        "research",
        "--research-report",
        str(report),
        "--approval-policy",
        "trusted_local",
        "--provider",
        "ollama",
        "--privacy",
        "local_only",
        "--cost-policy",
        "local_only",
        "--model",
        task.model,
        "--",
        task.prompt,
    ]


def run_research_task(task: ResearchTask, database: Path, budget_seconds: float) -> int:
    return supervise_research(
        research_command(task, database),
        root=task.repo_root,
        database=database,
        budget_seconds=budget_seconds,
    )


@dataclass(frozen=True)
class SequenceResult:
    completed: tuple[str, ...]
    stopped_at: str | None
    reason: str


def execute_sequence(
    store: ResearchTaskStore,
    task_ids: Sequence[str],
    *,
    explicitly_started: bool,
    available_seconds: float,
    handoff_seconds: float = 600,
    constraints_satisfied: bool = False,
    clock: Callable[[], float] = time.monotonic,
    runner: Callable[[ResearchTask, Path, float], int] = run_research_task,
) -> SequenceResult:
    """Stop at the first refusal or failure; never reorder, retry or auto-resume.

    The caller must authorize compute availability before invoking an execution
    adapter. Planning and listing never call that adapter or probe providers.
    """
    for value in (available_seconds, handoff_seconds):
        if isinstance(value, bool) or not math.isfinite(value) or value < 0:
            raise ValueError("Window and handoff allocations must be finite and nonnegative")
    if available_seconds <= handoff_seconds:
        raise ValueError("Available window must exceed the handoff reserve")
    if not task_ids or len(set(task_ids)) != len(task_ids):
        raise ValueError("Select a nonempty sequence of unique task IDs")
    deadline = clock() + available_seconds - handoff_seconds
    tasks = [store.get_task(task_id) for task_id in task_ids]
    completed: list[str] = []
    for task in tasks:
        admission = admit_task(
            ScheduledTask(task.task_id, task.required_seconds, task.status),
            explicitly_started=explicitly_started,
            window_deadline=deadline,
            now=clock(),
            constraints_satisfied=constraints_satisfied and task.repo_root.is_dir(),
        )
        if not admission.admitted:
            return SequenceResult(tuple(completed), task.task_id, admission.reason)
        store.transition(
            task.task_id, expected=ScheduledTaskStatus.PLANNED, status=ScheduledTaskStatus.RUNNING
        )
        try:
            assert admission.deadline is not None
            remaining = admission.deadline - clock()
            code = runner(task, store.path.resolve(), remaining) if remaining > 0 else 124
        except BaseException:
            store.transition(
                task.task_id,
                expected=ScheduledTaskStatus.RUNNING,
                status=ScheduledTaskStatus.FAILED,
                reason="Supervisor interrupted",
            )
            raise
        succeeded = code == 0 and clock() <= min(deadline, admission.deadline)
        store.transition(
            task.task_id,
            expected=ScheduledTaskStatus.RUNNING,
            status=ScheduledTaskStatus.COMPLETED if succeeded else ScheduledTaskStatus.FAILED,
            exit_code=code,
            reason=None if succeeded else "Worker failed or exceeded window",
        )
        if not succeeded:
            return SequenceResult(tuple(completed), task.task_id, "Worker failed; sequence stopped")
        completed.append(task.task_id)
    return SequenceResult(tuple(completed), None, "Selected sequence completed")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--database", type=Path, default=DEFAULT_ORCHESTRATED_RUN_DB)
    sub = parser.add_subparsers(dest="action", required=True)
    plan = sub.add_parser("plan", help="Persist a definition without starting models")
    plan.add_argument("task_id")
    plan.add_argument("--prompt", required=True)
    plan.add_argument("--repo-root", type=Path, default=Path.cwd())
    plan.add_argument("--model", required=True)
    plan.add_argument("--required-minutes", type=float, required=True)
    sub.add_parser("list", help="List definitions without contacting providers")
    run = sub.add_parser("run", help="Start an explicitly selected sequence")
    run.add_argument("task_ids", nargs="+")
    run.add_argument("--start", action="store_true", required=True)
    run.add_argument("--local-compute-available", action="store_true", required=True)
    run.add_argument("--available-minutes", type=float, required=True)
    run.add_argument("--handoff-minutes", type=float, default=10)
    defer = sub.add_parser("defer", help="Explicitly defer a planned definition")
    defer.add_argument("task_id")
    defer.add_argument("--reason", required=True)
    recover = sub.add_parser("fail-interrupted", help="Mark a stopped running worker failed")
    recover.add_argument("task_id")
    recover.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    store = ResearchTaskStore(args.database.resolve())
    try:
        if args.action == "plan":
            store.plan(
                ResearchTask(
                    args.task_id,
                    args.repo_root,
                    args.prompt,
                    args.model,
                    args.required_minutes * 60,
                )
            )
            print(f"{args.task_id}: planned")
        elif args.action == "list":
            for task in store.list_tasks():
                print(
                    f"{task.task_id}: {task.status.value}, {task.required_seconds / 60:g} minutes"
                )
        elif args.action in ("defer", "fail-interrupted"):
            store.transition(
                args.task_id,
                expected=ScheduledTaskStatus.PLANNED
                if args.action == "defer"
                else ScheduledTaskStatus.RUNNING,
                status=ScheduledTaskStatus.DEFERRED
                if args.action == "defer"
                else ScheduledTaskStatus.FAILED,
                reason=args.reason,
            )
        else:
            result = execute_sequence(
                store,
                args.task_ids,
                explicitly_started=args.start,
                constraints_satisfied=args.local_compute_available,
                available_seconds=args.available_minutes * 60,
                handoff_seconds=args.handoff_minutes * 60,
            )
            print(result)
            return 0 if result.stopped_at is None else 1
    except (ValueError, KeyError, sqlite3.IntegrityError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
