"""One bounded native Codex schema probe using the existing CLI runner.

The caller supplies current allowance authorization through capability_eval.
There are no retries, fallback routes or generated-tool execution. Native tools
and streaming remain unmeasured: CLI event streaming is not ChatClient streaming.
"""

from __future__ import annotations

import json
import math
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from ai_provider.capability_eval import SCHEMA, Verdict
from ai_provider.codex_usage import read_codex_allowance
from ai_provider.external_agents import (
    codex_eval_config,
    run_external_agent,
)

CALL_SECONDS = 180
STOP_THRESHOLD_PP = 10


class ProbeStopped(ValueError):
    """Safe, locally authored diagnostic that may be retained in a receipt."""


def checked_windows(report: dict) -> dict[tuple[str, str], tuple[float, int]]:
    """Require fresh, complete primary/secondary readings with cycle identity."""
    if report.get("status") != "available" or report.get("cleanup_verified") is not True:
        raise ProbeStopped("allowance unavailable or cleanup unverified")
    observed = datetime.fromisoformat(report.get("observed_at_utc") or "")
    if observed.tzinfo is None or not 0 <= (datetime.now(UTC) - observed).total_seconds() <= 60:
        raise ProbeStopped("allowance reading stale")
    windows = {}
    for row in report.get("windows", []):
        key = (row.get("bucket_id"), row.get("window"))
        used, reset = row.get("used_percent"), row.get("resets_at_unix_seconds")
        if (
            not isinstance(key[0], str)
            or not key[0]
            or key[1] not in {"primary", "secondary"}
            or key in windows
            or type(used) not in (int, float)
            or not math.isfinite(used)
            or not 0 <= used < 100
            or type(reset) is not int
            or reset <= datetime.now(UTC).timestamp()
        ):
            raise ProbeStopped("allowance window invalid or exhausted")
        windows[key] = (float(used), reset)
    buckets = {key[0] for key in windows}
    if not buckets or any(
        (bucket, name) not in windows for bucket in buckets for name in ("primary", "secondary")
    ):
        raise ProbeStopped("both allowance windows required")
    return windows


def check_after(before: dict, after: dict) -> None:
    """Accept call overshoot, then stop; never predict per-call consumption."""
    if before.keys() != after.keys():
        raise ProbeStopped("allowance buckets changed")
    for key, (used, reset) in before.items():
        current, current_reset = after[key]
        if reset != current_reset or current < used:
            raise ProbeStopped("allowance cycle changed")
        if current - used >= STOP_THRESHOLD_PP:
            raise ProbeStopped("observed allowance stop threshold reached")


def probe_codex(route_id: str, model: str, output: Path) -> Verdict:
    """Preserve a one-shot receipt even when inference or postflight fails."""
    started = time.monotonic()
    checked = datetime.now(UTC).isoformat()
    artifact = output.with_suffix(output.suffix + ".native")
    artifact.mkdir()  # Atomic, never reuse a consumed or partly completed trial.
    status, detail = "unknown", "native probe did not finish"
    receipt: dict = {
        "route_id": route_id,
        "model": model,
        "max_cli_invocations": 1,
        "timeout_seconds": CALL_SECONDS,
        "stop_threshold_pp": STOP_THRESHOLD_PP,
        "tools": "unmeasured",
        "streaming": "unmeasured",
    }
    try:
        receipt["phase"] = "client_lookup"
        schema = artifact / "schema.json"
        schema.write_text(json.dumps(SCHEMA), encoding="utf-8")
        before_report = read_codex_allowance()
        receipt["before"] = before_report
        receipt["phase"] = "preflight"
        before = checked_windows(before_report)
        # Persist admission evidence before the only possible inference call.
        (artifact / "admission.json").write_text(json.dumps(receipt), encoding="utf-8")
        try:
            receipt["phase"] = "inference"
            with tempfile.TemporaryDirectory(prefix="codex-capability-") as working:
                subprocess.run(
                    ["git", "init", "--quiet", working],
                    check=True,
                    capture_output=True,
                    timeout=10,
                )
                result = run_external_agent(
                    'Return exactly {"answer":7}. Do not use tools, inspect files, or access network.',
                    codex_eval_config(
                        model,
                        Path(working),
                        schema.resolve(),
                        (artifact / "answer.json").resolve(),
                        timeout_seconds=CALL_SECONDS,
                    ),
                )
            receipt["returncode"] = result.returncode
            receipt["usage"] = result.events.usage if result.events else None
        except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
            receipt["inference_error_type"] = type(exc).__name__
            raise
        finally:
            receipt["phase"] = "postflight"
            after_report = read_codex_allowance()
            receipt["after"] = after_report
        check_after(before, checked_windows(after_report))
        receipt["phase"] = "grade"
        events = result.events
        if result.returncode or events is None or events.failure_reason or events.parse_errors:
            raise ProbeStopped("native process or event protocol failed")
        if (
            events.command_events
            or events.tool_events
            or events.web_search_events
            or events.file_change_events
        ):
            raise ProbeStopped("unexpected native tool activity")
        answer = json.loads(result.last_message or events.final_answer or "null")
        passed = (
            isinstance(answer, dict)
            and answer == {"answer": 7}
            and type(answer.get("answer")) is int
        )
        status = "pass" if passed else "fail"
        detail = "native output-schema exact integer object; tools/streaming unmeasured"
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        # Safe locally generated diagnostics only; never retain raw client errors.
        detail = f"native probe stopped ({type(exc).__name__}); inspect receipt"
        receipt["error_type"] = type(exc).__name__
        if isinstance(exc, ProbeStopped):
            receipt["stop_reason"] = str(exc)
    finally:
        receipt.update(status=status, detail=detail)
        (artifact / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return Verdict(
        route_id, "structured_output", status, checked, round(time.monotonic() - started, 3), detail
    )
