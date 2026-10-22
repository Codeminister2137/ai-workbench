"""Direct validation commands with retained process-tree ownership."""

from __future__ import annotations

import locale
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, cast

from ai_provider.process_ownership import WindowsJob

CLEANUP_SECONDS = 2.0


class ValidationCleanupError(RuntimeError):
    """A started validator could not be safely closed; stop further validation."""


def _stop(process: subprocess.Popen[bytes], job: WindowsJob | None) -> None:
    deadline = time.monotonic() + CLEANUP_SECONDS
    verified = False
    try:
        if job is not None:
            verified = job.stop(CLEANUP_SECONDS)
        elif os.name != "nt":
            try:
                cast(Any, os).killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            verified = True
        elif process.poll() is None:
            # Ownership setup failed while the Windows root was still suspended.
            process.kill()
            verified = True
        process.wait(timeout=max(0.001, deadline - time.monotonic()))
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValidationCleanupError("Validation process cleanup could not be verified") from error
    if not verified:
        raise ValidationCleanupError("Validation process-tree cleanup could not be verified")


def run_validation_process(
    arguments: list[str],
    *,
    cwd: Path,
    timeout: float,
    capture_output: bool = True,
    text: bool = True,
    check: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Keep descendants owned until cleanup, including after their root exits.

    Temporary capture files avoid waiting on inherited output pipes. The command
    deadline includes launch/ownership setup; cleanup has a separate two-second
    bound. The caller selects the executable and optional environment. Timeout
    output retains at most the last 16,000 bytes of each stream.
    """
    if not capture_output or not text or check:
        raise ValueError("Validation requires text capture and explicit return-code handling")
    deadline = time.monotonic() + timeout
    job = None
    timed_out = False
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            arguments,
            cwd=cwd,
            env=env,
            stdout=stdout,
            stderr=stderr,
            shell=False,
            creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0) | 0x4)
            if os.name == "nt"
            else 0,
            start_new_session=os.name != "nt",
        )
        try:
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes

                job = WindowsJob(process)
                native = ctypes.WinDLL("ntdll")
                native.NtResumeProcess.argtypes = [wintypes.HANDLE]
                native.NtResumeProcess.restype = ctypes.c_long
                if time.monotonic() >= deadline:
                    timed_out = True
                elif native.NtResumeProcess(cast(Any, process)._handle) != 0:
                    raise OSError("Unable to resume owned validation process")
            try:
                if not timed_out:
                    process.wait(timeout=max(0.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                timed_out = True
        finally:
            active_error = sys.exception()
            try:
                _stop(process, job)
            except ValidationCleanupError as error:
                if isinstance(active_error, (KeyboardInterrupt, SystemExit)):
                    active_error.add_note(str(error))
                else:
                    raise
        encoding = "utf-8" if sys.flags.utf8_mode else locale.getencoding()
        captured = []
        for stream in (stdout, stderr):
            size = stream.seek(0, os.SEEK_END)
            stream.seek(max(0, size - 16_000) if timed_out else 0)
            captured.append(
                stream.read().decode(encoding, errors="replace" if timed_out else "strict")
            )
        output, errors = captured
    if timed_out:
        raise subprocess.TimeoutExpired(arguments, timeout, output=output, stderr=errors)
    return subprocess.CompletedProcess(arguments, process.returncode, output, errors)
