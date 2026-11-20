"""Explicit, local-only fixed acceptance job sequencing and CLI."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ai_orchestrator.scheduling import ScheduledTask, ScheduledTaskStatus, admit_task

from ai_provider.acceptance_storage import (
    CLEANUP_SECONDS as CLEANUP_SECONDS,
)
from ai_provider.acceptance_storage import (
    AcceptanceJob as AcceptanceJob,
)
from ai_provider.acceptance_storage import (
    AcceptanceJobStore as AcceptanceJobStore,
)
from ai_provider.acceptance_storage import (
    AcceptanceRecord as AcceptanceRecord,
)
from ai_provider.acceptance_storage import (
    artifact_directory as artifact_directory,
)
from ai_provider.acceptance_storage import (
    endpoint as endpoint,
)
from ai_provider.acceptance_storage import (
    validate_route as validate_route,
)
from ai_provider.orchestrated_runs import DEFAULT_ORCHESTRATED_RUN_DB


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
