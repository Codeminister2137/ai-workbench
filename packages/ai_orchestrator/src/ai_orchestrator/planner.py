"""Convert model recommendations into neutral execution plans."""

from __future__ import annotations

from dataclasses import dataclass

from ai_orchestrator.models import ModelRecommendation, TaskProfile


@dataclass(frozen=True, slots=True)
class ExecutionTarget:
    """Neutral execution target that callers adapt to their chosen executor."""

    provider: str
    model: str
    base_url: str | None = None
    timeout_seconds: float = 60.0


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """Prepared execution target and human-readable planning reasons."""

    target: ExecutionTarget
    reasons: tuple[str, ...]


def plan_execution(
    profile: TaskProfile,
    recommendation: ModelRecommendation,
    *,
    timeout_seconds: float = 60.0,
) -> ExecutionPlan:
    """Create a neutral execution plan from a selected model recommendation."""

    selected = recommendation.selected.backend
    model = profile.user_model_override or selected.model
    target = ExecutionTarget(
        provider=selected.provider,
        model=model,
        base_url=selected.base_url,
        timeout_seconds=timeout_seconds,
    )
    return ExecutionPlan(
        target=target,
        reasons=recommendation.reasons,
    )
