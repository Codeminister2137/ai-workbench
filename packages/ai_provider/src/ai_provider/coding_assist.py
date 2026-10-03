"""Coding-assistant orchestration and provider request helpers."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai_orchestrator import (
    AccessMethod,
    CostPolicyTier,
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
    OllamaResourceProfile,
    PrivacyClass,
    ProviderKind,
    create_chat_client,
    ensure_ollama_server,
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

    if target.access_method not in {
        AccessMethod.LOCAL_RUNTIME,
        AccessMethod.PROVIDER_API,
    }:
        raise ValueError(
            f"Execution target access method {target.access_method.value!r} "
            "is not supported by ai_provider. Use a dedicated executor for this route."
        )

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
        require_free_model=(
            provider is ProviderKind.REQUESTY
            and target.cost_policy_tier is CostPolicyTier.FREE_ONLY
        ),
    )


def coding_request_from_prompt(
    prompt: str,
    profile: TaskProfile,
    config: BackendConfig,
    *,
    system_prompt: str | None = None,
) -> AIRequest:
    """Build a provider-neutral request for a coding prompt."""

    messages = (AIMessage(MessageRole.USER, prompt),)
    if system_prompt:
        messages = (
            AIMessage(MessageRole.SYSTEM, system_prompt),
            *messages,
        )

    return AIRequest(
        messages=messages,
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
    prompt_for_review: str | None = None,
    timeout_seconds: float = 60.0,
    execute: bool = False,
    system_prompt: str | None = None,
    start_ollama: bool = False,
    ollama_command: str = "ollama",
    ollama_startup_timeout_seconds: float = 10.0,
    ollama_log_path: Path | None = None,
    ollama_resource_profile: OllamaResourceProfile | None = None,
    client_factory: Callable[[BackendConfig], ChatClient] = create_chat_client,
    progress_callback: Callable[[str], None] | None = None,
    progress_prefix: str = "local_agent_activity",
) -> CodingAssistResult:
    """Prepare and optionally execute one coding-oriented AI request."""

    orchestration = prepare_execution(
        prompt,
        profile,
        catalog,
        review_prompt=review_prompt,
        prompt_for_review=prompt_for_review,
        timeout_seconds=timeout_seconds,
    )
    if not orchestration.is_ready or orchestration.execution_plan is None:
        if progress_callback is not None:
            progress_callback(f"{progress_prefix}: failed - orchestration not ready")
        return CodingAssistResult(orchestration=orchestration)

    config = backend_config_from_execution_target(orchestration.execution_plan.target)
    request = coding_request_from_prompt(
        prompt,
        profile,
        config,
        system_prompt=system_prompt,
    )
    if not execute:
        if progress_callback is not None:
            progress_callback(
                f"{progress_prefix}: planned - route={orchestration.execution_plan.target.route_id}"
            )
        return CodingAssistResult(
            orchestration=orchestration,
            config=config,
            request=request,
        )

    if progress_callback is not None:
        progress_callback(
            f"{progress_prefix}: model_request - provider={config.provider.value} "
            f"model={config.model}"
        )
    if start_ollama and config.provider is ProviderKind.OLLAMA:
        if progress_callback is not None:
            progress_callback(f"{progress_prefix}: ollama_start - base_url={config.base_url}")
        if ollama_log_path is None and ollama_resource_profile is None:
            ensure_ollama_server(
                config.base_url,
                command=ollama_command,
                startup_timeout_seconds=ollama_startup_timeout_seconds,
            )
        elif ollama_resource_profile is None:
            ensure_ollama_server(
                config.base_url,
                command=ollama_command,
                startup_timeout_seconds=ollama_startup_timeout_seconds,
                log_path=ollama_log_path,
            )
        elif ollama_log_path is None:
            ensure_ollama_server(
                config.base_url,
                command=ollama_command,
                startup_timeout_seconds=ollama_startup_timeout_seconds,
                resource_profile=ollama_resource_profile,
            )
        else:
            ensure_ollama_server(
                config.base_url,
                command=ollama_command,
                startup_timeout_seconds=ollama_startup_timeout_seconds,
                log_path=ollama_log_path,
                resource_profile=ollama_resource_profile,
            )

    client = client_factory(config)
    response = client.complete(request)
    if progress_callback is not None:
        progress_callback(
            f"{progress_prefix}: completed - provider={response.backend.provider} "
            f"model={response.backend.model}"
        )
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
    cost_policy_tier: CostPolicyTier = CostPolicyTier.PREPAID_CREDITS_ALLOWED,
    route_id_override: str | None = None,
    access_method_override: AccessMethod | None = None,
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
        cost_policy_tier=cost_policy_tier,
        user_route_id_override=route_id_override,
        user_access_method_override=access_method_override,
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
    parser.add_argument("--route-id", help="Hard access-route override.")
    parser.add_argument(
        "--access-method",
        choices=[item.value for item in AccessMethod],
        help="Hard access-method override, such as local_runtime/provider_api.",
    )
    parser.add_argument("--model", help="Hard model override.")
    parser.add_argument(
        "--cost-policy",
        choices=[item.value for item in CostPolicyTier],
        default=CostPolicyTier.PREPAID_CREDITS_ALLOWED.value,
        help="Maximum billing boundary this task may cross.",
    )
    parser.add_argument(
        "--system",
        help="Optional provider-neutral system instruction sent before the user prompt.",
    )
    parser.add_argument("--max-latency-seconds", type=float, help="Hard latency constraint.")
    parser.add_argument("--timeout-seconds", type=float, default=60.0, help="Provider timeout.")
    parser.add_argument(
        "--start-ollama",
        action="store_true",
        help="Start `ollama serve` before executing a local Ollama request.",
    )
    parser.add_argument(
        "--ollama-command",
        default="ollama",
        help="Ollama executable used with --start-ollama.",
    )
    parser.add_argument(
        "--ollama-startup-timeout-seconds",
        type=float,
        default=10.0,
        help="Seconds to wait for Ollama to become reachable after starting it.",
    )
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
        cost_policy_tier=CostPolicyTier(args.cost_policy),
        route_id_override=args.route_id,
        access_method_override=(
            AccessMethod(args.access_method) if args.access_method is not None else None
        ),
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
        system_prompt=args.system,
        start_ollama=args.start_ollama,
        ollama_command=args.ollama_command,
        ollama_startup_timeout_seconds=args.ollama_startup_timeout_seconds,
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
    assert orchestration.execution_plan is not None
    print(f"route_id: {orchestration.execution_plan.target.route_id}")
    print(f"product: {orchestration.execution_plan.target.product}")
    print(f"provider: {result.config.provider.value}")
    print(f"model: {result.config.model}")
    print(f"cost_policy_tier: {orchestration.execution_plan.target.cost_policy_tier.value}")
    for reason in orchestration.recommendation.reasons:
        print(f"reason: {reason}")

    if result.response is not None:
        print(result.response.message.content)


if __name__ == "__main__":
    main()
