from __future__ import annotations

from dataclasses import dataclass

from ai_provider import BackendConfig, ProviderError, ProviderErrorCategory, ProviderKind

from ai_orchestrator.models import ModelRecommendation, TaskProfile


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    backend_config: BackendConfig
    reasons: tuple[str, ...]


def plan_execution(
    profile: TaskProfile,
    recommendation: ModelRecommendation,
    *,
    timeout_seconds: float = 60.0,
) -> ExecutionPlan:
    selected = recommendation.selected.backend
    try:
        provider = ProviderKind(selected.provider)
    except ValueError as exc:
        raise ProviderError(
            f"Recommended provider is not supported by ai_provider: {selected.provider}.",
            category=ProviderErrorCategory.CONFIGURATION,
            provider=selected.provider,
            raw_error=exc,
        ) from exc

    model = profile.user_model_override or selected.model
    config = BackendConfig(
        provider=provider,
        model=model,
        base_url=selected.base_url,
        timeout_seconds=timeout_seconds,
    )
    return ExecutionPlan(
        backend_config=config,
        reasons=recommendation.reasons,
    )
