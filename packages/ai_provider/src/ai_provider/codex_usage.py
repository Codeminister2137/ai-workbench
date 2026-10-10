"""Bounded Codex allowance reads via native login; no model turns or saved snapshots."""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import time
from typing import Any

from ai_orchestrator import AccessMethod, ExecutionTarget

from ai_provider.external_agents import external_agent_command
from ai_provider.native_account_usage import read_native_account_usage

MAX_LINE_BYTES = 1_048_576
MAX_RESPONSE_BYTES = 2_097_152


def read_execution_allowance(target: ExecutionTarget) -> dict[str, Any] | None:
    """Compatibility entry point for the provider-neutral account dispatcher."""
    from ai_provider.account_usage import read_execution_allowance as read

    return read(target)


def normalize_rate_limits(result: object) -> list[dict[str, Any]]:
    """Retain separate reported quota windows, omitting account identity and raw fields."""
    if not isinstance(result, dict):
        raise ValueError("Invalid quota response")
    buckets = result.get("rateLimitsByLimitId")
    if buckets is None:
        legacy = result.get("rateLimits")
        if not isinstance(legacy, dict):
            return []
        legacy_id = legacy.get("limitId")
        if legacy_id is not None and not isinstance(legacy_id, str):
            raise ValueError("Invalid quota bucket identity")
        buckets = {legacy_id or "legacy": legacy}
    if not isinstance(buckets, dict) or len(buckets) > 64:
        raise ValueError("Invalid quota buckets")
    windows = []
    for bucket_id, bucket in buckets.items():
        if (
            not isinstance(bucket_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", bucket_id)
            or not isinstance(bucket, dict)
            or bucket.get("limitId") not in (None, bucket_id)
        ):
            raise ValueError("Invalid quota bucket")
        for name in ("primary", "secondary"):
            window = bucket.get(name)
            if window is None:
                continue
            if not isinstance(window, dict):
                raise ValueError("Invalid quota window")
            used = window.get("usedPercent")
            duration = window.get("windowDurationMins")
            reset = window.get("resetsAt")
            if used is not None and (
                type(used) not in (int, float) or not math.isfinite(used) or not 0 <= used <= 100
            ):
                raise ValueError("Invalid quota percentage")
            if duration is not None and (type(duration) is not int or duration <= 0):
                raise ValueError("Invalid quota duration")
            if reset is not None and (type(reset) is not int or not 0 <= reset <= 253402300799):
                raise ValueError("Invalid quota reset")
            windows.append(
                {
                    "bucket_id": bucket_id,
                    "window": name,
                    "used_percent": used,
                    "window_duration_minutes": duration,
                    "resets_at_unix_seconds": reset,
                }
            )
    return windows


def read_codex_allowance(*, timeout_seconds: float = 15) -> dict[str, Any]:
    """Observe account-wide Codex windows through native auth, without model turns."""
    command = external_agent_command(AccessMethod.CODEX_CLI)
    return read_native_account_usage(
        (command, "app-server", "--listen", "stdio://") if command else None,
        source="codex_app_server",
        timeout_seconds=timeout_seconds,
        exchange=_exchange_rate_limits,
    )


def _exchange_rate_limits(process: subprocess.Popen[Any], deadline: float) -> list[dict[str, Any]]:
    """Perform only the app-server handshake and quota RPC."""

    def send(message: dict[str, Any]) -> None:
        if time.monotonic() >= deadline:
            raise TimeoutError("Observation deadline expired")
        assert process.stdin is not None
        process.stdin.write(json.dumps(message).encode() + b"\n")
        process.stdin.flush()

    def receive(expected_id: int) -> object:
        assert process.stdout is not None
        consumed = 0
        for _ in range(64):
            line = process.stdout.readline(MAX_LINE_BYTES + 1)
            consumed += len(line)
            if not line or len(line) > MAX_LINE_BYTES or consumed > MAX_RESPONSE_BYTES:
                raise ValueError("Bounded response unavailable")
            if not line.endswith(b"\n"):
                raise ValueError("Incomplete response")
            message = json.loads(line)
            if not isinstance(message, dict) or message.get("jsonrpc", "2.0") != "2.0":
                raise ValueError("Invalid RPC response")
            if "method" in message:
                if "id" in message:
                    raise ValueError("Unexpected server request")
                continue
            if type(message.get("id")) is not int or message["id"] != expected_id:
                raise ValueError("Unexpected response identity")
            if "error" in message:
                raise ValueError("RPC refused")
            if not isinstance(message.get("result"), dict):
                raise ValueError("Missing response result")
            return message["result"]
        raise ValueError("Notification limit exceeded")

    send(
        {
            "id": 1,
            "method": "initialize",
            "params": {"clientInfo": {"name": "ai_projects_usage", "version": "0.1.0"}},
        }
    )
    receive(1)
    send({"method": "initialized", "params": {}})
    send({"id": 2, "method": "account/rateLimits/read"})
    return normalize_rate_limits(receive(2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-seconds", type=float, default=15)
    args = parser.parse_args(argv)
    try:
        report = read_codex_allowance(timeout_seconds=args.timeout_seconds)
    except ValueError:
        parser.error("Timeout must be finite and between zero and 120 seconds")
    print(json.dumps(report, allow_nan=False))
    return 0 if report["status"] == "available" else 1


if __name__ == "__main__":
    raise SystemExit(main())
