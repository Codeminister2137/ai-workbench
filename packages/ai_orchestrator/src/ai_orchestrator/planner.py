from __future__ import annotations

from dataclasses import dataclass

from ai_orchestrator.models import ModelRecommendation, TaskProfile


@dataclass(frozen=True, slots=True)
class ExecutionTarget:
    provider: str
    model: str
    base_url: str | None = None
    timeout_seconds: float = 60.0


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    target: ExecutionTarget
    reasons: tuple[str, ...]


def plan_execution(
    profile: TaskProfile,
    recommendation: ModelRecommendation,
    *,
    timeout_seconds: float = 60.0,
) -> ExecutionPlan:
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
