"""Reusable direct-process validation and bounded result reporting."""

from __future__ import annotations

import argparse
import math
import shlex
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ai_agent.repo_assistant_args import DEFAULT_VALIDATION_COMMAND


@dataclass(frozen=True, slots=True)
class ValidationCommandResult:
    """Captured result for one deterministic validation command."""

    command: str
    returncode: int | None
    status: str
    elapsed_seconds: float
    executable: str | None = None
    stdout_preview: str = ""
    stderr_preview: str = ""
    failure_reason: str = ""


def activity_preview_lines(text: str, *, limit: int = 1_500) -> str:
    """Return a compact preview for command output fields."""

    normalized = "\n".join(line.rstrip() for line in text.splitlines() if line.strip())
    limit = max(0, limit)
    if len(normalized) <= limit:
        return normalized
    suffix = " ...[truncated]"
    return normalized[: max(0, limit - len(suffix))].rstrip() + suffix[:limit]


def validation_commands_from_args(args: argparse.Namespace) -> tuple[str, ...]:
    """Return deterministic validation commands selected for this run."""

    if args.skip_validation:
        return ()
    commands = tuple(command.strip() for command in args.validation_command if command.strip())
    if getattr(args, "tool_profile", "coding") == "research":
        return commands
    return commands or (DEFAULT_VALIDATION_COMMAND,)


def split_validation_command(command: str, *, windows: bool) -> list[str]:
    """Split a direct-execution command while preserving Windows path separators."""

    arguments = shlex.split(command, posix=not windows)
    if windows:
        arguments = [
            argument[1:-1]
            if len(argument) >= 2 and argument[0] == argument[-1] == '"'
            else argument
            for argument in arguments
        ]
    return arguments


def _captured_text(value: str | bytes | None) -> str:
    """TimeoutExpired may carry bytes even when the process requested text."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def run_validation_commands(
    commands: Sequence[str],
    *,
    repo_root: Path,
    timeout_seconds: float,
    default_python: str | None = sys.executable,
    progress_callback: Callable[[str], None] = print,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> tuple[ValidationCommandResult, ...]:
    """Run deterministic local validation commands and capture bounded output."""

    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
        raise ValueError("Validation timeout must be a finite positive number")
    try:
        valid_timeout = timeout_seconds > 0 and math.isfinite(timeout_seconds)
    except OverflowError:
        valid_timeout = False
    if not valid_timeout:
        raise ValueError("Validation timeout must be a finite positive number")
    results: list[ValidationCommandResult] = []
    execute = subprocess.run if runner is None else runner
    for index, command in enumerate(commands, start=1):
        progress_callback(f"validation_command: {command}")
        started = time.perf_counter()
        executable = None
        try:
            command_arguments = split_validation_command(command, windows=sys.platform == "win32")
            if not command_arguments:
                raise ValueError("Validation command must contain an executable")
            if command == DEFAULT_VALIDATION_COMMAND and default_python is not None:
                command_arguments[0] = default_python
            executable = command_arguments[0]
            completed = execute(
                command_arguments,
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = time.perf_counter() - started
            stdout = _captured_text(exc.stdout)
            stderr = _captured_text(exc.stderr)
            results.append(
                ValidationCommandResult(
                    command=command,
                    executable=executable,
                    returncode=None,
                    status="timeout",
                    elapsed_seconds=elapsed,
                    stdout_preview=activity_preview_lines(stdout),
                    stderr_preview=activity_preview_lines(stderr),
                    failure_reason=f"validation command timed out after {timeout_seconds:g}s",
                )
            )
            progress_callback(f"validation_result: {index} status=timeout")
        except (OSError, ValueError) as exc:
            elapsed = time.perf_counter() - started
            results.append(
                ValidationCommandResult(
                    command=command,
                    executable=executable,
                    returncode=None,
                    status="failed_to_start",
                    elapsed_seconds=elapsed,
                    failure_reason=str(exc),
                )
            )
            progress_callback(f"validation_result: {index} status=failed_to_start")
        else:
            elapsed = time.perf_counter() - started
            status = "passed" if completed.returncode == 0 else "failed"
            results.append(
                ValidationCommandResult(
                    command=command,
                    executable=executable,
                    returncode=completed.returncode,
                    status=status,
                    elapsed_seconds=elapsed,
                    stdout_preview=activity_preview_lines(completed.stdout),
                    stderr_preview=activity_preview_lines(completed.stderr),
                    failure_reason=""
                    if completed.returncode == 0
                    else f"validation command exited with code {completed.returncode}",
                )
            )
            progress_callback(
                f"validation_result: {index} status={status} returncode={completed.returncode}"
            )
    return tuple(results)


def default_validation_python(args: argparse.Namespace) -> str | None:
    """Select an explicit executable only when the built-in pytest default is active."""
    commands = getattr(args, "validation_command", ())
    if getattr(args, "skip_validation", False) or any(
        isinstance(command, str) and command.strip() for command in commands
    ):
        return None
    if getattr(args, "tool_profile", "coding") == "research":
        return None
    return getattr(args, "validation_python", None) or sys.executable


def validation_status(results: Sequence[ValidationCommandResult]) -> str:
    """Collapse command results into the stage-level validation status."""

    if not results:
        return "not_run"
    if all(result.status == "passed" for result in results):
        return "passed"
    if any(result.status == "timeout" for result in results):
        return "timeout"
    return "failed"


def validation_results_json(
    results: Sequence[ValidationCommandResult],
) -> list[dict[str, object]]:
    """Return stable JSON-friendly validation result metadata."""

    return [
        {
            "command": result.command,
            "executable": result.executable,
            "returncode": result.returncode,
            "status": result.status,
            "elapsed_seconds": round(result.elapsed_seconds, 3),
            "stdout_preview": result.stdout_preview,
            "stderr_preview": result.stderr_preview,
            "failure_reason": result.failure_reason,
        }
        for result in results
    ]
