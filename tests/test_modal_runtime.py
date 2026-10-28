"""Offline contracts for the Modal runtime adapter."""

from __future__ import annotations

import pytest
from ai_orchestrator import ExecutionTarget, load_model_catalog, recommend_model
from ai_orchestrator.models import (
    AccessMethod,
    BillingSource,
    CostPolicyTier,
    PrivacyClass,
    QualityThreshold,
    TaskCapability,
    TaskProfile,
    TaskType,
)
from ai_provider.adapters.modal import ModalRuntimeChatClient
from ai_provider.coding_assist import backend_config_from_execution_target
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.errors import ProviderError
from ai_provider.factory import create_chat_client

CATALOG = "packages/ai_orchestrator/examples/model_catalog.toml"


def test_access_method_and_billing_source_exist() -> None:
    assert AccessMethod.MODAL_RUNTIME.value == "modal_runtime"
    assert BillingSource.MODAL_TOKEN_BILLING.value == "modal_token_billing"
    assert BillingSource.MODAL_RUNTIME_BILLING.value == "modal_runtime_billing"


def test_provider_kind_exists() -> None:
    assert ProviderKind.MODAL.value == "modal"


def test_factory_creates_modal_client() -> None:
    config = BackendConfig(
        provider=ProviderKind.MODAL,
        model="Qwen/Qwen2.5-Coder-7B-Instruct",
        base_url="https://owner--modal.modal.run/v1",
        api_key="test-key",
    )
    client = create_chat_client(config)
    assert isinstance(client, ModalRuntimeChatClient)
    assert client.backend.provider == "modal"
    assert client.backend.capabilities.tools is True
    assert client.base_url == "https://owner--modal.modal.run/v1"


def test_modal_client_requires_base_url() -> None:
    config = BackendConfig(
        provider=ProviderKind.MODAL,
        model="Qwen/Qwen2.5-Coder-7B-Instruct",
        api_key="test-key",
    )
    client = create_chat_client(config)
    with pytest.raises(ProviderError, match="base_url"):
        _ = client.base_url


def test_backend_config_from_execution_target_accepts_modal_runtime() -> None:
    target = ExecutionTarget(
        route_id="modal/qwen/qwen2.5-coder-7b-instruct",
        provider="modal",
        product="modal",
        model="Qwen/Qwen2.5-Coder-7B-Instruct",
        access_method=AccessMethod.MODAL_RUNTIME,
        auth_method="api_key",
        billing_source=BillingSource.MODAL_RUNTIME_BILLING,
        cost_policy_tier=CostPolicyTier.PREPAID_CREDITS_ALLOWED,
        base_url="https://owner--modal.modal.run/v1",
        timeout_seconds=60.0,
    )
    config = backend_config_from_execution_target(target)
    assert config.provider is ProviderKind.MODAL
    assert config.model == "Qwen/Qwen2.5-Coder-7B-Instruct"


def test_catalog_selects_modal_route_with_tools() -> None:
    catalog = load_model_catalog(CATALOG)
    profile = TaskProfile(
        task_type=TaskType.CODING,
        privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        required_capabilities=frozenset({TaskCapability.CHAT, TaskCapability.TOOLS}),
        quality_threshold=QualityThreshold.STANDARD,
        latency_target="interactive",
        max_expected_latency_seconds=None,
        cost_policy_tier=CostPolicyTier.PREPAID_CREDITS_ALLOWED,
        user_route_id_override="modal/qwen/qwen2.5-coder-7b-instruct",
        user_access_method_override=None,
        user_backend_override=None,
        user_model_override=None,
    )
    selected = recommend_model(profile, catalog).selected
    assert selected.backend.route_id == "modal/qwen/qwen2.5-coder-7b-instruct"
