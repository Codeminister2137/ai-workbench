from __future__ import annotations

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
    PrivacyClass,
    QualityThreshold,
    TaskCapability,
    TaskProfile,
    TaskType,
    derive_subtask_profile,
    load_model_catalog,
    plan_delegated_subtask,
    plan_execution,
    recommend_model,
)
from ai_orchestrator.models import LatencyTarget, ModelCatalogEntry, ModelContextLimits


def test_load_model_catalog_reads_toml_entries(tmp_path: Path) -> None:
    catalog_path = tmp_path / "models.toml"
    catalog_path.write_text(
        """
[[models]]
provider = "ollama"
model = "llama3.2"
location = "local"
quality = "standard"
latency = "interactive"
base_url = "http://localhost:11434"

[models.capabilities]
chat = true
structured_output = false

[models.estimate]
typical_latency_seconds = 8
input_cost_per_million_tokens = 0
output_cost_per_million_tokens = 0
source = "local benchmark"
""",
        encoding="utf-8",
    )

    catalog = load_model_catalog(catalog_path)

    assert len(catalog) == 1
    assert catalog[0].backend.provider == "ollama"
    assert catalog[0].backend.route_id == "ollama-llama3-2"
    assert catalog[0].backend.product == "ollama"
    assert catalog[0].backend.model == "llama3.2"
    assert catalog[0].backend.location is BackendLocation.LOCAL
    assert catalog[0].backend.access_method is AccessMethod.LOCAL_RUNTIME
    assert catalog[0].backend.auth_method is AuthMethod.NONE
    assert catalog[0].backend.billing_source is BillingSource.LOCAL_FREE
    assert catalog[0].backend.cost_policy_tier is CostPolicyTier.LOCAL_ONLY
    assert catalog[0].backend.capabilities.chat is True
    assert catalog[0].backend.base_url == "http://localhost:11434"
    assert catalog[0].backend.estimate.typical_latency_seconds == 8
    assert catalog[0].backend.estimate.source == "local benchmark"


def test_load_model_catalog_reads_context_limits(tmp_path: Path) -> None:
    catalog_path = tmp_path / "models.toml"
    catalog_path.write_text(
        """
[[models]]
provider = "ollama"
model = "qwen2.5-coder:14b"
location = "local"

[models.context_limits]
context_window_tokens = 32768
runtime_context_tokens = 4096

[models.metadata]
family = "qwen2"
parameter_size = "14.8B"
quantization_level = "Q4_K_M"
""",
        encoding="utf-8",
    )

    catalog = load_model_catalog(catalog_path)

    assert catalog[0].backend.context_limits == ModelContextLimits(
        context_window_tokens=32768,
        runtime_context_tokens=4096,
    )
    assert catalog[0].metadata["family"] == "qwen2"
    assert catalog[0].metadata["parameter_size"] == "14.8B"


def test_load_model_catalog_defaults_codex_cli_access_metadata(tmp_path: Path) -> None:
    catalog_path = tmp_path / "models.toml"
    catalog_path.write_text(
        """
[[models]]
provider = "openai"
model = "gpt-5.1"
location = "external"
access_method = "codex_cli"
""",
        encoding="utf-8",
    )

    catalog = load_model_catalog(catalog_path)

    assert catalog[0].backend.access_method is AccessMethod.CODEX_CLI
    assert catalog[0].backend.product == "codex"
    assert catalog[0].backend.auth_method is AuthMethod.CHATGPT_SIGN_IN
    assert catalog[0].backend.billing_source is BillingSource.CHATGPT_SUBSCRIPTION_ALLOWANCE
    assert catalog[0].backend.cost_policy_tier is CostPolicyTier.ALLOWANCES_ALLOWED


@pytest.mark.parametrize(
    ("access_method", "product", "auth_method", "billing_source"),
    [
        (
            "copilot_cli",
            "github_copilot",
            AuthMethod.GITHUB_ACCOUNT_SIGN_IN,
            BillingSource.GITHUB_COPILOT_SUBSCRIPTION_ALLOWANCE,
        ),
        (
            "kiro_cli",
            "kiro",
            AuthMethod.KIRO_SIGN_IN,
            BillingSource.KIRO_SUBSCRIPTION_ALLOWANCE,
        ),
    ],
)
def test_load_model_catalog_defaults_external_agent_access_metadata(
    tmp_path: Path,
    access_method: str,
    product: str,
    auth_method: AuthMethod,
    billing_source: BillingSource,
) -> None:
    catalog_path = tmp_path / "models.toml"
    catalog_path.write_text(
        f"""
[[models]]
provider = "{product}"
model = "default"
location = "external"
access_method = "{access_method}"
""",
        encoding="utf-8",
    )

    catalog = load_model_catalog(catalog_path)

    assert catalog[0].backend.product == product
    assert catalog[0].backend.auth_method is auth_method
    assert catalog[0].backend.billing_source is billing_source
    assert catalog[0].backend.cost_policy_tier is CostPolicyTier.ALLOWANCES_ALLOWED


def test_example_model_catalog_includes_coding_mvp_backends() -> None:
    catalog_path = (
        Path(__file__).resolve().parents[1]
        / "packages"
        / "ai_orchestrator"
        / "examples"
        / "model_catalog.toml"
    )

    catalog = load_model_catalog(catalog_path)
    identities = {(entry.backend.provider, entry.backend.model) for entry in catalog}

    assert ("ollama", "deepseek-coder-v2:16b") in identities
    assert ("ollama", "gpt-oss:20b") in identities
    assert ("ollama", "qwen2.5-coder:14b") in identities
    assert ("ollama", "qwen3:14b") in identities
    assert ("openai", "gpt-5.1") in identities
    assert ("openai", "gpt-5-mini") in identities
    assert ("requesty", "openai/gpt-5.1") in identities
    assert ("requesty", "openai/gpt-5-mini") in identities
    assert ("openai", "gpt-5.1") in identities
    route_ids = {entry.backend.route_id for entry in catalog}
    assert "openai-codex-gpt-5-5" in route_ids
    assert "google-antigravity-gemini-3-1-pro" in route_ids
    assert "github-copilot-cli-default" in route_ids
    assert "kiro-cli-default" in route_ids
    assert all(
        entry.backend.estimate.source
        for entry in catalog
        if entry.backend.provider in {"openai", "requesty"}
    )


def test_plan_execution_converts_recommendation_to_neutral_target() -> None:
    candidate = ModelCatalogEntry(
        backend=ModelBackend(
            route=AccessRoute(
                route_id="ollama-llama3-2",
                provider="ollama",
                product="ollama",
                model="llama3.2",
                location=BackendLocation.LOCAL,
                access_method=AccessMethod.LOCAL_RUNTIME,
                auth_method=AuthMethod.NONE,
                billing_source=BillingSource.LOCAL_FREE,
                cost_policy_tier=CostPolicyTier.LOCAL_ONLY,
                base_url="http://localhost:11434",
            ),
            capabilities=ModelCapabilities(),
        ),
        quality=QualityThreshold.STANDARD,
        latency=LatencyTarget.INTERACTIVE,
    )
    recommendation = recommend_model(TaskProfile(), (candidate,))

    plan = plan_execution(TaskProfile(), recommendation, timeout_seconds=10)

    assert plan.target.route_id == "ollama-llama3-2"
    assert plan.target.provider == "ollama"
    assert plan.target.product == "ollama"
    assert plan.target.model == "llama3.2"
    assert plan.target.access_method is AccessMethod.LOCAL_RUNTIME
    assert plan.target.auth_method is AuthMethod.NONE
    assert plan.target.billing_source is BillingSource.LOCAL_FREE
    assert plan.target.cost_policy_tier is CostPolicyTier.LOCAL_ONLY
    assert plan.target.base_url == "http://localhost:11434"
    assert plan.target.timeout_seconds == 10
    assert plan.reasons == recommendation.reasons


def test_plan_execution_allows_targets_outside_ai_provider() -> None:
    candidate = ModelCatalogEntry(
        backend=ModelBackend(
            route=AccessRoute(
                route_id="custom-model",
                provider="custom",
                product="custom",
                model="model",
                location=BackendLocation.LOCAL,
                access_method=AccessMethod.LOCAL_RUNTIME,
                auth_method=AuthMethod.NONE,
                billing_source=BillingSource.LOCAL_FREE,
                cost_policy_tier=CostPolicyTier.LOCAL_ONLY,
            ),
            capabilities=ModelCapabilities(),
        ),
    )
    recommendation = recommend_model(TaskProfile(), (candidate,))

    plan = plan_execution(TaskProfile(), recommendation)

    assert plan.target.provider == "custom"
    assert plan.target.model == "model"


def test_derive_subtask_profile_inherits_parent_privacy_and_defaults_cost_to_local_only() -> None:
    parent = TaskProfile(
        task_type=TaskType.CODING,
        privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        cost_policy_tier=CostPolicyTier.BILLING_ALLOWED,
        quality_threshold=QualityThreshold.HIGH,
        user_model_override="gpt-5.1",
        user_backend_override="openai",
    )

    subtask = derive_subtask_profile(
        parent=parent,
        task_type=TaskType.SUMMARIZATION,
    )

    assert subtask.task_type is TaskType.SUMMARIZATION
    assert subtask.privacy_class is PrivacyClass.EXTERNAL_ALLOWED
    assert subtask.cost_policy_tier is CostPolicyTier.LOCAL_ONLY
    assert subtask.quality_threshold is QualityThreshold.STANDARD
    assert subtask.user_model_override is None
    assert subtask.user_backend_override is None


def test_derive_subtask_profile_accepts_explicit_overrides() -> None:
    parent = TaskProfile(
        task_type=TaskType.CODING,
        privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        cost_policy_tier=CostPolicyTier.BILLING_ALLOWED,
    )

    subtask = derive_subtask_profile(
        parent=parent,
        task_type=TaskType.EXTRACTION,
        privacy_class=PrivacyClass.LOCAL_ONLY,
        cost_policy_tier=CostPolicyTier.ALLOWANCES_ALLOWED,
        quality_threshold=QualityThreshold.LOW,
        required_capabilities=frozenset({TaskCapability.CHAT, TaskCapability.STRUCTURED_OUTPUT}),
        user_model_override="custom-model",
    )

    assert subtask.task_type is TaskType.EXTRACTION
    assert subtask.privacy_class is PrivacyClass.LOCAL_ONLY
    assert subtask.cost_policy_tier is CostPolicyTier.ALLOWANCES_ALLOWED
    assert subtask.quality_threshold is QualityThreshold.LOW
    assert subtask.required_capabilities == frozenset(
        {TaskCapability.CHAT, TaskCapability.STRUCTURED_OUTPUT}
    )
    assert subtask.user_model_override == "custom-model"


def test_plan_delegated_subtask_routes_to_local_candidate() -> None:
    catalog_path = (
        Path(__file__).resolve().parents[1]
        / "packages"
        / "ai_orchestrator"
        / "examples"
        / "model_catalog.toml"
    )
    catalog = load_model_catalog(catalog_path)

    parent_profile = TaskProfile(
        task_type=TaskType.CODING,
        privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        cost_policy_tier=CostPolicyTier.BILLING_ALLOWED,
    )

    delegated = plan_delegated_subtask(
        parent_profile=parent_profile,
        catalog=catalog,
        task_type=TaskType.SUMMARIZATION,
        subtask_id="context-summary",
        description="Summarize large repo context before sending prompt",
    )

    assert delegated.subtask_id == "context-summary"
    assert delegated.description == "Summarize large repo context before sending prompt"
    assert delegated.profile.privacy_class is PrivacyClass.EXTERNAL_ALLOWED
    assert delegated.profile.cost_policy_tier is CostPolicyTier.LOCAL_ONLY
    assert delegated.execution_plan.target.access_method is AccessMethod.LOCAL_RUNTIME
    assert delegated.execution_plan.target.provider == "ollama"
    assert delegated.execution_plan.target.cost_policy_tier is CostPolicyTier.LOCAL_ONLY
