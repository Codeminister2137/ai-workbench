from __future__ import annotations

from ai_orchestrator import (
    ExecutionTarget,
    ModelCatalogEntry,
    OrchestrationResult,
    TaskProfile,
    prepare_execution,
)
from ai_provider import AIMessage, AIRequest, BackendConfig, MessageRole, PrivacyClass, ProviderKind


def backend_config_from_execution_target(target: ExecutionTarget) -> BackendConfig:
    """Adapt an orchestrator execution decision to the ai_provider config shape."""
    try:
        provider = ProviderKind(target.provider)
    except ValueError as exc:
        supported = ", ".join(kind.value for kind in ProviderKind)
        raise ValueError(
            f"Execution target provider {target.provider!r} is not supported by "
            f"ai_provider. Supported providers: {supported}."
        ) from exc

    return BackendConfig(
        provider=provider,
        model=target.model,
        base_url=target.base_url,
        timeout_seconds=target.timeout_seconds,
    )


def prepare_backend_config(
    prompt: str,
    profile: TaskProfile,
    catalog: tuple[ModelCatalogEntry, ...],
    *,
    review_prompt: bool = True,
    timeout_seconds: float = 60.0,
) -> tuple[OrchestrationResult, BackendConfig | None]:
    """Prepare an ai_provider config from orchestrator output without executing a request."""
    result = prepare_execution(
        prompt,
        profile,
        catalog,
        review_prompt=review_prompt,
        timeout_seconds=timeout_seconds,
    )
    if not result.is_ready or result.execution_plan is None:
        return result, None

    return result, backend_config_from_execution_target(result.execution_plan.target)


def ai_request_from_prompt(
    prompt: str,
    profile: TaskProfile,
    config: BackendConfig,
) -> AIRequest:
    """Build a provider request after orchestration has selected a backend config."""
    return AIRequest(
        messages=(AIMessage(MessageRole.USER, prompt),),
        model=config.model,
        privacy_class=PrivacyClass(profile.privacy_class.value),
        metadata={
            "orchestrator_selected_provider": config.provider.value,
            "orchestrator_selected_model": config.model,
        },
    )


def prepare_provider_request(
    prompt: str,
    profile: TaskProfile,
    catalog: tuple[ModelCatalogEntry, ...],
    *,
    review_prompt: bool = True,
    timeout_seconds: float = 60.0,
) -> tuple[OrchestrationResult, BackendConfig | None, AIRequest | None]:
    """Prepare provider config and request objects without executing the request."""
    result, config = prepare_backend_config(
        prompt,
        profile,
        catalog,
        review_prompt=review_prompt,
        timeout_seconds=timeout_seconds,
    )
    if config is None:
        return result, None, None

    return result, config, ai_request_from_prompt(prompt, profile, config)


def main() -> None:
    target = ExecutionTarget(
        provider="ollama",
        model="llama3.2",
        base_url="http://localhost:11434",
        timeout_seconds=30,
    )
    config = backend_config_from_execution_target(target)
    print(config)


if __name__ == "__main__":
    main()
