from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai_orchestrator import (
    ExecutionTarget,
    LatencyTarget,
    ModelCatalogEntry,
    OrchestrationResult,
    OrchestrationStatus,
    QualityThreshold,
    TaskCapability,
    TaskProfile,
    TaskType,
    load_model_catalog,
    prepare_execution,
)
from ai_orchestrator import PrivacyClass as OrchestratorPrivacyClass
from ai_provider import (
    AIMessage,
    AIRequest,
    AIResponse,
    BackendConfig,
    ChatClient,
    MessageRole,
    PrivacyClass,
    ProviderKind,
    create_chat_client,
)


@dataclass(frozen=True, slots=True)
class CodingAssistResult:
    """Prepared or executed coding-assistant request."""

    orchestration: OrchestrationResult
    config: BackendConfig | None = None
    request: AIRequest | None = None
    response: AIResponse | None = None


def backend_config_from_execution_target(target: ExecutionTarget) -> BackendConfig:
    """Adapt an orchestrator execution target to provider runtime config."""

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


def coding_request_from_prompt(
    prompt: str,
    profile: TaskProfile,
    config: BackendConfig,
) -> AIRequest:
    """Build a provider-neutral request for a coding prompt."""

    return AIRequest(
        messages=(AIMessage(MessageRole.USER, prompt),),
        model=config.model,
        privacy_class=PrivacyClass(profile.privacy_class.value),
        metadata={
            "task_type": profile.task_type.value,
            "orchestrator_selected_provider": config.provider.value,
            "orchestrator_selected_model": config.model,
        },
    )


def run_coding_prompt(
    prompt: str,
    profile: TaskProfile,
    catalog: tuple[ModelCatalogEntry, ...],
    *,
    review_prompt: bool = True,
    timeout_seconds: float = 60.0,
    execute: bool = False,
    client_factory: Callable[[BackendConfig], ChatClient] = create_chat_client,
) -> CodingAssistResult:
    """Prepare and optionally execute one coding-oriented AI request."""

    orchestration = prepare_execution(
        prompt,
        profile,
        catalog,
        review_prompt=review_prompt,
        timeout_seconds=timeout_seconds,
    )
    if not orchestration.is_ready or orchestration.execution_plan is None:
        return CodingAssistResult(orchestration=orchestration)

    config = backend_config_from_execution_target(orchestration.execution_plan.target)
    request = coding_request_from_prompt(prompt, profile, config)
    if not execute:
        return CodingAssistResult(
            orchestration=orchestration,
            config=config,
            request=request,
        )

    client = client_factory(config)
    response = client.complete(request)
    return CodingAssistResult(
        orchestration=orchestration,
        config=config,
        request=request,
        response=response,
    )


def coding_task_profile(
    *,
    privacy_class: OrchestratorPrivacyClass = OrchestratorPrivacyClass.LOCAL_ONLY,
    quality_threshold: QualityThreshold = QualityThreshold.STANDARD,
    latency_target: LatencyTarget = LatencyTarget.INTERACTIVE,
    max_expected_latency_seconds: float | None = None,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> TaskProfile:
    """Create the default task profile for coding-assistant requests."""

    return TaskProfile(
        task_type=TaskType.CODING,
        privacy_class=privacy_class,
        required_capabilities=frozenset({TaskCapability.CHAT}),
        quality_threshold=quality_threshold,
        latency_target=latency_target,
        max_expected_latency_seconds=max_expected_latency_seconds,
        user_backend_override=provider_override,
        user_model_override=model_override,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare or execute a coding AI request.")
    parser.add_argument("prompt", help="Coding prompt to prepare or execute.")
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("packages/ai_orchestrator/examples/model_catalog.toml"),
        help="Path to a TOML model catalog.",
    )
    parser.add_argument(
        "--privacy",
        choices=[item.value for item in OrchestratorPrivacyClass],
        default=OrchestratorPrivacyClass.LOCAL_ONLY.value,
        help="Privacy class for the request.",
    )
    parser.add_argument(
        "--quality",
        choices=[item.value for item in QualityThreshold],
        default=QualityThreshold.STANDARD.value,
        help="Minimum quality threshold.",
    )
    parser.add_argument(
        "--provider",
        help="Hard provider override, such as ollama/openai/requesty.",
    )
    parser.add_argument("--model", help="Hard model override.")
    parser.add_argument("--max-latency-seconds", type=float, help="Hard latency constraint.")
    parser.add_argument("--timeout-seconds", type=float, default=60.0, help="Provider timeout.")
    parser.add_argument(
        "--skip-prompt-review",
        action="store_true",
        help="Bypass deterministic prompt review.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the provider request. Without this, only print the prepared plan.",
    )
    args = parser.parse_args()

    catalog = load_model_catalog(args.catalog)
    profile = coding_task_profile(
        privacy_class=OrchestratorPrivacyClass(args.privacy),
        quality_threshold=QualityThreshold(args.quality),
        max_expected_latency_seconds=args.max_latency_seconds,
        provider_override=args.provider,
        model_override=args.model,
    )
    result = run_coding_prompt(
        args.prompt,
        profile,
        catalog,
        review_prompt=not args.skip_prompt_review,
        timeout_seconds=args.timeout_seconds,
        execute=args.execute,
    )
    _print_result(result)


def _print_result(result: CodingAssistResult) -> None:
    orchestration = result.orchestration
    print(f"status: {orchestration.status.value}")

    if orchestration.status is OrchestrationStatus.NEEDS_PROMPT_REVIEW:
        assert orchestration.prompt_judge is not None
        for issue in orchestration.prompt_judge.issues:
            print(f"prompt_issue: {issue.severity.value} {issue.code}: {issue.message}")
        if orchestration.prompt_judge.refined_prompt:
            print(f"suggested_prompt: {orchestration.prompt_judge.refined_prompt}")
        return

    if orchestration.status is OrchestrationStatus.MODEL_SELECTION_FAILED:
        print(f"failure_reason: {orchestration.failure_reason}")
        return

    assert result.config is not None
    assert orchestration.recommendation is not None
    print(f"provider: {result.config.provider.value}")
    print(f"model: {result.config.model}")
    for reason in orchestration.recommendation.reasons:
        print(f"reason: {reason}")

    if result.response is not None:
        print(result.response.message.content)


if __name__ == "__main__":
    main()
