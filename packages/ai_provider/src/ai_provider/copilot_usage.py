"""Read native Copilot quota without model sessions, prompts or credential discovery."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import time
from datetime import datetime
from typing import Any

from ai_orchestrator import AccessMethod

from ai_provider.external_agents import external_agent_command
from ai_provider.native_account_usage import read_native_account_usage


def normalize_quota(result: object) -> list[dict[str, Any]]:
    """Preserve native request units and unlimited sentinel; omit account identifiers."""
    if not isinstance(result, dict):
        raise ValueError("Invalid quota response")
    snapshots = result.get("quotaSnapshots")
    if snapshots is None:
        return []
    if not isinstance(snapshots, dict) or len(snapshots) > 64:
        raise ValueError("Invalid quota snapshots")
    windows = []
    for bucket_id, snapshot in snapshots.items():
        if (
            not isinstance(bucket_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", bucket_id)
            or not isinstance(snapshot, dict)
        ):
            raise ValueError("Invalid quota bucket")
        entitlement = snapshot.get("entitlementRequests")
        used = snapshot.get("usedRequests")
        remaining = snapshot.get("remainingPercentage")
        reset = snapshot.get("resetDate")
        for value, minimum, maximum in (
            (entitlement, -1, None),
            (used, 0, None),
            (remaining, 0, 100),
        ):
            if value is not None and (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or value < minimum
                or (maximum is not None and value > maximum)
            ):
                raise ValueError("Invalid quota measurement")
        if entitlement is not None and -1 < entitlement < 0:
            raise ValueError("Invalid quota entitlement")
        if reset is not None:
            if not isinstance(reset, str) or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})?)?",
                reset,
            ):
                raise ValueError("Invalid quota reset")
            datetime.fromisoformat(reset)
        windows.append(
            {
                "bucket_id": bucket_id,
                "window": "entitlement",
                "entitlement_requests": entitlement,
                "used_requests": used,
                "remaining_percent": remaining,
                "reset_date": reset,
            }
        )
    return windows


def read_copilot_allowance(*, timeout_seconds: float = 15) -> dict[str, Any]:
    """Read account.getQuota with existing global auth; BYOK is not subscription usage."""
    command = external_agent_command(AccessMethod.COPILOT_CLI)
    byok = any(os.getenv(key) for key in ("COPILOT_PROVIDER_BASE_URL", "COPILOT_PROVIDER_API_KEY"))
    report = read_native_account_usage(
        (command, "--headless", "--no-auto-update", "--log-level", "none", "--stdio")
        if command and not byok
        else None,
        source="copilot_account_quota",
        timeout_seconds=timeout_seconds,
        exchange=_exchange_quota,
    )
    if byok:
        report["reason"] = "subscription_billing_overridden"
    return report


def _exchange_quota(process: subprocess.Popen[Any], deadline: float) -> list[dict[str, Any]]:
    return normalize_quota(_exchange_account_result(process, deadline, "account.getQuota"))


def _exchange_account_result(
    process: subprocess.Popen[Any], deadline: float, method: str
) -> dict[str, Any]:
    """Exchange only the two account-only RPCs using the bounded native framing."""
    if method not in {"account.getQuota", "auth.getStatus"}:
        raise ValueError("Unsupported account diagnostic")
    if time.monotonic() >= deadline:
        raise TimeoutError("Observation deadline expired")
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": {}}).encode()
    assert process.stdin is not None and process.stdout is not None
    process.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
    process.stdin.flush()
    consumed = 0
    for _ in range(64):
        header = process.stdout.readline(1025)
        consumed += len(header)
        if not header or len(header) > 1024 or not header.endswith(b"\n"):
            raise ValueError("Invalid quota frame header")
        if not re.fullmatch(rb"Content-Length: [0-9]+\r?\n", header):
            raise ValueError("Invalid quota frame header")
        length = int(header.split(b":", 1)[1])
        if not 0 < length <= 1_048_576 or consumed + length > 2_097_152:
            raise ValueError("Quota frame exceeds bound")
        if process.stdout.readline(3) not in (b"\r\n", b"\n"):
            raise ValueError("Invalid quota frame separator")
        raw = process.stdout.read(length)
        consumed += len(raw)
        if len(raw) != length:
            raise ValueError("Incomplete quota frame")
        response = json.loads(raw)
        if not isinstance(response, dict) or response.get("jsonrpc") != "2.0":
            raise ValueError("Invalid quota RPC response")
        if "method" in response:
            if "id" in response:
                raise ValueError("Unexpected quota server request")
            continue
        if type(response.get("id")) is not int or response["id"] != 1:
            raise ValueError("Invalid quota response identity")
        if "error" in response:
            raise ValueError("Quota RPC refused")
        result = response.get("result")
        if not isinstance(result, dict):
            raise ValueError("Invalid account response result")
        return result
    raise ValueError("Quota notification bound exceeded")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-seconds", type=float, default=15)
    args = parser.parse_args(argv)
    try:
        report = read_copilot_allowance(timeout_seconds=args.timeout_seconds)
    except ValueError:
        parser.error("Timeout must be finite and between zero and 120 seconds")
    print(json.dumps(report, allow_nan=False))
    return 0 if report["status"] == "available" else 1


if __name__ == "__main__":
    raise SystemExit(main())
