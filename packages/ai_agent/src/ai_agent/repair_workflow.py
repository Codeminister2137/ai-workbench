"""Reusable repair workflow driven by deterministic validation and observed effects."""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from ai_orchestrator.repair import repair_progress
from ai_orchestrator.review import research_review_reserve_seconds
from ai_provider import ProviderError
from ai_provider.orchestrated_runs import OrchestratedStageRecord
from ai_provider.repair_state import changed_paths, workspace_fingerprints

from ai_agent.run_tracking import (
    OrchestratedRunTracker,
    execution_status_with_validation_stage,
    execution_status_without_validation_error,
    fallback_details,
    remaining_orchestrated_budget_seconds,
    validation_status_from_stage,
)
from ai_agent.validation import validation_commands_from_args


def validation_stage_needs_repair(stage: OrchestratedStageRecord | None) -> bool:
    return validation_status_from_stage(stage) in {"failed", "timeout"}


def format_validation_failures_for_prompt(stage: OrchestratedStageRecord | None) -> str:
    if stage is None or not stage.details:
        return "No deterministic validation details were recorded."
    results = stage.details.get("results")
    if not isinstance(results, list) or not results:
        return json.dumps(stage.details, indent=2, sort_keys=True)
    formatted: list[str] = []
    for index, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            continue
        formatted.append(f"Validation command {index}: {item.get('command', '')}")
        formatted.append(f"Status: {item.get('status', '')}")
        if item.get("returncode") is not None:
            formatted.append(f"Return code: {item.get('returncode')}")
        if item.get("failure_reason"):
            formatted.append(f"Failure reason: {item.get('failure_reason')}")
        if item.get("stdout_preview"):
            formatted.append("Stdout preview:")
            formatted.append(str(item["stdout_preview"]))
        if item.get("stderr_preview"):
            formatted.append("Stderr preview:")
            formatted.append(str(item["stderr_preview"]))
        formatted.append("")
    return "\n".join(formatted).strip() or json.dumps(stage.details, indent=2, sort_keys=True)


def build_orchestrated_repair_prompt(
    *,
    original_prompt: str,
    validation_stage: OrchestratedStageRecord | None,
    assistant_response_text: str | None,
    attempt_number: int,
) -> str:
    """Build a focused repair prompt from deterministic validation evidence."""

    assistant_summary = assistant_response_text or "No prior assistant response was captured."
    if len(assistant_summary) > 6000:
        assistant_summary = assistant_summary[:6000] + (
            "\n[Prior response excerpt truncated; inspect the saved artifact/current files "
            "before changing them. Original task and validation evidence follow intact.]"
        )
    return (
        "Repair the repository changes from the previous implementation attempt.\n\n"
        "Original task:\n"
        f"{original_prompt}\n\n"
        "Latest assistant response:\n"
        f"{assistant_summary}\n\n"
        "Deterministic validation failure evidence:\n"
        f"{format_validation_failures_for_prompt(validation_stage)}\n\n"
        f"Repair attempt: {attempt_number}\n\n"
        "Make the smallest focused fix needed for the validation failure. Preserve the "
        "original requested behavior, do not expand scope, and stop at any material "
        "decision boundary."
    )


def validation_failure_fingerprint(stage: OrchestratedStageRecord | None) -> str:
    """Ignore ordinary timing noise when comparing deterministic failure evidence."""
    evidence = format_validation_failures_for_prompt(stage)
    return re.sub(r"\b\d+(?:\.\d+)?\s*(?:ms|s|seconds)\b", "<duration>", evidence)


def run_orchestrated_repair_loop(
    *,
    args: argparse.Namespace,
    tracker: OrchestratedRunTracker,
    repo_root: Path,
    execution_status: str,
    validation_stage: OrchestratedStageRecord | None,
    original_prompt: str,
    assistant_response_text: str | None,
    deadline: float | None,
    repair_attempt: Callable[[str, int, float], tuple[str, str | None]],
) -> tuple[str, OrchestratedStageRecord | None, str | None]:
    """Run bounded repair attempts until validation passes or policy stops the loop."""

    validation_status = validation_status_from_stage(validation_stage)
    if not (
        args.mode == "implement"
        and args.execute
        and execution_status.startswith("completed")
        and validation_stage_needs_repair(validation_stage)
    ):
        tracker.complete_stage(
            "repair",
            status="skipped",
            details={
                "skip_reason": "repair not needed",
                "validation_status_before_repair": validation_status,
            },
        )
        return execution_status, validation_stage, assistant_response_text

    execution_status = execution_status_with_validation_stage(execution_status, validation_stage)
    deadline = tracker.deadline if deadline is None else min(deadline, tracker.deadline)
    max_cycles = args.max_repair_cycles
    if max_cycles == 0:
        tracker.complete_stage(
            "repair",
            status="skipped",
            details={
                "skip_reason": "repair disabled by --max-repair-cycles 0",
                "validation_status_before_repair": validation_status,
            },
        )
        return execution_status, validation_stage, assistant_response_text

    tracker.start_stage(
        "repair",
        details={
            "max_repair_cycles": "unbounded" if max_cycles == -1 else max_cycles,
            "validation_status_before_repair": validation_status,
        },
    )
    attempts: list[dict[str, object]] = []
    attempt_number = 0
    repair_status = "failed"
    no_progress_count = 0
    stop_reason = "cycle_limit"
    reserve = research_review_reserve_seconds(
        tracker.run_record.budget_seconds,
        enabled=(
            getattr(args, "research_review_policy", "legacy") == "quality_first"
            and getattr(args, "research_execution", None) is not None
        ),
    )
    while max_cycles == -1 or attempt_number < max_cycles:
        remaining = remaining_orchestrated_budget_seconds(
            deadline=deadline, floor_seconds=reserve + 1.0
        )
        if remaining is not None and remaining <= 0:
            repair_status = "timeout"
            stop_reason = "review_budget_reserved"
            break
        attempt_number += 1
        print(f"repair_cycle: {attempt_number} status=running")
        repair_prompt = build_orchestrated_repair_prompt(
            original_prompt=original_prompt,
            validation_stage=validation_stage,
            assistant_response_text=assistant_response_text,
            attempt_number=attempt_number,
        )
        before = workspace_fingerprints(repo_root)
        previous_failure = validation_failure_fingerprint(validation_stage)
        # Leave part of the repair allocation for deterministic validation.
        timeout_seconds = (
            min(args.timeout_seconds, remaining / 2)
            if remaining is not None
            else args.timeout_seconds
        )
        try:
            attempt_status, attempt_response = repair_attempt(
                repair_prompt,
                attempt_number,
                timeout_seconds,
            )
        except (ProviderError, subprocess.TimeoutExpired, OSError, RuntimeError) as exc:
            attempt_status = "timeout" if isinstance(exc, subprocess.TimeoutExpired) else "failed"
            attempt_response = None
            failure_reason = str(exc)
        else:
            failure_reason = ""
        if attempt_response:
            assistant_response_text = attempt_response
        print(f"repair_cycle: {attempt_number} status={attempt_status}")
        attempt_details: dict[str, object] = {
            "attempt": attempt_number,
            "status": attempt_status,
            **fallback_details(args),
        }
        if failure_reason:
            print(f"repair_cycle_failure_reason: {failure_reason}")
            attempt_details["failure_reason"] = failure_reason
        if attempt_status != "completed":
            attempts.append(attempt_details)
            repair_status = attempt_status
            stop_reason = "repair_execution_failed"
            break
        validation_args = copy.copy(args)
        validation_remaining = remaining_orchestrated_budget_seconds(
            deadline=deadline, floor_seconds=reserve + 1.0
        )
        if validation_remaining is not None and validation_remaining <= 0:
            attempts.append(attempt_details)
            repair_status = "timeout"
            stop_reason = "review_budget_reserved"
            break
        if validation_remaining is not None:
            command_count = max(1, len(validation_commands_from_args(args)))
            validation_args.validation_timeout_seconds = min(
                args.validation_timeout_seconds, validation_remaining / command_count
            )
        after = workspace_fingerprints(repo_root)
        validation_stage = tracker.record_validation_stage(
            args=validation_args,
            repo_root=repo_root,
            execution_status=execution_status,
        )
        validation_status = validation_status_from_stage(validation_stage)
        attempt_details["validation_status"] = validation_status
        paths = changed_paths(before, after)
        progress = repair_progress(
            state_changed=bool(paths),
            failure_changed=previous_failure != validation_failure_fingerprint(validation_stage),
        )
        attempt_details["progress"] = progress
        attempt_details["changed_paths"] = paths
        no_progress_count = no_progress_count + 1 if progress == "no_progress" else 0
        print(f"repair_progress: {progress} consecutive_no_progress={no_progress_count}")
        attempts.append(attempt_details)
        if validation_status == "passed":
            repair_status = "completed"
            execution_status = execution_status_without_validation_error(execution_status)
            stop_reason = "validation_passed"
            break
        if not validation_stage_needs_repair(validation_stage):
            repair_status = "skipped"
            stop_reason = "validation_not_run"
            break
        if no_progress_count >= 2:
            repair_status = "stalled"
            stop_reason = "repeated_no_progress"
            break

    if repair_status != "completed" and validation_stage_needs_repair(validation_stage):
        execution_status = execution_status_with_validation_stage(
            execution_status,
            validation_stage,
        )
    tracker.complete_stage(
        "repair",
        status=repair_status,
        details={
            "attempts": attempts,
            "attempt_count": attempt_number,
            "stop_reason": stop_reason,
            "review_reserve_seconds": reserve,
            "validation_status_after_repair": validation_status_from_stage(validation_stage),
        },
    )
    return execution_status, validation_stage, assistant_response_text
