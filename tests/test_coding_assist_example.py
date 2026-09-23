from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from ai_orchestrator import (
    AccessMethod,
    AccessRoute,
    AuthMethod,
    BackendLocation,
    BillingSource,
    CostPolicyTier,
    ModelBackend,
    ModelCapabilities,
    ModelCatalogEntry,
    ModelPerformanceEstimate,
    PrivacyClass,
    QualityThreshold,
)
from ai_provider import (
    AIMessage,
    AIRequest,
    AIResponse,
    BackendInfo,
    MessageRole,
    ProviderKind,
)
from ai_provider import (
    BackendLocation as ProviderBackendLocation,
)

_EXAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "packages"
    / "ai_provider"
    / "examples"
    / ("coding_assist.py")
)
_SPEC = importlib.util.spec_from_file_location("coding_assist_example", _EXAMPLE_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_EXAMPLE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _EXAMPLE
_SPEC.loader.exec_module(_EXAMPLE)
coding_task_profile = _EXAMPLE.coding_task_profile
run_coding_prompt = _EXAMPLE.run_coding_prompt


class FakeClient:
    def __init__(self) -> None:
        self.requests: list[AIRequest] = []

    @property
    def backend(self) -> BackendInfo:
        return BackendInfo(
            provider="ollama",
            model="llama3.2",
            location=ProviderBackendLocation.LOCAL,
        )

    def complete(self, request: AIRequest) -> AIResponse:
        self.requests.append(request)
        return AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, "coding answer"),
            backend=self.backend,
        )

    def stream(self, request: AIRequest):
        raise NotImplementedError


def _candidate(
    provider: str = "ollama",
    model: str = "llama3.2",
    location: BackendLocation = BackendLocation.LOCAL,
    *,
    quality: QualityThreshold = QualityThreshold.STANDARD,
) -> ModelCatalogEntry:
    access_method = (
        AccessMethod.LOCAL_RUNTIME
        if location is BackendLocation.LOCAL
        else AccessMethod.PROVIDER_API
    )
    auth_method = AuthMethod.NONE if location is BackendLocation.LOCAL else AuthMethod.API_KEY
    if location is BackendLocation.LOCAL:
        billing_source = BillingSource.LOCAL_FREE
        cost_policy_tier = CostPolicyTier.LOCAL_ONLY
    elif provider == "requesty":
        billing_source = BillingSource.REQUESTY_BILLING
        cost_policy_tier = CostPolicyTier.ALLOWANCES_ALLOWED
    else:
        billing_source = BillingSource.OPENAI_API_BILLING
        cost_policy_tier = CostPolicyTier.BILLING_ALLOWED
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
            ),
            capabilities=ModelCapabilities(chat=True, streaming=True),
            estimate=ModelPerformanceEstimate(
                typical_latency_seconds=10,
                input_cost_per_million_tokens=0,
                output_cost_per_million_tokens=0,
                source="test",
            ),
        ),
        quality=quality,
    )


def test_run_coding_prompt_prepares_request_without_execution() -> None:
    profile = coding_task_profile()

    result = run_coding_prompt(
        "Explain the failing test and suggest a minimal fix.",
        profile,
        (_candidate(),),
    )

    assert result.response is None
    assert result.config is not None
    assert result.config.provider is ProviderKind.OLLAMA
    assert result.request is not None
    assert result.request.messages == (
        AIMessage(MessageRole.USER, "Explain the failing test and suggest a minimal fix."),
    )
    assert result.request.metadata["task_type"] == "coding"


def test_run_coding_prompt_can_include_system_prompt() -> None:
    profile = coding_task_profile()

    result = run_coding_prompt(
        "Explain the failing test and suggest a minimal fix.",
        profile,
        (_candidate(),),
        system_prompt="Be concise and preserve user intent.",
    )

    assert result.request is not None
    assert result.request.messages == (
        AIMessage(MessageRole.SYSTEM, "Be concise and preserve user intent."),
        AIMessage(MessageRole.USER, "Explain the failing test and suggest a minimal fix."),
    )


def test_run_coding_prompt_executes_with_injected_client() -> None:
    client = FakeClient()
    profile = coding_task_profile()

    result = run_coding_prompt(
        "Explain the failing test and suggest a minimal fix.",
        profile,
        (_candidate(),),
        execute=True,
        client_factory=lambda config: client,
    )

    assert result.response is not None
    assert result.response.message.content == "coding answer"
    assert client.requests[0].model == "llama3.2"


def test_run_coding_prompt_can_start_ollama_before_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient()
    profile = coding_task_profile()
    calls: list[tuple[str | None, str, float]] = []

    monkeypatch.setattr(
        _EXAMPLE,
        "ensure_ollama_server",
        lambda base_url, *, command, startup_timeout_seconds: calls.append(
            (base_url, command, startup_timeout_seconds)
        ),
    )

    result = run_coding_prompt(
        "Explain the failing test and suggest a minimal fix.",
        profile,
        (_candidate(),),
        execute=True,
        start_ollama=True,
        ollama_command="ollama-test",
        ollama_startup_timeout_seconds=3.0,
        client_factory=lambda config: client,
    )

    assert result.response is not None
    assert calls == [(None, "ollama-test", 3.0)]


def test_run_coding_prompt_keeps_local_only_profile_off_external_backend() -> None:
    external = _candidate("openai", "gpt-5.1", BackendLocation.EXTERNAL)
    profile = coding_task_profile(privacy_class=PrivacyClass.LOCAL_ONLY)

    result = run_coding_prompt(
        "Explain the failing test and suggest a minimal fix.",
        profile,
        (external,),
    )

    assert result.config is None
    assert result.orchestration.failure_reason is not None
    assert "local-only" in result.orchestration.failure_reason
