"""Read-only usage diagnostics over explicitly selected acceptance artifacts.

Sources are declared by the caller, not inferred from authentication or a path.
The report retains known counters, not prompts, raw client events or credentials.
It cannot determine remaining allowance or the supervisor's account usage.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from ai_provider.external_agents import parse_external_agent_jsonl

SOURCE_CLIENTS = {
    "local_free": "local",
    "chatgpt_subscription_allowance": "codex",
    "chatgpt_workspace_credits": "codex",
    "github_copilot_subscription_allowance": "copilot",
    "kiro_subscription_allowance": "kiro",
    "antigravity_subscription_allowance": "antigravity",
}
TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)
READ_LIMIT = 8_000_000


def _number(value: object) -> int | float | None:
    if type(value) is int and value >= 0:
        return value
    if type(value) is float and math.isfinite(value) and value >= 0:
        return value
    return None


def _read(directory: Path, name: str) -> str | None:
    target = directory / name
    if not target.is_file():
        return None
    if not target.resolve().is_relative_to(directory):
        raise ValueError(f"Receipt leaves the selected directory: {name}")
    with target.open("rb") as stream:
        body = stream.read(READ_LIMIT + 1)
    if len(body) > READ_LIMIT:
        raise ValueError(f"Receipt exceeds the diagnostic read limit: {name}")
    return body.decode("utf-8-sig")


def summarize_usage(directory: Path, source: str) -> dict[str, Any]:
    """Separate a run's reported counters without inventing cost or quota values."""
    if source not in SOURCE_CLIENTS:
        raise ValueError("Select a supported, explicit billing source")
    directory = directory.resolve()
    if not directory.is_dir():
        raise ValueError("Selected acceptance directory does not exist")
    report: dict[str, Any] = {
        "directory": str(directory),
        "declared_billing_source": source,
        "metrics": {},
        "evidence": [],
        "notes": [],
        "receipt_errors": 0,
        "remaining_allowance": "unknown",
        "supervisor_usage": "unknown",
    }
    if SOURCE_CLIENTS[source] == "local":
        text = _read(directory, "worker-result.json")
        if text is None:
            report["notes"].append("No worker-result.json usage receipt")
            return report
        result = json.loads(text)
        rows = result.get("usage") if isinstance(result, dict) else None
        if not isinstance(rows, list):
            raise ValueError("Worker result has no usage array")
        report["evidence"].append("worker-result.json")
        report["observed_calls"] = len(rows)
        for provenance in ("provider_reported", "estimated"):
            matching = [
                row for row in rows if isinstance(row, dict) and row.get("source") == provenance
            ]
            for field in TOKEN_FIELDS:
                values = [
                    number for row in matching if (number := _number(row.get(field))) is not None
                ]
                if values:
                    report["metrics"][f"{provenance}.{field}"] = {
                        "value": sum(values),
                        "measured_calls": len(values),
                        "scope": "sum_of_recorded_calls",
                    }
        report["notes"].append("Missing call counters are unknown; sums may be partial")
        return report

    events = _read(directory, "stdout.jsonl")
    if events is None:
        report["notes"].append("No stdout.jsonl client receipt; logs are not guessed")
        return report
    summary = parse_external_agent_jsonl(events)
    report["evidence"].append("stdout.jsonl")
    if summary.parse_errors:
        report["receipt_errors"] = len(summary.parse_errors)
        report["notes"].append(f"Client receipt has {len(summary.parse_errors)} malformed lines")
    usage = summary.usage or {}
    fields = TOKEN_FIELDS
    if SOURCE_CLIENTS[source] == "copilot":
        fields = ("premium_requests", "nano_aiu")
    for field in fields:
        value = usage.get(field)
        if field == "premium_requests" and value is None:
            value = usage.get("premiumRequests")
        number = _number(value)
        if number is not None:
            report["metrics"][field] = {
                "value": number,
                "scope": "latest_reported_usage",
            }
    meters = usage.get("metering_usage")
    if SOURCE_CLIENTS[source] == "kiro" and isinstance(meters, list):
        values_by_unit: dict[str, list[int | float]] = {}
        for meter in meters:
            if not isinstance(meter, dict):
                continue
            # Export only recognized units; arbitrary strings may contain private data.
            unit = meter.get("unit")
            number = _number(meter.get("value"))
            if (
                isinstance(unit, str)
                and unit in {"credit", "credits", "token", "tokens"}
                and number is not None
            ):
                values_by_unit.setdefault(unit, []).append(number)
        for unit, values in values_by_unit.items():
            for index, number in enumerate(values):
                key = f"meter.{unit}" + (f"[{index}]" if len(values) > 1 else "")
                report["metrics"][key] = {"value": number, "scope": "reported_meter_entry"}
            if len(values) > 1:
                report["notes"].append(f"Repeated meter unit {unit}: its total remains unknown")
    report["notes"].append("Latest client totals are not summed across checkpoints")
    report["notes"].append("Cached/reasoning counters are shown separately, never added to totals")
    if not report["metrics"]:
        report["notes"].append("No supported usage counters in the selected receipt")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", nargs=2, action="append", required=True, metavar=("SOURCE", "DIRECTORY")
    )
    args = parser.parse_args(argv)
    failed = False
    for source, directory in args.run:
        try:
            report = summarize_usage(Path(directory), source)
        except (OSError, ValueError, RecursionError) as error:
            print(
                f"Usage unavailable for {directory}: {type(error).__name__}; "
                "inspect selected receipts"
            )
            failed = True
            continue
        print(f"\nRun: {report['directory']}\nDeclared billing source: {source}")
        failed = failed or bool(report["receipt_errors"])
        for name, metric in report["metrics"].items():
            measured = metric.get("measured_calls")
            coverage = (
                f"; {measured}/{report['observed_calls']} calls measured"
                if measured is not None
                else ""
            )
            print(f"  {name}: {metric['value']} ({metric['scope']}{coverage})")
        if not report["metrics"]:
            print("  Usage: unknown")
        print("  Remaining allowance: unknown; supervisor account usage: unknown")
        for note in report["notes"]:
            print("  " + note)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
