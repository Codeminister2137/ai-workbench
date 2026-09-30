from __future__ import annotations

import argparse
import json
import sys
import time
import tracemalloc
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from io import TextIOBase
from pathlib import Path
from typing import Any

from ai_provider import AIResponse


@dataclass(frozen=True)
class RunMetrics:
    """Local process metrics captured for one CLI run."""

    started_wall_seconds: float
    started_cpu_seconds: float
    tracemalloc_started: bool


class TeeOutput(TextIOBase):
    """Write CLI output to the terminal and an optional transcript file."""

    def __init__(self, terminal: Any, transcript: Any) -> None:
        self._terminal = terminal
        self._transcript = transcript

    def write(self, text: str) -> int:
        self._transcript.write(text)
        try:
            self._terminal.write(text)
        except UnicodeEncodeError:
            encoding = getattr(self._terminal, "encoding", None) or "utf-8"
            safe_text = text.encode(encoding, errors="replace").decode(encoding)
            self._terminal.write(safe_text)
        return len(text)

    def write_transcript_only(self, text: str) -> int:
        """Write text only to the transcript file, not the terminal."""

        return self._transcript.write(text)

    def flush(self) -> None:
        self._terminal.flush()
        if not self._transcript.closed:
            self._transcript.flush()


def print_transcript_header(args: argparse.Namespace, argv: Sequence[str] | None) -> None:
    """Print reproducible CLI invocation metadata for transcript logs."""

    effective_argv = list(argv) if argv is not None else sys.argv[1:]
    print("=== CLI invocation ===")
    print(f"timestamp_utc: {datetime.now(UTC).isoformat()}")
    print(f"cwd: {Path.cwd()}")
    print("argv_json: " + json.dumps(effective_argv, ensure_ascii=False))
    print("request:")
    print(args.prompt or "")
    print()


def print_model_input(label: str, *, system_prompt: str, prompt: str) -> None:
    """Print the exact model input for evaluation transcripts."""

    print(f"\n=== {label} model input ===")
    print("system_prompt:")
    print("```text")
    print(system_prompt.rstrip())
    print("```")
    print("user_prompt:")
    print("```text")
    print(prompt.rstrip())
    print("```")


def print_external_agent_input(label: str, *, prompt: str) -> None:
    """Print the exact stdin prompt sent to an external agent CLI."""

    print(f"\n=== {label} external-agent input ===")
    print("stdin_prompt:")
    print("```text")
    print(prompt.rstrip())
    print("```")


def write_transcript_only(text: str) -> None:
    """Write content to the transcript side of stdout when tee logging is active."""

    writer = getattr(sys.stdout, "write_transcript_only", None)
    if callable(writer):
        writer(text)


def start_run_metrics() -> RunMetrics:
    """Start local process metrics for transcript observability."""

    tracemalloc_started = False
    if not tracemalloc.is_tracing():
        tracemalloc.start()
        tracemalloc_started = True
    return RunMetrics(
        started_wall_seconds=time.perf_counter(),
        started_cpu_seconds=time.process_time(),
        tracemalloc_started=tracemalloc_started,
    )


def print_run_metrics(
    metrics: RunMetrics,
    *,
    primary_elapsed_seconds: float | None,
    primary_response: AIResponse | None,
    scrutiny_elapsed_seconds: float | None,
    scrutiny_response: AIResponse | None,
) -> None:
    """Print local process and provider-reported metrics for transcript analysis."""

    current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    total_wall_seconds = time.perf_counter() - metrics.started_wall_seconds
    total_cpu_seconds = time.process_time() - metrics.started_cpu_seconds
    print("\n=== Run metrics ===")
    print(f"total_wall_seconds: {total_wall_seconds:.3f}")
    print(f"process_cpu_seconds: {total_cpu_seconds:.3f}")
    print(f"python_memory_current_bytes: {current_bytes}")
    print(f"python_memory_peak_bytes: {peak_bytes}")
    print(f"primary_elapsed_seconds: {_format_optional_seconds(primary_elapsed_seconds)}")
    _print_response_usage("primary", primary_response)
    print(f"scrutiny_elapsed_seconds: {_format_optional_seconds(scrutiny_elapsed_seconds)}")
    _print_response_usage("scrutiny", scrutiny_response)
    if metrics.tracemalloc_started:
        tracemalloc.stop()


def _print_response_usage(prefix: str, response: AIResponse | None) -> None:
    """Print token and provider latency metrics for one response."""

    if response is None:
        print(f"{prefix}_usage_source: unavailable")
        return
    print(f"{prefix}_usage_source: {response.usage.source.value}")
    print(f"{prefix}_input_tokens: {response.usage.input_tokens}")
    print(f"{prefix}_output_tokens: {response.usage.output_tokens}")
    print(f"{prefix}_total_tokens: {response.usage.total_tokens}")
    print(f"{prefix}_provider_latency_ms: {response.latency_ms}")


def _format_optional_seconds(value: float | None) -> str:
    """Format an optional elapsed-time value for stable transcript output."""

    if value is None:
        return "None"
    return f"{value:.3f}"
