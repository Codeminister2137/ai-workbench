"""Sanitized OpenRouter account observations without model inference."""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request

from ai_provider.adapters.openrouter import BASE_URL, _free_pricing
from ai_provider.http_transport import urlopen


def _quota(data: dict[str, Any]) -> dict[str, int] | None:
    counter = data.get("free_model_daily_requests")
    if not isinstance(counter, dict):
        return None
    values: dict[str, int] = {}
    for name in ("used", "limit", "remaining"):
        value = counter.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return None
        values[name] = value
    if values["used"] + values["remaining"] != values["limit"]:
        return None
    return values


def read_openrouter_allowance(
    *, api_key: str | None = None, timeout_seconds: float = 15, include_models: bool = False
) -> dict[str, Any]:
    """GET quota and optionally account-visible free models; never send a prompt.

    Credentials come from the caller or the conventional process environment.
    Entrypoints may use the existing ``uv --env-file`` bootstrap. This function
    does not discover credential files, change account settings or retry errors.
    Socket timeouts bound individual I/O; callers own the total process deadline.
    Availability and zero advertised prices are observations, not live admission.
    """
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (float, int))
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise ValueError("Metadata timeout must be finite and positive")
    result: dict[str, Any] = {
        "source": "openrouter_api",
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "completion_requests": 0,
        "checks": [],
    }
    key = api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY")
    if not key:
        return {**result, "status": "unavailable", "reason": "credential_not_configured"}
    paths = ("key", "models/user") if include_models else ("key",)
    for path in paths:
        check: dict[str, Any] = {"path": path, "method": "GET"}
        result["checks"].append(check)
        try:
            request = Request(
                f"{BASE_URL}/{path}",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                },
                method="GET",
            )
            byte_limit = 65_536 if path == "key" else 2_097_152
            with urlopen(request, timeout=timeout_seconds) as response:
                body = response.read(byte_limit + 1)
                check["http_status"] = response.status
                age = response.headers.get("Age", "0")
                check["cached"] = (
                    response.headers.get("CF-Cache-Status", "").upper() == "HIT"
                    or not age.isdigit()
                    or int(age) != 0
                )
            if len(body) > byte_limit:
                raise ValueError("Metadata response exceeded byte bound")
            raw = json.loads(body)
            if not isinstance(raw, dict):
                raise ValueError("Invalid metadata envelope")
            data = raw.get("data")
            if path == "key":
                if not isinstance(data, dict):
                    raise ValueError("Invalid account metadata")
                check["is_free_tier"] = (
                    data.get("is_free_tier") if type(data.get("is_free_tier")) is bool else None
                )
                check["free_model_daily_requests"] = None if check["cached"] else _quota(data)
            else:
                if not isinstance(data, list):
                    raise ValueError("Invalid model metadata")
                check["free_models"] = [
                    {
                        "id": row["id"],
                        "tools": "tools" in row.get("supported_parameters", []),
                    }
                    for row in data
                    if isinstance(row, dict)
                    and isinstance(row.get("id"), str)
                    and row["id"].endswith(":free")
                    and _free_pricing(row.get("pricing"))
                    and isinstance(row.get("supported_parameters", []), list)
                ]
        except (OSError, ValueError, TypeError) as error:
            check.update(
                failure_kind=type(error).__name__,
                http_status=error.code
                if isinstance(error, HTTPError)
                else check.get("http_status"),
            )
            return {**result, "status": "unavailable", "reason": "metadata_request_failed"}
    return {**result, "status": "observed"}


def main() -> int:
    """Print closed metadata fields only; no credential or raw response output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-models", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=15)
    args = parser.parse_args()
    result = read_openrouter_allowance(
        timeout_seconds=args.timeout_seconds, include_models=args.include_models
    )
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "observed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
