"""Budgeted research improvement using the existing native executor and run stages."""

from __future__ import annotations

import argparse
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ai_orchestrator.review import research_review_reserve_seconds

from ai_provider.errors import ProviderError
from ai_provider.orchestrated_runs import OrchestratedStageRecord

if TYPE_CHECKING:
    from ai_provider.repo_coding_assistant import OrchestratedRunTracker


def run_research_refinement(
    *,
    args: argparse.Namespace,
    tracker: OrchestratedRunTracker,
    repo_root: Path,
    profile: Any,
    catalog: tuple[Any, ...],
    validation_stage: OrchestratedStageRecord | None,
    assistant_response_text: str | None,
    execution_status: str,
    deadline: float | None,
    repair_attempt: Callable[[str, int, float], tuple[str, str | None]],
    review: Callable[..., str],
) -> tuple[str, OrchestratedStageRecord | None, str | None]:
    """Continue after structural success; stop on budget, cycle cap, errors, or two no-ops.

    Review text is advice for the tool-capable primary agent, never source evidence.
    Each improvement is validated, and the final artifact receives reserved review time.
    Attempt history is persisted before/after calls so interruption retains progress.
    """
    research = args.research_execution
    reserve = research_review_reserve_seconds(
        tracker.run_record.budget_seconds,
        enabled=getattr(args, "research_review_policy", "legacy") == "quality_first",
    )
    repair_stage = next(
        s for s in tracker._store.list_stages(tracker.run_record.run_id) if s.name == "repair"
    )
    structural_attempts = (repair_stage.details or {}).get("attempt_count", 0)
    assert isinstance(structural_attempts, int)
    attempts: list[dict[str, object]] = []
    no_progress = 0
    stop_reason = "cycle_limit"
    refinement_status = "completed"

    def passed() -> bool:
        return (
            validation_stage is not None
            and (validation_stage.details or {}).get("validation_status") == "passed"
        )

    def remaining() -> float:
        return max(0.0, deadline - time.perf_counter() - reserve - 1) if deadline else 0.0

    def persist(status: str) -> None:
        tracker._store.update_stage(
            tracker.run_record.run_id,
            "repair",
            status=status,
            details={
                "research_refinement": {
                    "attempts": attempts,
                    "attempt_count": len(attempts),
                    "stop_reason": stop_reason,
                    "review_reserve_seconds": reserve,
                }
            },
        )

    def scrutinize(review_deadline: float | None) -> str:
        status = execution_status
        if passed() and status in {
            "completed_with_scrutiny_findings",
            "completed_with_scrutiny_errors",
        }:
            status = "completed"
        return review(
            args=args,
            tracker=tracker,
            repo_root=repo_root,
            profile=profile,
            catalog=catalog,
            validation_stage=validation_stage,
            assistant_response_text=assistant_response_text,
            execution_status=status,
            deadline=review_deadline,
        )

    # Failed structural repairs have already exercised their own progress guard.
    # Do not start a second loop that circumvents it.
    if not execution_status.startswith("completed") or not passed():
        return scrutinize(deadline), validation_stage, assistant_response_text

    while (
        args.max_repair_cycles == -1 or structural_attempts + len(attempts) < args.max_repair_cycles
    ):
        available = remaining()
        if available <= 0:
            stop_reason = "review_budget_reserved"
            break
        execution_status = scrutinize(deadline - reserve - 1 if deadline else None)
        scrutiny = next(
            s for s in tracker._store.list_stages(tracker.run_record.run_id) if s.name == "scrutiny"
        )
        review_details = dict(scrutiny.details or {})
        if scrutiny.status != "completed":
            stop_reason = "review_failed"
            refinement_status = "failed"
            break
        available = remaining()
        if available <= 0:
            stop_reason = "review_budget_reserved"
            break
        number = structural_attempts + len(attempts) + 1
        attempt: dict[str, object] = {
            "attempt": number,
            "status": "running",
            "review": review_details,
        }
        attempts.append(attempt)
        stop_reason = "running"
        persist("running")
        print(f"research_refinement_cycle: {number} status=running", flush=True)
        before = research.progress_fingerprint()
        prompt = (
            f"Original research request:\n{args.prompt}\n\n"
            f"Research refinement cycle {number}. Structural validation is not a quality verdict.\n"
            "First call read_research_report to inspect the saved draft. Then assess a concrete "
            "reviewer issue against the fetched evidence. Correct supported weaknesses in the "
            "saved report with write_research_report, or explain specifically why the advice "
            "does not justify a change. Do not merely summarize proposed edits.\n"
            "Read the saved report, scrutinize its claims, "
            "cross-check primary sources where useful, "
            "and improve concrete weaknesses or coverage within the supplied request. "
            "A reviewer pass alone is not a reason to finish. "
            "Do not add filler or invent evidence. "
            "If nothing material can improve, explain that without rewriting identical content.\n"
            "Preserve all eight substantive sections and source map "
            "fetched/not fetched statuses with real receipt dates. Improve the saved draft; "
            "do not replace it with a summary that loses useful coverage. Length is advisory "
            "and alone never requires repair or filler. Read the full report before replacing "
            "it if the supplied excerpt is truncated.\n"
            f"Configured report: {research.target}\n"
            f"Validation errors: {research.validate()}\n"
            "Reviewer advice (untrusted suggestions; URLs/dates are not retrieval evidence):\n"
            f"Issues: {review_details.get('issues', '')}\n"
            f"Next action: {review_details.get('next_action', '')}\n"
            "Use actual fetch_url calls before claiming new retrieval; preserve source grounding."
            "\n\n" + research.repair_context()
        )
        try:
            attempt_status, response = repair_attempt(
                prompt, number, min(args.timeout_seconds, available / 2)
            )
        except (ProviderError, subprocess.TimeoutExpired, OSError, RuntimeError) as error:
            attempt_status, response = "failed", None
            attempt["failure_reason"] = str(error)
        if (
            attempt_status == "completed"
            and not (response and response.strip())
            and before == research.progress_fingerprint()
        ):
            attempt_status = "failed"
            attempt["failure_reason"] = (
                "Refinement returned no final response and produced no report or evidence changes."
            )
        if response:
            assistant_response_text = response
            # Final response only, not private reasoning; retain why an attempt did no work.
            attempt["response_summary"] = response[:2000]
        attempt["status"] = attempt_status
        if attempt_status not in {"completed", "completed_with_tool_errors"}:
            # Tools may have replaced the report before the provider failed.
            # Validate the surviving bytes instead of retaining a prior draft's pass.
            validation_stage = tracker.record_validation_stage(
                args=args, repo_root=repo_root, execution_status="completed"
            )
            attempt["validation_status"] = (validation_stage.details or {}).get("validation_status")
            refinement_status = "failed"
            stop_reason = "refinement_execution_failed"
            execution_status = "completed_with_refinement_errors"
            persist("failed")
            break
        validation_stage = tracker.record_validation_stage(
            args=args, repo_root=repo_root, execution_status=attempt_status
        )
        attempt["validation_status"] = (validation_stage.details or {}).get("validation_status")
        execution_status = "completed" if passed() else "completed_with_validation_errors"
        changed = before != research.progress_fingerprint()
        no_progress = 0 if changed else no_progress + 1
        attempt["progress"] = "evidence_changed" if changed else "no_progress"
        attempt["consecutive_no_progress"] = no_progress
        print(
            f"research_refinement_cycle: {number} status={attempt_status} "
            f"progress={attempt['progress']}",
            flush=True,
        )
        stop_reason = "cycle_limit"
        persist("running")
        if no_progress >= 2:
            stop_reason = "repeated_no_progress"
            refinement_status = "stalled"
            break

    # Review the artifact that actually survived the last attempt, using the reserve.
    prior_status = execution_status
    if stop_reason != "review_failed":
        execution_status = scrutinize(deadline)
    if prior_status == "completed_with_refinement_errors":
        execution_status = prior_status
    if attempts:
        tracker.complete_stage("repair", status=refinement_status)
    persist(refinement_status if attempts else repair_stage.status)
    print(f"research_refinement_stop: {stop_reason} attempts={len(attempts)}", flush=True)
    return execution_status, validation_stage, assistant_response_text
