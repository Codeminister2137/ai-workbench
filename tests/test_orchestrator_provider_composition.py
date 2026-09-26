from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from ai_orchestrator import (
    AccessMethod,
    AccessRoute,
    AuthMethod,
    BackendLocation,
    BillingSource,
    CostPolicyTier,
    ExecutionTarget,
    ModelBackend,
    ModelCatalogEntry,
    OrchestrationStatus,
    TaskProfile,
)
from ai_orchestrator import (
    PrivacyClass as OrchestratorPrivacyClass,
)
from ai_provider import MessageRole, PrivacyClass, ProviderKind

_EXAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "packages"
    / "ai_provider"
    / "examples"
    / "orchestrator_execution_target.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "orchestrator_execution_target_example", _EXAMPLE_PATH
)
assert _SPEC is not None
assert _SPEC.loader is not None
_EXAMPLE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_EXAMPLE)
backend_config_from_execution_target = _EXAMPLE.backend_config_from_execution_target
ai_request_from_prompt = _EXAMPLE.ai_request_from_prompt
prepare_backend_config = _EXAMPLE.prepare_backend_config
prepare_provider_request = _EXAMPLE.prepare_provider_request


def _candidate(
    provider: str = "ollama",
    model: str = "llama3.2",
    location: BackendLocation = BackendLocation.LOCAL,
) -> ModelCatalogEntry:
    access_method = (
        AccessMethod.LOCAL_RUNTIME
        if location is BackendLocation.LOCAL
        else AccessMethod.PROVIDER_API
    )
    auth_method = AuthMethod.NONE if location is BackendLocation.LOCAL else AuthMethod.API_KEY
    billing_source = (
        BillingSource.LOCAL_FREE
        if location is BackendLocation.LOCAL
        else BillingSource.OPENAI_API_BILLING
    )
    cost_policy_tier = (
        CostPolicyTier.LOCAL_ONLY
        if location is BackendLocation.LOCAL
        else CostPolicyTier.BILLING_ALLOWED
    )
    return ModelCatalogEntry(
        backend=ModelBackend(
            route=AccessRoute(
                route_id=f"{provider}-{model}",
                provider=provider,
                product=provider,
                model=model,
                location=location,
                access_method=access_method,
                auth_method=auth_method,
                billing_source=billing_source,
                cost_policy_tier=cost_policy_tier,
                base_url="http://localhost:11434" if provider == "ollama" else None,
            ),
        )
    )


def test_orchestrator_execution_target_can_be_adapted_to_provider_config() -> None:
    target = ExecutionTarget(
        route_id="ollama-llama3.2",
        provider="ollama",
        product="ollama",
        model="llama3.2",
        access_method=AccessMethod.LOCAL_RUNTIME,
        auth_method=AuthMethod.NONE,
        billing_source=BillingSource.LOCAL_FREE,
        cost_policy_tier=CostPolicyTier.LOCAL_ONLY,
        base_url="http://localhost:11434",
        timeout_seconds=15,
    )

    config = backend_config_from_execution_target(target)

    assert config.provider is ProviderKind.OLLAMA
    assert config.model == "llama3.2"
    assert config.base_url == "http://localhost:11434"
    assert config.timeout_seconds == 15


def test_orchestrator_target_adapter_rejects_unknown_provider() -> None:
    target = ExecutionTarget(
        route_id="custom-model",
        provider="custom",
        product="custom",
        model="model",
        access_method=AccessMethod.LOCAL_RUNTIME,
        auth_method=AuthMethod.NONE,
        billing_source=BillingSource.LOCAL_FREE,
        cost_policy_tier=CostPolicyTier.LOCAL_ONLY,
    )

    with pytest.raises(ValueError, match="not supported by ai_provider"):
        backend_config_from_execution_target(target)


def test_orchestrator_target_adapter_rejects_codex_cli_access_method() -> None:
    target = ExecutionTarget(
        route_id="openai-codex-gpt-5.5",
        provider="openai",
        product="codex",
        model="gpt-5.5",
        access_method=AccessMethod.CODEX_CLI,
        auth_method=AuthMethod.CHATGPT_SIGN_IN,
        billing_source=BillingSource.CHATGPT_SUBSCRIPTION_ALLOWANCE,
        cost_policy_tier=CostPolicyTier.ALLOWANCES_ALLOWED,
    )

    with pytest.raises(ValueError, match="Use a dedicated executor"):
        backend_config_from_execution_target(target)


def test_prepare_backend_config_adapts_ready_orchestration_result() -> None:
    result, config = prepare_backend_config(
        "Explain how to run the provider tests as a numbered list with short commands.",
        TaskProfile(),
        (_candidate(),),
        timeout_seconds=15,
    )

    assert result.status is OrchestrationStatus.READY
    assert config is not None
    assert config.provider is ProviderKind.OLLAMA
    assert config.model == "llama3.2"
    assert config.base_url == "http://localhost:11434"
    assert config.timeout_seconds == 15


def test_prepare_backend_config_keeps_advisory_prompt_review_findings() -> None:
    result, config = prepare_backend_config("Fix this", TaskProfile(), (_candidate(),))

    assert result.status is OrchestrationStatus.READY
    assert config is not None


def test_prepare_backend_config_returns_no_config_when_model_selection_fails() -> None:
    result, config = prepare_backend_config(
        "Explain how to run the provider tests as a numbered list with short commands.",
        TaskProfile(),
        (),
    )

    assert result.status is OrchestrationStatus.MODEL_SELECTION_FAILED
    assert config is None


def test_ai_request_from_prompt_uses_provider_request_contract() -> None:
    target = ExecutionTarget(
        route_id="ollama-llama3.2",
        provider="ollama",
        product="ollama",
        model="llama3.2",
        access_method=AccessMethod.LOCAL_RUNTIME,
        auth_method=AuthMethod.NONE,
        billing_source=BillingSource.LOCAL_FREE,
        cost_policy_tier=CostPolicyTier.LOCAL_ONLY,
    )
    config = backend_config_from_execution_target(target)

    request = ai_request_from_prompt(
        "Explain how to run the tests.",
        TaskProfile(privacy_class=OrchestratorPrivacyClass.PUBLIC_OR_LOW_RISK),
        config,
    )

    assert request.model == "llama3.2"
    assert request.privacy_class is PrivacyClass.PUBLIC_OR_LOW_RISK
    assert request.messages[0].role is MessageRole.USER
    assert request.messages[0].content == "Explain how to run the tests."
    assert request.metadata["orchestrator_selected_provider"] == "ollama"
    assert request.metadata["orchestrator_selected_model"] == "llama3.2"


def test_prepare_provider_request_builds_config_and_request_without_execution() -> None:
    result, config, request = prepare_provider_request(
        "Explain how to run the provider tests as a numbered list with short commands.",
        TaskProfile(),
        (_candidate(),),
        timeout_seconds=15,
    )

    assert result.status is OrchestrationStatus.READY
    assert config is not None
    assert request is not None
    assert request.model == config.model
    assert request.messages[0].content == result.original_prompt


def test_prepare_provider_request_keeps_advisory_prompt_review_findings() -> None:
    result, config, request = prepare_provider_request("Fix this", TaskProfile(), (_candidate(),))

    assert result.status is OrchestrationStatus.READY
    assert config is not None
    assert request is not None
