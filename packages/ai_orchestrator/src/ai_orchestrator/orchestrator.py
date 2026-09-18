from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai_orchestrator.models import (
    ModelCatalogEntry,
    ModelRecommendation,
    PromptIssueSeverity,
    PromptJudgeResult,
    TaskProfile,
)
from ai_orchestrator.planner import ExecutionPlan, plan_execution
from ai_orchestrator.prompt_judge import judge_prompt
from ai_orchestrator.recommender import recommend_model


class OrchestrationStatus(StrEnum):
    READY = "ready"
    NEEDS_PROMPT_REVIEW = "needs_prompt_review"
    MODEL_SELECTION_FAILED = "model_selection_failed"


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    original_prompt: str
    profile: TaskProfile
    status: OrchestrationStatus
    prompt_judge: PromptJudgeResult | None
    recommendation: ModelRecommendation | None
    execution_plan: ExecutionPlan | None
    failure_reason: str | None = None

    @property
    def is_ready(self) -> bool:
        return self.status is OrchestrationStatus.READY


def prepare_execution(
    prompt: str,
    profile: TaskProfile,
    catalog: tuple[ModelCatalogEntry, ...],
    *,
    review_prompt: bool = True,
    timeout_seconds: float = 60.0,
) -> OrchestrationResult:
    prompt_judge = judge_prompt(prompt, profile) if review_prompt else None
    if prompt_judge is not None and _needs_prompt_review(prompt_judge):
        return OrchestrationResult(
            original_prompt=prompt,
            profile=profile,
            status=OrchestrationStatus.NEEDS_PROMPT_REVIEW,
            prompt_judge=prompt_judge,
            recommendation=None,
            execution_plan=None,
        )

    try:
        recommendation = recommend_model(profile, catalog)
    except ValueError as exc:
        return OrchestrationResult(
            original_prompt=prompt,
            profile=profile,
            status=OrchestrationStatus.MODEL_SELECTION_FAILED,
            prompt_judge=prompt_judge,
            recommendation=None,
            execution_plan=None,
            failure_reason=str(exc),
        )

    execution_plan = plan_execution(
        profile,
        recommendation,
        timeout_seconds=timeout_seconds,
    )

    return OrchestrationResult(
        original_prompt=prompt,
        profile=profile,
        status=OrchestrationStatus.READY,
        prompt_judge=prompt_judge,
        recommendation=recommendation,
        execution_plan=execution_plan,
    )


def _needs_prompt_review(prompt_judge: PromptJudgeResult) -> bool:
    return prompt_judge.should_refine or any(
        issue.severity is PromptIssueSeverity.BLOCKING for issue in prompt_judge.issues
    )
