"""OpenCode Go on-demand model inventory and account metadata.

Officially supported metadata:

- ``GET https://opencode.ai/inference/go/v1/models`` lists available models.
- Chat usage is returned in Chat Completions responses.
- Go subscription remaining allowance is **not** exposed by an official
  endpoint scoped to the Go inference key. The Console Budgets API covers
  workspace member monetary budgets and requires separate permissions/scope.

This collector therefore reports account allowance as ``unavailable`` rather
than scraping or inferring it from published limits.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request

from ai_provider.contracts import ModelCapabilities, UsageSource
from ai_provider.http_transport import urlopen
from ai_provider.source_info import (
    AccountAllowance,
    ModelInventory,
    ModelInventoryItem,
    SourceInfo,
    _utc_now,
)

GO_INFERENCE_BASE_URL = "https://opencode.ai/inference/go"
GO_CHAT_BASE_URL = "https://opencode.ai/inference/go/openai/v1"


@dataclass(frozen=True, slots=True)
class OpenCodeGoSourceInfo(SourceInfo):
    """Collect OpenCode Go metadata using the official inference endpoints."""

    api_key: str | None = None
    base_url: str = GO_INFERENCE_BASE_URL
    user_agent: str = "ai_projects/0.1.0"

    @property
    def source(self) -> str:
        return "opencode_go"

    @property
    def models_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/v1/models"

    def list_models(
        self,
        *,
        timeout_seconds: float = 15,
    ) -> ModelInventory:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("Metadata timeout must be finite and positive")

        observed_at = _utc_now()
        if not self.api_key:
            return ModelInventory(
                status="unavailable",
                source=self.source,
                observed_at_utc=observed_at,
                reason="credential_not_configured",
            )

        request = Request(
            self.models_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": self.user_agent,
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                body = response.read(2_097_152 + 1)
            if len(body) > 2_097_152:
                raise ValueError("Model metadata response exceeded byte bound")
            raw = json.loads(body.decode("utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("Invalid model metadata envelope")
            data = raw.get("data")
            if not isinstance(data, list):
                raise ValueError("Invalid model metadata list")
            models = tuple(
                _parse_model_row(row, self.source, observed_at_utc=observed_at) for row in data
            )
            return ModelInventory(
                status="observed",
                source=self.source,
                models=models,
                observed_at_utc=observed_at,
            )
        except (OSError, ValueError, TypeError) as error:
            reason = "metadata_request_failed"
            if isinstance(error, HTTPError):
                if error.code == 401:
                    reason = "authentication_failed"
                elif error.code == 403:
                    reason = "permission_denied"
            return ModelInventory(
                status="unavailable",
                source=self.source,
                observed_at_utc=observed_at,
                reason=reason,
            )

    def account_allowance(
        self,
        *,
        timeout_seconds: float = 15,
    ) -> AccountAllowance:
        """Return unavailable because Go does not expose a quota endpoint for the inference key.

        Published monthly/5-hour/weekly dollar limits are not account observations.
        """

        del timeout_seconds  # No network call; parameter kept for interface parity.
        return AccountAllowance(
            status="unavailable",
            source=self.source,
            observed_at_utc=_utc_now(),
            reason="no_official_account_allowance_endpoint_for_go_key",
        )


def read_opencode_go_allowance(
    *, api_key: str | None = None, timeout_seconds: float = 15
) -> dict[str, Any]:
    """Return an explicit unavailable report for Go subscription allowance.

    Go publishes model-specific monthly/5-hour/weekly dollar limits, but it does
    not expose a supported endpoint for the inference key to read remaining
    allowance. This function records that gap rather than inferring a value.
    """

    if api_key is None:
        api_key = os.getenv("OPENCODE_API_KEY")
    return (
        OpenCodeGoSourceInfo(api_key=api_key)
        .account_allowance(timeout_seconds=timeout_seconds)
        .to_dict()
    )


_RESPONSES_MODELS = frozenset(
    {
        "grok-4.6",
        "grok-4.7",
        "gpt-5.6-luna",
        "gpt-6-luna",
        "deepseek-v4.1-flash",
        "deepseek-v4-pro",
        "deepseek-v4-flash",
        "deepseek-v4-flash-vision-exp",
        "muse-spark-1.2-contributor",
        "muse-spark-1.3-contributor",
    }
)

_MESSAGES_MODELS = frozenset(
    {
        "claude-haiku-5-5",
        "minimax-m2.7",
    }
)

_TRAINING_MODELS = frozenset(
    {
        "muse-spark-1.2-contributor",
        "muse-spark-1.3-contributor",
        "gemini-4-argon-contributor",
    }
)

_GLOBAL_REGION_MODELS = frozenset(
    {
        "deepseek-v4.1-flash",
        "deepseek-v4-pro",
        "deepseek-v4-flash",
        "deepseek-v4-flash-vision-exp",
    }
)


def _model_protocol(model_id: str) -> str:
    if model_id in _RESPONSES_MODELS:
        return "responses"
    if model_id in _MESSAGES_MODELS:
        return "messages"
    return "chat"


def _parse_model_row(row: object, source: str, observed_at_utc: str) -> ModelInventoryItem:
    if not isinstance(row, dict):
        row = {}
    model_id = row.get("id")
    if not isinstance(model_id, str):
        model_id = "unknown"

    capabilities = None
    supported = row.get("supported_parameters")
    if isinstance(supported, list):
        capabilities = ModelCapabilities(
            chat=True,
            streaming="stream" in supported or "streaming" in supported,
            tools="tools" in supported,
            structured_output="structured_output" in supported or "response_format" in supported,
            multimodal_input="vision" in supported or "images" in supported,
        )

    context_window = row.get("context_window")
    context_window_tokens: int | None = None
    if isinstance(context_window, int | float) and not isinstance(context_window, bool):
        if context_window > 0:
            context_window_tokens = int(context_window)

    prices: dict[str, Any] | None = None
    pricing = row.get("pricing")
    if isinstance(pricing, dict):
        prices = {
            key: value
            for key, value in pricing.items()
            if isinstance(value, (str, int, float)) and not isinstance(value, bool)
        }
        if not prices:
            prices = None

    protocol = _model_protocol(model_id)
    endpoint = {
        "responses": f"{GO_INFERENCE_BASE_URL}/v1/responses",
        "messages": f"{GO_INFERENCE_BASE_URL}/v1/messages",
    }.get(protocol, f"{GO_CHAT_BASE_URL}/chat/completions")
    return ModelInventoryItem(
        id=model_id,
        source=source,
        endpoint=endpoint,
        capabilities=capabilities,
        context_window_tokens=context_window_tokens,
        prices=prices,
        observed_at_utc=observed_at_utc,
        protocol=protocol,
        trains_on_request_data=model_id in _TRAINING_MODELS,
        requires_global_regions=model_id in _GLOBAL_REGION_MODELS,
    )


def usage_from_response(raw_response: dict[str, Any]) -> dict[str, Any]:
    """Extract provider-reported usage from a Go Chat Completions response.

    This mirrors the normalization in ``openai_compatible`` but keeps the
    source label explicit for Go.
    """

    raw_usage = raw_response.get("usage")
    if not isinstance(raw_usage, dict):
        return {
            "source": "opencode_go",
            "usage_source": UsageSource.UNAVAILABLE.value,
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "reported_cost_usd": None,
        }

    def int_token(name: str) -> int | None:
        value = raw_usage.get(name)
        return value if type(value) is int and value >= 0 else None

    cost = raw_usage.get("cost")
    reported_cost = None
    if isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= 0:
        try:
            candidate = float(cost)
            if math.isfinite(candidate):
                reported_cost = candidate
        except OverflowError:
            pass

    return {
        "source": "opencode_go",
        "usage_source": UsageSource.PROVIDER_REPORTED.value,
        "input_tokens": int_token("prompt_tokens"),
        "output_tokens": int_token("completion_tokens"),
        "total_tokens": int_token("total_tokens"),
        "reported_cost_usd": reported_cost,
    }


def _probe_model(
    model_id: str,
    *,
    api_key: str,
    prompt: str,
    max_output_tokens: int,
    timeout_seconds: float,
) -> dict[str, object]:
    """Send one minimal public/synthetic request to one Go model.

    Returns a sanitized result with status, latency, usage and error category.
    No prompt content or raw errors are emitted.
    """

    from uuid import uuid4

    from ai_provider import (
        AIMessage,
        AIRequest,
        BackendConfig,
        MessageRole,
        PrivacyClass,
        ProviderKind,
        create_chat_client,
    )
    from ai_provider.errors import ProviderError

    started = time.perf_counter()
    try:
        client = create_chat_client(
            BackendConfig(
                provider=ProviderKind.OPENCODE_GO,
                model=model_id,
                api_key=api_key,
                timeout_seconds=timeout_seconds,
            )
        )
        request = AIRequest(
            messages=(AIMessage(MessageRole.USER, prompt),),
            privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
            metadata={"public_or_synthetic": True, "opencode_session": uuid4().hex},
            max_output_tokens=max_output_tokens,
        )
        response = client.complete(request)
        return {
            "model": model_id,
            "status": "ok",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.total_tokens,
            "finish_reason": response.finish_reason.value,
        }
    except ProviderError as error:
        return {
            "model": model_id,
            "status": "error",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "error_category": error.category.value,
            "retryable": error.retryable,
        }
    except (OSError, TimeoutError, ValueError) as error:
        return {
            "model": model_id,
            "status": "error",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "error_category": type(error).__name__,
            "retryable": False,
        }


def _select_probe_models(inventory: ModelInventory, selector: str) -> list[str]:
    if selector == "all":
        return [model.id for model in inventory.models]
    if selector == "free":
        return [model.id for model in inventory.models if model.id.endswith("-free")]
    return [model_id.strip() for model_id in selector.split(",") if model_id.strip()]


def main(argv: list[str] | None = None) -> int:
    """Print closed Go model metadata; never emit the API key.

    With --probe-models, sends one minimal request per selected model to verify
    access. Use --probe-models=free for a zero-cost smoke test, or pass a
    comma-separated list to target specific models.
    """

    import argparse
    import os

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--timeout-seconds", type=float, default=15)
    parser.add_argument("--probe-models", default=None)
    parser.add_argument("--probe-prompt", default="Say hello in one sentence.")
    parser.add_argument("--probe-max-tokens", type=int, default=8)
    args = parser.parse_args(argv)

    api_key = args.api_key if args.api_key is not None else os.getenv("OPENCODE_API_KEY")
    collector = OpenCodeGoSourceInfo(api_key=api_key)
    inventory = collector.list_models(timeout_seconds=args.timeout_seconds)
    allowance = collector.account_allowance(timeout_seconds=args.timeout_seconds)
    result: dict[str, object] = {
        "models": inventory.to_dict(),
        "allowance": allowance.to_dict(),
    }
    if args.probe_models and inventory.status == "observed":
        selected = _select_probe_models(inventory, args.probe_models)
        result["probes"] = [
            _probe_model(
                model_id,
                api_key=api_key or "",
                prompt=args.probe_prompt,
                max_output_tokens=args.probe_max_tokens,
                timeout_seconds=args.timeout_seconds,
            )
            for model_id in selected
        ]
        result["probe_summary"] = {
            "selected": len(selected),
            "ok": sum(1 for probe in result["probes"] if probe["status"] == "ok"),
            "error": sum(1 for probe in result["probes"] if probe["status"] == "error"),
        }
    print(json.dumps(result, indent=2))
    return 0 if inventory.status == "observed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
