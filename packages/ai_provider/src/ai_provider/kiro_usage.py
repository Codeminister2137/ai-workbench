"""Read Kiro V2 plan credits in a temporary tool-free quota session.

Only the inspected 2.24.0 client is admitted. Other versions remain unknown until
their profile, hook and slash-command isolation contracts are verified.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any

from ai_orchestrator import AccessMethod

from ai_provider.external_agents import external_agent_command
from ai_provider.native_account_usage import read_native_account_usage

SOURCE = "kiro_isolated_v2_usage"
VERIFIED_VERSION = "kiro-cli-chat 2.24.0"
MAX_OUTPUT_BYTES = 65536
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def normalize_usage(text: str) -> list[dict[str, Any]]:
    """Keep native plan-covered credit units; never infer a remaining balance.

    The native percentage is retained as reported, without claiming whether it is
    used/remaining. Reset dates have no invented timezone. Additional credit packs,
    organization plans and changed output formats require separate compatibility.
    """
    text = ANSI.sub("", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if (
        len(lines) != 3
        or re.fullmatch(r"[A-Za-z ]+https://app\.kiro\.dev/account/usage", lines[2]) is None
    ):
        raise ValueError("Unsupported quota output")
    header = re.fullmatch(
        r"Estimated Usage \| resets on (\d{4}-\d{2}-\d{2}) \| KIRO [A-Z_]+",
        lines[0],
    )
    credits = re.fullmatch(
        r"Credits \(([0-9]+(?:\.[0-9]+)?) of ([0-9]+(?:\.[0-9]+)?) covered in plan\), "
        r"([0-9]+(?:\.[0-9]+)?)%",
        lines[1],
    )
    if header is None or credits is None:
        raise ValueError("Unsupported quota output")
    reset = header[1]
    date.fromisoformat(reset)
    covered, entitlement, percent = (float(value) for value in credits.groups())
    if not all(math.isfinite(value) and value >= 0 for value in (covered, entitlement, percent)):
        raise ValueError("Invalid credit measurement")
    if percent > 100 or covered > entitlement:
        raise ValueError("Invalid credit measurement")
    return [
        {
            "bucket_id": "plan_credits",
            "window": "subscription",
            "measurement_kind": "native_estimate",
            "covered_credits": covered,
            "plan_credits": entitlement,
            "reported_percent": percent,
            "reset_date": reset,
        }
    ]


def _read_output(process: subprocess.Popen[Any], deadline: float) -> str:
    assert process.stdin is not None and process.stdout is not None
    process.stdin.close()  # No follow-up text, approval answers or model prompts.
    payload = process.stdout.read(MAX_OUTPUT_BYTES + 1)
    if time.monotonic() >= deadline:
        raise TimeoutError("Observation expired")
    if len(payload) > MAX_OUTPUT_BYTES:
        raise ValueError("Quota output exceeded bound")
    try:
        returncode = process.wait(timeout=max(0.001, deadline - time.monotonic()))
    except subprocess.TimeoutExpired as error:
        raise TimeoutError("Observation expired") from error
    if returncode != 0:
        raise ValueError("Native quota command failed")
    return payload.decode("utf-8")


def read_kiro_allowance(*, timeout_seconds: float = 15) -> dict[str, Any]:
    """Prove the admitted version/profile boundary before a single quota session."""
    command = external_agent_command(AccessMethod.KIRO_CLI)
    report = read_native_account_usage(
        None,
        source=SOURCE,
        timeout_seconds=timeout_seconds,
        exchange=_exchange_usage,
    )
    if command is None:
        return report
    deadline = time.monotonic() + timeout_seconds
    env = {**os.environ, "KIRO_NO_AUTO_UPDATE": "1"}
    try:
        with tempfile.TemporaryDirectory(prefix="ai-kiro-quota-") as temporary:
            directory = Path(temporary).resolve()
            # TEMP overrides and directory links must not inherit a repository.
            if any(
                (parent / marker).exists()
                for parent in (directory, *directory.parents)
                for marker in (".git", "AGENTS.md", "CURRENT_CONTEXT.md")
            ):
                report["reason"] = "isolation_unverified"
                return report
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                report["reason"] = "timeout"
                return report
            version = read_native_account_usage(
                (command, "--version"),
                source=SOURCE,
                timeout_seconds=remaining,
                exchange=_exchange_version,
                cwd=directory,
                env=env,
            )
            if not version["cleanup_verified"]:
                return version
            if version["status"] != "available":
                version["reason"] = "client_version_unverified"
                return version
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                report["reason"] = "timeout"
                return report
            name = directory.name
            agent = directory / ".kiro" / "agents" / f"{name}.json"
            agent.parent.mkdir(parents=True)
            agent.write_text(
                json.dumps(
                    {
                        "name": name,
                        "prompt": "",
                        "tools": [],
                        "allowedTools": [],
                        "resources": [],
                        "hooks": {},
                        "mcpServers": {},
                        "includeMcpJson": False,
                    }
                ),
                encoding="utf-8",
            )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                report["reason"] = "timeout"
                return report
            report = read_native_account_usage(
                (
                    command,
                    "chat",
                    "--v2",
                    "--agent",
                    name,
                    "--no-interactive",
                    "--trust-tools=",
                    "/usage",
                ),
                source=SOURCE,
                timeout_seconds=remaining,
                exchange=_exchange_usage,
                cwd=directory,
                env=env,
            )
    except OSError:
        report.update(
            status="unknown",
            reason="isolation_setup_or_cleanup_failed",
            windows=[],
            observed_at_utc=None,
        )
    return report


def _exchange_version(process: subprocess.Popen[Any], deadline: float) -> list[dict[str, Any]]:
    if _read_output(process, deadline).strip() != VERIFIED_VERSION:
        raise ValueError("Unverified client version")
    return [{"version_verified": True}]


def _exchange_usage(process: subprocess.Popen[Any], deadline: float) -> list[dict[str, Any]]:
    return normalize_usage(_read_output(process, deadline))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-seconds", type=float, default=15)
    args = parser.parse_args(argv)
    try:
        report = read_kiro_allowance(timeout_seconds=args.timeout_seconds)
    except ValueError:
        parser.error("Timeout must be finite and between zero and 120 seconds")
    print(json.dumps(report, allow_nan=False))
    return 0 if report["status"] == "available" else 1


if __name__ == "__main__":
    raise SystemExit(main())
