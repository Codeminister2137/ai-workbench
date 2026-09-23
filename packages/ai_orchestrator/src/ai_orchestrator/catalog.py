"""Load and validate model catalog entries from structured configuration."""

from __future__ import annotations

import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ai_orchestrator.models import (
    AccessMethod,
    AccessRoute,
    AuthMethod,
    BackendLocation,
    BillingSource,
    CostPolicyTier,
    LatencyTarget,
    ModelBackend,
    ModelCapabilities,
    ModelCatalogEntry,
    ModelContextLimits,
    ModelPerformanceEstimate,
    QualityThreshold,
)


def load_model_catalog(path: Path | str) -> tuple[ModelCatalogEntry, ...]:
    """Load, validate, and convert a TOML model catalog into typed entries."""

    catalog_path = Path(path)
    if not catalog_path.is_file():
        raise FileNotFoundError(f"Model catalog file not found: {catalog_path}")

    raw = tomllib.loads(catalog_path.read_text(encoding="utf-8"))
    entries = raw.get("models")
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        raise ValueError("Model catalog must define a top-level 'models' array.")

    return tuple(_parse_entry(item) for item in entries)


def _parse_entry(item: object) -> ModelCatalogEntry:
    if not isinstance(item, dict):
        raise ValueError("Each model catalog entry must be a TOML table.")

    provider = _required_string(item, "provider")
    model = _required_string(item, "model")
    location = BackendLocation(_required_string(item, "location"))
    access_method = AccessMethod(
        _optional_string(item, "access_method", default=_default_access_method(location))
    )
    route_id = _optional_string(
        item,
        "route_id",
        default=_default_route_id(provider, model),
    )
    product = _optional_string(
        item,
        "product",
        default=_default_product(provider, access_method),
    )
    auth_method = AuthMethod(
        _optional_string(
            item,
            "auth_method",
            default=_default_auth_method(provider, access_method),
        )
    )
    billing_source = BillingSource(
        _optional_string(
            item,
            "billing_source",
            default=_default_billing_source(provider, access_method),
        )
    )
    cost_policy_tier = CostPolicyTier(
        _optional_string(
            item,
            "cost_policy_tier",
            default=_default_cost_policy_tier(location, billing_source),
        )
    )
    quality = QualityThreshold(str(item.get("quality", QualityThreshold.STANDARD.value)))
    latency = LatencyTarget(str(item.get("latency", LatencyTarget.INTERACTIVE.value)))
    base_url = item.get("base_url")
    notes = item.get("notes")
    capabilities = _capabilities(item.get("capabilities", {}))
    context_limits = _context_limits(item.get("context_limits", {}))
    estimate = _estimate(item.get("estimate", {}))
    metadata = _metadata(item.get("metadata", {}))

    return ModelCatalogEntry(
        backend=ModelBackend(
            route=AccessRoute(
                route_id=route_id,
                provider=provider,
                product=product,
                model=model,
                location=location,
                access_method=access_method,
                auth_method=auth_method,
                billing_source=billing_source,
                cost_policy_tier=cost_policy_tier,
                base_url=base_url if isinstance(base_url, str) else None,
            ),
            capabilities=capabilities,
            context_limits=context_limits,
            estimate=estimate,
        ),
        quality=quality,
        latency=latency,
        notes=notes if isinstance(notes, str) else None,
        metadata=metadata,
    )


def _required_string(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Model catalog entry must define a non-empty {key!r}.")
    return value.strip()


def _optional_string(item: dict[str, Any], key: str, *, default: str) -> str:
    value = item.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Model catalog entry {key!r} must be a non-empty string.")
    return value.strip()


def _default_route_id(provider: str, model: str) -> str:
    normalized_model = (
        model.lower().replace(":", "-").replace("/", "-").replace(".", "-").replace("_", "-")
    )
    return f"{provider.lower()}-{normalized_model}"


def _default_access_method(location: BackendLocation) -> str:
    if location is BackendLocation.LOCAL:
        return AccessMethod.LOCAL_RUNTIME.value
    return AccessMethod.PROVIDER_API.value


def _default_product(provider: str, access_method: AccessMethod) -> str:
    if access_method is AccessMethod.CODEX_CLI:
        return "codex"
    if access_method is AccessMethod.ANTIGRAVITY_CLI:
        return "antigravity"
    if access_method is AccessMethod.PROVIDER_API and provider == "openai":
        return "openai_api"
    if access_method is AccessMethod.PROVIDER_API and provider in {"google", "gemini"}:
        return "google_ai_studio"
    return provider


def _default_auth_method(provider: str, access_method: AccessMethod) -> str:
    if access_method is AccessMethod.LOCAL_RUNTIME:
        return AuthMethod.NONE.value
    if access_method is AccessMethod.CODEX_CLI:
        return AuthMethod.CHATGPT_SIGN_IN.value
    if access_method is AccessMethod.ANTIGRAVITY_CLI:
        return AuthMethod.GOOGLE_ACCOUNT_SIGN_IN.value
    return AuthMethod.API_KEY.value


def _default_billing_source(provider: str, access_method: AccessMethod) -> str:
    if access_method is AccessMethod.LOCAL_RUNTIME:
        return BillingSource.LOCAL_FREE.value
    if access_method is AccessMethod.CODEX_CLI:
        return BillingSource.CHATGPT_SUBSCRIPTION_ALLOWANCE.value
    if access_method is AccessMethod.ANTIGRAVITY_CLI:
        return BillingSource.ANTIGRAVITY_SUBSCRIPTION_ALLOWANCE.value
    if provider == "requesty":
        return BillingSource.REQUESTY_BILLING.value
    if provider in {"google", "gemini"}:
        return BillingSource.GOOGLE_AI_STUDIO_FREE.value
    if provider == "openai":
        return BillingSource.OPENAI_API_BILLING.value
    return BillingSource.OPENAI_API_BILLING.value


def _default_cost_policy_tier(
    location: BackendLocation,
    billing_source: BillingSource,
) -> str:
    if location is BackendLocation.LOCAL or billing_source is BillingSource.LOCAL_FREE:
        return CostPolicyTier.LOCAL_ONLY.value
    if billing_source is BillingSource.GOOGLE_AI_STUDIO_FREE:
        return CostPolicyTier.FREE_ONLY.value
    if billing_source in {
        BillingSource.CHATGPT_SUBSCRIPTION_ALLOWANCE,
        BillingSource.CHATGPT_WORKSPACE_CREDITS,
        BillingSource.ANTIGRAVITY_SUBSCRIPTION_ALLOWANCE,
    }:
        return CostPolicyTier.ALLOWANCES_ALLOWED.value
    if billing_source is BillingSource.REQUESTY_BILLING:
        return CostPolicyTier.PREPAID_CREDITS_ALLOWED.value
    return CostPolicyTier.BILLING_ALLOWED.value


def _capabilities(raw: object) -> ModelCapabilities:
    if not isinstance(raw, dict):
        raise ValueError("Model capabilities must be a table.")

    return ModelCapabilities(
        chat=_bool(raw, "chat", default=True),
        streaming=_bool(raw, "streaming", default=False),
        tools=_bool(raw, "tools", default=False),
        structured_output=_bool(raw, "structured_output", default=False),
        multimodal_input=_bool(raw, "multimodal_input", default=False),
        embeddings=_bool(raw, "embeddings", default=False),
    )


def _bool(raw: dict[str, Any], key: str, *, default: bool) -> bool:
    value = raw.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"Capability {key!r} must be a boolean.")
    return value


def _estimate(raw: object) -> ModelPerformanceEstimate:
    if not isinstance(raw, dict):
        raise ValueError("Model estimate must be a table.")

    return ModelPerformanceEstimate(
        typical_latency_seconds=_optional_float(raw, "typical_latency_seconds"),
        input_cost_per_million_tokens=_optional_float(raw, "input_cost_per_million_tokens"),
        output_cost_per_million_tokens=_optional_float(raw, "output_cost_per_million_tokens"),
        source=_optional_nullable_string(raw, "source"),
        source_url=_optional_nullable_string(raw, "source_url"),
    )


def _context_limits(raw: object) -> ModelContextLimits:
    if not isinstance(raw, dict):
        raise ValueError("Model context_limits must be a table.")

    return ModelContextLimits(
        context_window_tokens=_optional_positive_int(raw, "context_window_tokens"),
        runtime_context_tokens=_optional_positive_int(raw, "runtime_context_tokens"),
    )


def _metadata(raw: object) -> dict[str, str | int | float | bool]:
    if not isinstance(raw, dict):
        raise ValueError("Model metadata must be a table.")
    metadata: dict[str, str | int | float | bool] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, (str, int, float, bool)):
            raise ValueError("Model metadata values must be scalar TOML values.")
        metadata[key] = value
    return metadata


def _optional_float(raw: dict[str, Any], key: str) -> float | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        raise ValueError(f"Estimate {key!r} must be a number.")
    return float(value)


def _optional_positive_int(raw: dict[str, Any], key: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"Context limit {key!r} must be a positive integer.")
    return value


def _optional_nullable_string(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Estimate {key!r} must be a non-empty string when present.")
    return value.strip()
