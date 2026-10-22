"""OpenRouter per-endpoint availability and performance observations.

Read-only metadata from the public OpenRouter endpoints API
(``GET /api/v1/models/{author}/{slug}/endpoints``). The endpoint reports, per
provider endpoint, the availability signals that decide whether a route can
serve a request now: provider, endpoint tag, reported status, uptime over the
last day and half hour, latency, throughput, quantization, service tier,
context length, prices and supported parameters.

These are source-reported availability observations, not quality judgments. A
healthy endpoint says nothing about how good the model behind it is, and a
quantized endpoint is not the same capability as a full-precision one.

Nothing here sends a prompt, reads a credential file, or infers a value the
source did not report. A model with no advertised endpoint is reported as an
observed empty result, because that absence is itself the finding.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request

from ai_provider.adapters.openrouter import BASE_URL
from ai_provider.http_transport import urlopen
from ai_provider.source_info import EndpointAvailability, EndpointInventory, _utc_now

SOURCE = "openrouter"
_MAX_BYTES = 2_097_152


def _validated_model_id(model_id: str) -> str:
    """Return a model id that can be embedded in the endpoints path."""

    if not isinstance(model_id, str) or not model_id.strip():
        raise ValueError("Model id must be a non-empty string")
    candidate = model_id.strip()
    if candidate.count("/") != 1 or any(character.isspace() for character in candidate):
        raise ValueError("Model id must be '<author>/<slug>'")
    author, slug = candidate.split("/", 1)
    if not author or not slug:
        raise ValueError("Model id must be '<author>/<slug>'")
    return candidate


def _endpoints_url(model_id: str) -> str:
    author, slug = model_id.split("/", 1)
    return f"{BASE_URL}/models/{quote(author, safe='')}/{quote(slug, safe=':')}/endpoints"


def _number(row: dict[str, Any], name: str) -> float | None:
    value = row.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    candidate = float(value)
    return candidate if math.isfinite(candidate) else None


def _positive_int(row: dict[str, Any], name: str) -> int | None:
    value = row.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _text(row: dict[str, Any], name: str) -> str | None:
    value = row.get(name)
    return value if isinstance(value, str) and value else None


def _prices(row: dict[str, Any]) -> dict[str, Any] | None:
    pricing = row.get("pricing")
    if not isinstance(pricing, dict):
        return None
    prices = {
        key: value
        for key, value in pricing.items()
        if isinstance(value, (str, int, float)) and not isinstance(value, bool)
    }
    return prices or None


def _supported_parameters(row: dict[str, Any]) -> tuple[str, ...] | None:
    supported = row.get("supported_parameters")
    if not isinstance(supported, list):
        return None
    return tuple(value for value in supported if isinstance(value, str))


def _parse_endpoint(
    row: object, model_id: str, observed_at_utc: str
) -> EndpointAvailability | None:
    if not isinstance(row, dict):
        return None
    provider = _text(row, "provider_name")
    if provider is None:
        return None
    status = row.get("status")
    return EndpointAvailability(
        source=SOURCE,
        model=model_id,
        provider=provider,
        endpoint=_text(row, "tag"),
        status=status if type(status) is int else None,
        uptime_1d_percent=_number(row, "uptime_last_1d"),
        uptime_30m_percent=_number(row, "uptime_last_30m"),
        latency_seconds=_number(row, "latency_last_30m"),
        throughput_tokens_per_second=_number(row, "throughput_last_30m"),
        quantization=_text(row, "quantization"),
        service_tier=_text(row, "service_tier"),
        context_length=_positive_int(row, "context_length"),
        max_completion_tokens=_positive_int(row, "max_completion_tokens"),
        prices=_prices(row),
        supported_parameters=_supported_parameters(row),
        observed_at_utc=observed_at_utc,
    )


def read_openrouter_endpoint_availability(
    model_id: str, *, api_key: str | None = None, timeout_seconds: float = 15
) -> EndpointInventory:
    """Read the advertised provider endpoints for one OpenRouter model.

    The endpoints API is public, so a credential is optional; when one is
    configured it is sent to the same host that already serves our other
    OpenRouter calls. Credentials come from the caller or the conventional
    process environment; this function never discovers credential files.

    No prompt is sent and no model is called. Socket timeouts bound individual
    I/O; callers own the total process deadline.
    """

    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (float, int))
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise ValueError("Metadata timeout must be finite and positive")
    model = _validated_model_id(model_id)
    if api_key is None:
        api_key = os.getenv("OPENROUTER_API_KEY")

    observed_at = _utc_now()
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(_endpoints_url(model), headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(_MAX_BYTES + 1)
        if len(body) > _MAX_BYTES:
            raise ValueError("Endpoint metadata response exceeded byte bound")
        raw = json.loads(body.decode("utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Invalid endpoint metadata envelope")
        data = raw.get("data")
        if not isinstance(data, dict):
            raise ValueError("Invalid endpoint metadata payload")
        rows = data.get("endpoints")
        if not isinstance(rows, list):
            raise ValueError("Invalid endpoint metadata list")
        endpoints = tuple(
            endpoint
            for endpoint in (_parse_endpoint(row, model, observed_at) for row in rows)
            if endpoint is not None
        )
    except (OSError, ValueError, TypeError) as error:
        reason = "metadata_request_failed"
        if isinstance(error, HTTPError):
            if error.code == 404:
                reason = "model_not_found"
            elif error.code == 401:
                reason = "authentication_failed"
            elif error.code == 403:
                reason = "permission_denied"
        return EndpointInventory(
            status="unavailable",
            source=SOURCE,
            model=model,
            observed_at_utc=observed_at,
            reason=reason,
        )
    return EndpointInventory(
        status="observed",
        source=SOURCE,
        model=model,
        endpoints=endpoints,
        observed_at_utc=observed_at,
        reason=None if endpoints else "no_endpoints_advertised",
    )


def main() -> int:
    """Print closed availability fields only; no credential or raw response output."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", help="OpenRouter model id, for example 'qwen/qwen3.8-27b:free'")
    parser.add_argument("--timeout-seconds", type=float, default=15)
    args = parser.parse_args()
    result = read_openrouter_endpoint_availability(args.model, timeout_seconds=args.timeout_seconds)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.status == "observed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
