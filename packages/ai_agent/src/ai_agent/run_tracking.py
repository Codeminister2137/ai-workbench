"""Foreground run planning, stage receipts and handoff through the existing store."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from ai_orchestrator import OrchestrationResult
from ai_orchestrator.review import research_review_reserve_seconds
from ai_provider.orchestrated_runs import (
    OrchestratedRunRecord,
    OrchestratedStagePlanItem,
    OrchestratedStageRecord,
    SQLiteOrchestratedRunStore,
)
from ai_provider.repair_state import changed_paths, workspace_fingerprints

from ai_agent.validation import (
    ValidationCommandResult,
    default_validation_python,
    run_validation_commands,
    validation_commands_from_args,
    validation_results_json,
    validation_status,
)

ORCHESTRATED_STAGE_PLAN: tuple[tuple[str, str, str], ...] = (
    (
        "prompt_review",
        "deterministic/local",
        "review the user request and refine or block before provider execution",
    ),
    (
        "planning",
        "primary",
        "ask the primary route for a bounded implementation plan",
    ),
    (
        "auxiliary_panel",
        "derived_local_cheap",
        "run local or cheaper reviewer/test/risk support passes",
    ),
    (
        "implementation",
        "primary",
        "run the selected implementation route with approved local tools",
    ),
    (
        "validation",
        "deterministic/local",
        "run allowed checks and record skipped or failed validation",
    ),
    (
        "scrutiny",
        "derived_local_cheap",
        "critique the final response and claimed validation",
    ),
    (
        "repair",
        "policy_bounded",
        "attempt one targeted repair only when time and findings justify it",
    ),
    (
        "final_handoff",
        "deterministic/local",
        "report changed files, validation, blockers, risks, and next action",
    ),
)


def _check_budget(seconds: float) -> None:
    """Refuse invalid programmatic/persisted budgets before stages or timers start."""
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise ValueError("Run budget must be a finite positive number")
    try:
        valid = seconds > 0 and math.isfinite(seconds)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("Run budget must be a finite positive number")


def print_orchestrated_stage_plan(
    *,
    args: argparse.Namespace,
    orchestration: OrchestrationResult,
    run_record: OrchestratedRunRecord | None = None,
    stage_records: Sequence[OrchestratedStageRecord] = (),
) -> None:
    """Print the foreground unattended workflow plan without running stages."""

    print("\n=== Orchestrated away-work plan ===")
    print("away_orchestrated: enabled")
    if run_record is not None:
        print(f"away_run_db: {args.away_run_db}")
        print(f"away_run_id: {run_record.run_id}")
        print(f"away_run_status: {run_record.status}")
        print(f"away_run_stage_records: {len(stage_records)}")
    print(f"away_plan_mode: {args.mode}")
    budget_seconds = run_record.budget_seconds if run_record is not None else args.away_minutes * 60
    print(f"away_plan_budget_minutes: {budget_seconds / 60:g}")
    print(f"away_plan_budget_seconds: {budget_seconds:g}")
    if args.mode == "plan":
        print("away_plan_execution: not_started")
        print("away_plan_skip_reason: plan mode never contacts a provider")
    else:
        print("away_plan_execution: foreground_run")
    if orchestration.execution_plan is not None:
        target = orchestration.execution_plan.target
        print(f"away_plan_primary_route_id: {target.route_id}")
        print(f"away_plan_primary_provider: {target.provider}")
        print(f"away_plan_primary_model: {target.model}")
        print(f"away_plan_primary_access_method: {target.access_method.value}")
        print(f"away_plan_primary_cost_policy_tier: {target.cost_policy_tier.value}")
    else:
        print("away_plan_primary_route_id: unavailable")
    print("away_plan_auxiliary_route_policy: derived_local_cheap")
    print("away_plan_external_writes: disabled")
    print(f"away_plan_approval_policy: {args.approval_policy}")
    validation_commands = validation_commands_from_args(args)
    print(
        "away_plan_validation_commands_json: "
        + json.dumps(list(validation_commands), sort_keys=True)
    )
    selected_python = default_validation_python(args)
    if selected_python is not None:
        print(f"away_plan_validation_python: {selected_python}")
    print(
        "away_plan_max_repair_cycles: "
        + ("unbounded" if args.max_repair_cycles == -1 else str(args.max_repair_cycles))
    )
    for name, route, purpose in ORCHESTRATED_STAGE_PLAN:
        print(f"away_stage: {name} route={route} status=planned purpose={purpose}")


def persist_orchestrated_run_plan(
    *,
    args: argparse.Namespace,
    repo_root: Path,
    orchestration: OrchestrationResult,
    prompt: str,
) -> tuple[OrchestratedRunRecord, tuple[OrchestratedStageRecord, ...]]:
    """Persist the durable run and planned stage rows for an orchestrated CLI run."""

    _check_budget(args.away_minutes)
    budget_seconds = args.away_minutes * 60
    deadline = getattr(args, "_execution_deadline", None)
    if args.execute and deadline is not None:
        budget_seconds = min(budget_seconds, max(0.0, deadline - time.perf_counter()))
    _check_budget(budget_seconds)
    store = SQLiteOrchestratedRunStore(resolve_orchestrated_run_db_path(args, repo_root))
    target = (
        orchestration.execution_plan.target if orchestration.execution_plan is not None else None
    )
    run_record = store.create_run(
        repo_root=repo_root,
        mode=args.mode,
        prompt=prompt,
        budget_seconds=budget_seconds,
        approval_policy=args.approval_policy,
        primary_route_id=target.route_id if target is not None else None,
        primary_provider=target.provider if target is not None else None,
        primary_model=target.model if target is not None else None,
    )
    stage_records = store.replace_stage_plan(
        run_record.run_id,
        tuple(
            OrchestratedStagePlanItem(
                name=name,
                route_policy=route,
                purpose=purpose,
            )
            for name, route, purpose in ORCHESTRATED_STAGE_PLAN
        ),
    )
    args.away_run_db = store.path
    return run_record, stage_records


def git_status_short(repo_root: Path) -> tuple[str, ...]:
    """Return concise Git working tree status for final handoff metadata."""

    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return (f"git status unavailable: {exc}",)
    if result.returncode != 0:
        detail = result.stderr.strip() or f"git status exited with code {result.returncode}"
        return (f"git status failed: {detail}",)
    return tuple(line for line in result.stdout.splitlines() if line.strip())


def remaining_orchestrated_budget_seconds(
    *,
    deadline: float | None,
    floor_seconds: float = 1.0,
) -> float | None:
    if deadline is None:
        return None
    return max(0.0, deadline - time.perf_counter() - floor_seconds)


class OrchestratedRunTracker:
    """Persist and print stage transitions for one foreground orchestrated run."""

    def __init__(
        self,
        *,
        store: SQLiteOrchestratedRunStore,
        run_record: OrchestratedRunRecord,
        progress_callback: Callable[[str], None] = print,
    ) -> None:
        _check_budget(run_record.budget_seconds)
        self._store = store
        self.run_record = run_record
        self._progress_callback = progress_callback
        # ``None`` means "no baseline captured yet" and is distinct from a
        # captured baseline of an empty workspace (``{}``).
        self.initial_workspace: dict[str, str] | None = None
        self.scrutiny_status = "not_run"
        self.scrutiny_details: dict[str, object] | None = None
        self.deadline = time.perf_counter() + run_record.budget_seconds

    @classmethod
    def create(
        cls,
        *,
        args: argparse.Namespace,
        repo_root: Path,
        orchestration: OrchestrationResult,
        prompt: str,
        progress_callback: Callable[[str], None] = print,
    ) -> tuple[OrchestratedRunTracker, tuple[OrchestratedStageRecord, ...]]:
        run_record, stage_records = persist_orchestrated_run_plan(
            args=args,
            repo_root=repo_root,
            orchestration=orchestration,
            prompt=prompt,
        )
        store = SQLiteOrchestratedRunStore(resolve_orchestrated_run_db_path(args, repo_root))
        tracker = cls(store=store, run_record=run_record, progress_callback=progress_callback)
        # Establish the workspace baseline here, before any stage runs, so the
        # handoff can report what this run changed even when ``begin_run`` is
        # skipped (non-implement modes never start the run).
        tracker.initial_workspace = workspace_fingerprints(repo_root)
        deadline = getattr(args, "_execution_deadline", None)
        if deadline is not None:
            tracker.deadline = min(tracker.deadline, deadline)
        return tracker, stage_records

    def begin_run(self) -> None:
        """Mark the run as executing, capturing a baseline if none exists yet.

        ``create`` already records the pre-work baseline; this is a fallback for
        trackers built directly, and the earlier snapshot is preferred because it
        attributes every later change to the run.
        """
        if self.initial_workspace is None:
            self.initial_workspace = workspace_fingerprints(Path(self.run_record.repo_root))
        self.run_record = self._store.update_run_status(
            self.run_record.run_id,
            status="running",
            execution_status="running",
        )

    def finish_run(self, *, execution_status: str) -> None:
        self.run_record = self._store.update_run_status(
            self.run_record.run_id,
            status="completed" if execution_status != "failed" else "failed",
            execution_status=execution_status,
        )

    def start_stage(
        self,
        stage_name: str,
        *,
        details: dict[str, object] | None = None,
    ) -> OrchestratedStageRecord:
        record = self._store.start_stage(
            self.run_record.run_id,
            stage_name,
            details=details,
        )
        self._progress_callback(
            f"away_stage_status: {stage_name} status=running started_at={record.started_at_utc}"
        )
        return record

    def complete_stage(
        self,
        stage_name: str,
        *,
        status: str = "completed",
        details: dict[str, object] | None = None,
    ) -> OrchestratedStageRecord:
        record = self._store.complete_stage(
            self.run_record.run_id,
            stage_name,
            status=status,
            details=details,
        )
        if stage_name == "scrutiny":
            # Persisted stage details merge across attempts; final delivery must
            # use only this attempt, never a stale pass or proposed revision.
            self.scrutiny_details = dict(details or {})
        self._progress_callback(
            f"away_stage_status: {stage_name} status={status} "
            f"completed_at={record.completed_at_utc}"
        )
        return record

    def record_validation_stage(
        self,
        *,
        args: argparse.Namespace,
        repo_root: Path,
        execution_status: str,
    ) -> OrchestratedStageRecord:
        """Persist deterministic validation-stage status for this foreground slice."""

        commands = validation_commands_from_args(args)
        self.start_stage(
            "validation",
            details={
                "execution_status_before_validation": execution_status,
                "commands": list(commands),
            },
        )
        if execution_status == "failed":
            return self.complete_stage(
                "validation",
                status="skipped",
                details={
                    "validation_status": "not_run",
                    "skip_reason": "primary execution failed before validation",
                },
            )
        research = getattr(args, "research_execution", None)
        if not commands and research is None:
            return self.complete_stage(
                "validation",
                status="skipped",
                details={
                    "validation_status": "not_run",
                    "skip_reason": "validation skipped by --skip-validation",
                },
            )
        remaining = remaining_orchestrated_budget_seconds(
            deadline=self.deadline,
            floor_seconds=research_review_reserve_seconds(
                self.run_record.budget_seconds,
                enabled=(
                    getattr(args, "research_review_policy", "legacy") == "quality_first"
                    and getattr(args, "tool_profile", "coding") == "research"
                ),
            )
            + 1.0,
        )
        if remaining is not None and remaining <= 0:
            return self.complete_stage(
                "validation",
                status="timeout",
                details={
                    "validation_status": "timeout",
                    "failure_reason": "review budget reserved before validation",
                    "results": [],
                },
            )
        results = run_validation_commands(
            commands,
            repo_root=repo_root,
            timeout_seconds=min(args.validation_timeout_seconds, remaining / max(1, len(commands)))
            if remaining is not None
            else args.validation_timeout_seconds,
            default_python=default_validation_python(args),
            progress_callback=self._progress_callback,
        )
        if research is not None:
            started = time.perf_counter()
            errors = research.validate()
            results = (
                ValidationCommandResult(
                    command="research report and current-run receipts",
                    returncode=1 if errors else 0,
                    status="failed" if errors else "passed",
                    elapsed_seconds=time.perf_counter() - started,
                    stdout_preview=""
                    if errors
                    else "Report structure and current-run receipts verified",
                    stderr_preview="\n".join(errors),
                ),
            ) + results
        result_status = validation_status(results)
        stage_status = "completed" if result_status == "passed" else result_status
        return self.complete_stage(
            "validation",
            status=stage_status,
            details={
                "validation_status": result_status,
                "results": validation_results_json(results),
            },
        )

    def record_final_handoff_stage(
        self,
        *,
        execution_status: str,
        validation_stage: OrchestratedStageRecord | None,
        repo_root: Path,
        assistant_response_text: str | None,
        final_answer_text: str | None = None,
        scrutiny_policy: str = "advisory",
    ) -> OrchestratedStageRecord:
        """Persist final handoff fields for the returning user.

        ``scrutiny_policy`` is recorded so a later reader can tell whether a
        non-pass verdict was merely advisory (ADR-066 default) or configured as
        a blocking requirement, rather than having to infer it from the outcome.

        ``changed_files`` is derived from the workspace fingerprint baseline
        captured by :meth:`create`, so it describes what *this run* changed
        rather than the whole working tree. Without that baseline the change set
        is not known, and an explicit note is recorded instead of a guessed list.
        """

        final_workspace = workspace_fingerprints(repo_root)
        changed_files = (
            tuple(changed_paths(self.initial_workspace, final_workspace))
            if self.initial_workspace is not None
            else ("workspace baseline not recorded; changed files unknown",)
        )
        validation_status = (
            str((validation_stage.details or {}).get("validation_status", validation_stage.status))
            if validation_stage is not None
            else "not_recorded"
        )
        self.start_stage(
            "final_handoff",
            details={
                "execution_status": execution_status,
                "validation_status": validation_status,
            },
        )
        handoff_status = "failed" if execution_status == "failed" else "completed"
        blockers = ""
        risks = ""
        next_action = "review the assistant response"
        if execution_status == "failed":
            blockers = "execution failed"
            next_action = "inspect failure details and decide whether to repair"
        elif validation_status in {"failed", "timeout"}:
            blockers = f"validation {validation_status}"
            next_action = "inspect validation failures and repair remaining issues"
        elif validation_status in {"not_run", "not_recorded", "skipped"}:
            risks = (
                "validation not recorded by deterministic wrapper"
                if validation_status == "not_recorded"
                else "validation not run by deterministic wrapper"
            )
            next_action = "run deterministic validation before treating the work as done"
        if execution_status == "completed_with_refinement_errors":
            blockers = "research refinement failed"
            next_action = "inspect research refinement failure details in the repair stage"
        if self.run_record.mode == "implement" and self.scrutiny_status != "pass":
            # A non-pass verdict is a risk, never a blocker, unless the owner
            # configured scrutiny as a requirement (ADR-066 keeps that option).
            label = "scrutiny" if scrutiny_policy == "required" else "advisory scrutiny"
            risks = (risks + "; " if risks else "") + f"{label} {self.scrutiny_status}"
            if not blockers:
                next_action = (
                    "inspect scrutiny details and review remaining claims before completion"
                )
        return self.complete_stage(
            "final_handoff",
            status=handoff_status,
            details={
                "execution_status": execution_status,
                "validation_status": validation_status,
                "scrutiny_status": self.scrutiny_status,
                "scrutiny_policy": scrutiny_policy,
                "changed_files": changed_files,
                "assistant_response_available": assistant_response_text is not None,
                "final_answer_available": final_answer_text is not None,
                "blockers": blockers,
                "risks": risks,
                "next_action": next_action,
            },
        )


def resolve_orchestrated_run_db_path(args: argparse.Namespace, repo_root: Path) -> Path:
    path = Path(args.away_run_db)
    if path.is_absolute():
        return path
    return repo_root / path


def execution_status_with_validation_stage(
    execution_status: str,
    validation_stage: OrchestratedStageRecord | None,
) -> str:
    """Surface deterministic validation failures in the final execution status."""

    if validation_stage is None:
        return execution_status
    result_status = validation_status_from_stage(validation_stage)
    if execution_status == "completed" and result_status in {"failed", "timeout"}:
        return "completed_with_validation_errors"
    return execution_status


def execution_status_without_validation_error(execution_status: str) -> str:
    if execution_status == "completed_with_validation_errors":
        return "completed"
    return execution_status


def validation_status_from_stage(stage: OrchestratedStageRecord | None) -> str:
    if stage is None:
        return "not_recorded"
    return str((stage.details or {}).get("validation_status", stage.status))


def fallback_details(args: argparse.Namespace) -> dict[str, Any]:
    session = getattr(args, "fallback_session", None)
    if session is None:
        return {}
    return {
        "effective_route_id": session.current.route_id,
        "fallback_attempts": list(session.attempts),
        **({"fallback_handoff": session.handoff} if session.handoff is not None else {}),
    }
