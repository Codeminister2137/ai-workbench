"""Final scrutiny of observed implementation evidence through local review policy."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from ai_orchestrator import (
    CostPolicyTier,
    LatencyTarget,
    ModelCatalogEntry,
    QualityThreshold,
    TaskProfile,
    TaskType,
    derive_subtask_profile,
)
from ai_orchestrator import PrivacyClass as OrchestratorPrivacyClass
from ai_orchestrator.review import ReviewMode, ReviewSettings, ReviewWorkload, select_review_plan
from ai_provider import (
    BackendConfig,
    ChatClient,
    ProviderError,
    ProviderKind,
    create_chat_client,
    get_ollama_resource_profile,
)
from ai_provider.coding_assist import CodingAssistResult, run_coding_prompt
from ai_provider.orchestrated_runs import OrchestratedStageRecord
from ai_provider.repair_state import changed_paths, workspace_fingerprints
from ai_provider.scrutiny import (
    RESEARCH_SCRUTINY_SYSTEM_PROMPT,
    RESPONSE_SCRUTINY_SYSTEM_PROMPT,
    build_research_scrutiny_prompt,
    build_response_scrutiny_prompt,
    parse_response_scrutiny_report,
)

from ai_agent.repair_workflow import format_validation_failures_for_prompt
from ai_agent.run_tracking import OrchestratedRunTracker, remaining_orchestrated_budget_seconds


def _print_research_admission_diagnostics(details: dict[str, Any]) -> None:
    """Expose bounded admission facts without printing tokenizer errors or paths."""
    review = details.get("research_review")
    if not isinstance(review, dict):
        return
    method = review.get("input_bound_method")
    if method in ("utf8_bytes_plus_framing", "verified_local_tokenizer"):
        print(f"scrutiny_input_bound_method: {method}")
    for key in ("input_token_upper_bound", "context_tokens"):
        value = review.get(key)
        if type(value) is int and value >= 0:
            print(f"scrutiny_{key}: {value}")
    fallback = review.get("tokenizer_fallback_reason")
    if fallback is not None:
        category = (
            "dependency_unavailable"
            if fallback == "Optional tokenizers dependency is unavailable"
            else "profile_unverified"
        )
        print(f"scrutiny_tokenizer_fallback: {category}")


def run_orchestrated_scrutiny(
    *,
    args: argparse.Namespace,
    tracker: OrchestratedRunTracker,
    repo_root: Path,
    profile: TaskProfile,
    catalog: tuple[ModelCatalogEntry, ...],
    validation_stage: OrchestratedStageRecord | None,
    assistant_response_text: str | None,
    execution_status: str,
    deadline: float | None,
    coding_runner: Callable[..., CodingAssistResult] = run_coding_prompt,
    client_factory: Callable[[BackendConfig], ChatClient] = create_chat_client,
) -> str:
    """Review observed implementation evidence locally after the last repair."""
    research = getattr(args, "research_execution", None)
    if research is not None and execution_status == "failed":
        tracker.complete_stage(
            "scrutiny", status="skipped", details={"skip_reason": "primary research failed"}
        )
        return execution_status
    tracker.start_stage(
        "scrutiny",
        details={
            "route_policy": "neutral_research_review"
            if research is not None
            and getattr(args, "research_review_policy", "legacy") == "quality_first"
            else "derived_local_cheap"
        },
    )
    deadline = tracker.deadline if deadline is None else min(deadline, tracker.deadline)
    remaining = remaining_orchestrated_budget_seconds(deadline=deadline)
    details: dict[str, object] = {}
    stage_status = "failed"
    tracker.scrutiny_status = "failed"
    if remaining is not None and remaining <= 0:
        tracker.scrutiny_status = "not_run"
        stage_status = "skipped"
        details["skip_reason"] = "wall-clock budget exhausted before scrutiny"
    else:
        paths = (
            []
            if research is not None
            else changed_paths(tracker.initial_workspace, workspace_fingerprints(repo_root))
        )
        # Keep the review bounded; fingerprints establish observed changes, not correctness.
        evidence = ["Observed changed/deleted paths:\n" + "\n".join(paths[:100])]
        if research is not None:
            evidence = [research.review_evidence()]
        content_budget = 12_000
        for name in paths:
            path = repo_root / name
            if path.suffix not in {".py", ".md", ".toml", ".ps1", ".txt", ".json"}:
                continue
            if content_budget <= 0:
                break
            try:
                with path.open(encoding="utf-8", errors="replace") as stream:
                    excerpt = stream.read(min(3_000, content_budget))
            except OSError:
                continue
            content_budget -= len(excerpt)
            evidence.append(f"File excerpt (may be incomplete): {name}\n{excerpt}")
        scrutiny_prompt = build_response_scrutiny_prompt(
            args.prompt,
            (
                (assistant_response_text or "No assistant response captured.")[:2_000]
                if research is not None
                else (assistant_response_text or "No assistant response captured.")
            )
            + "\n\nExecution status: "
            + execution_status
            + "\nDeterministic validation evidence:\n"
            + format_validation_failures_for_prompt(validation_stage)
            + "\n\n"
            + "\n\n".join(evidence),
        )
        review_options: dict[str, Any] = {"client_factory": client_factory}
        context_length = 32768
        scrutiny_system = (
            RESPONSE_SCRUTINY_SYSTEM_PROMPT
            + "\nReview the implementation claims against the supplied file excerpts and "
            "deterministic validation. Evidence is bounded: explicitly identify unverified "
            "claims. Never override failed or skipped validation with a pass claim. "
            "Recommend a concrete next action; do not execute actions."
        )
        if research is not None:
            from ai_provider.research_execution import ResearchChatClient

            scrutiny_prompt = build_research_scrutiny_prompt(
                args.prompt,
                assistant_response_text or "No assistant response captured.",
                execution_status=execution_status,
                validation_evidence=format_validation_failures_for_prompt(validation_stage),
                research_evidence="\n\n".join(evidence),
            )
            scrutiny_system = RESEARCH_SCRUTINY_SYSTEM_PROMPT
            context_length = (
                get_ollama_resource_profile(args.ollama_profile).context_length
                if args.ollama_profile
                else 32768
            )

            def research_reviewer_client(config: BackendConfig) -> ChatClient:
                return ResearchChatClient(
                    client_factory(config),
                    {"ollama_context_length": context_length},
                    max_output_tokens=1200,
                )

            review_options["client_factory"] = research_reviewer_client
        scrutiny_profile = derive_subtask_profile(
            parent=profile,
            task_type=TaskType.CLASSIFICATION,
            quality_threshold=QualityThreshold.STANDARD,
            latency_target=LatencyTarget.BACKGROUND,
            cost_policy_tier=CostPolicyTier.LOCAL_ONLY,
            privacy_class=OrchestratorPrivacyClass.LOCAL_ONLY,
        )
        try:
            if (
                research is not None
                and getattr(args, "research_review_policy", "legacy") == "quality_first"
            ):
                from ai_provider.research_execution import _validate_local_runtime
                from ai_provider.research_review import ResearchReviewClient

                review_model = getattr(args, "research_review_model", None)
                scrutiny_profile = replace(
                    scrutiny_profile,
                    user_model_override=review_model,
                )
                selected_mode = getattr(args, "research_review_mode", "auto")
                plan = select_review_plan(
                    scrutiny_profile,
                    catalog,
                    ReviewWorkload(),
                    mode_override=ReviewMode(selected_mode) if selected_mode != "auto" else None,
                    primary_model=tracker.run_record.primary_model,
                )
                _validate_local_runtime(
                    BackendConfig(
                        ProviderKind(plan.candidate.backend.provider),
                        plan.candidate.backend.model,
                        base_url=plan.candidate.backend.base_url,
                    )
                )
                scrutiny_profile = replace(
                    scrutiny_profile,
                    user_route_id_override=plan.candidate.backend.route_id,
                )
                settings = ReviewSettings(
                    getattr(args, "research_review_output_tokens", 4096),
                    getattr(args, "research_review_timeout_seconds", 300.0),
                )
                review_details: dict[str, object] = {
                    "policy": "quality_first",
                    "route_id": plan.candidate.backend.route_id,
                    "model": plan.candidate.backend.model,
                    "reasons": list(plan.reasons),
                }
                details["research_review"] = review_details

                def planned_reviewer_client(config: BackendConfig) -> ChatClient:
                    return ResearchReviewClient(
                        config,
                        plan.mode,
                        context_length,
                        settings,
                        deadline,
                        details=review_details,
                        client_factory=client_factory,
                        tokenizer_file=getattr(args, "research_review_tokenizer_file", None),
                    )

                review_options["client_factory"] = planned_reviewer_client
            scrutiny = coding_runner(
                scrutiny_prompt,
                scrutiny_profile,
                catalog,
                review_prompt=False,
                timeout_seconds=min(args.timeout_seconds, remaining)
                if remaining is not None
                else args.timeout_seconds,
                execute=True,
                system_prompt=scrutiny_system,
                start_ollama=args.start_ollama,
                ollama_command=args.ollama_command,
                ollama_startup_timeout_seconds=args.ollama_startup_timeout_seconds,
                ollama_log_path=args.ollama_log_file,
                ollama_resource_profile=get_ollama_resource_profile(args.ollama_profile)
                if args.ollama_profile
                else None,
                progress_callback=print,
                progress_prefix="scrutiny_activity",
                **review_options,
            )
            if scrutiny.response is None:
                raise ProviderError(scrutiny.orchestration.failure_reason or "No scrutiny response")
            report = parse_response_scrutiny_report(scrutiny.response.message.content)
        except (ProviderError, ValueError) as exc:
            details["failure_reason"] = str(exc)
            print(f"scrutiny_failure_reason: {exc}")
            _print_research_admission_diagnostics(details)
        else:
            stage_status = "completed"
            tracker.scrutiny_status = report.verdict
            details.update(
                verdict=report.verdict,
                score=report.score,
                issues=report.issues,
                next_action=report.recommended_next_action,
                revised_response=report.revised_response,
            )
            print(report.raw_text)
    details["scrutiny_status"] = tracker.scrutiny_status
    tracker.complete_stage("scrutiny", status=stage_status, details=details)
    print(f"scrutiny_status: {tracker.scrutiny_status}")
    if execution_status == "completed" and tracker.scrutiny_status != "pass":
        return (
            "completed_with_scrutiny_findings"
            if stage_status == "completed"
            else "completed_with_scrutiny_errors"
        )
    return execution_status
