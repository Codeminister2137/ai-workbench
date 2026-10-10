"""Owned, bounded native account reads shared by provider-specific protocols."""

from __future__ import annotations

import ctypes
import math
import os
import queue
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from ai_provider.process_ownership import WindowsJob


def read_native_account_usage(
    command: tuple[str, ...] | None,
    *,
    source: str,
    timeout_seconds: float,
    exchange: Callable[[subprocess.Popen[Any], float], list[dict[str, Any]]],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run an account-only exchange with retained tree ownership and verified cleanup.

    Protocol adapters return whitelisted measurements, never raw provider data.
    The exchange runs in a reader thread so startup/write/read share one deadline.
    Cleanup has a separate two-second bound; failure invalidates measurements.
    """
    if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds):
        raise ValueError("Timeout must be finite")
    if not 0 < timeout_seconds <= 120:
        raise ValueError("Timeout must be between zero and 120 seconds")
    report: dict[str, Any] = {
        "status": "unknown",
        "source": source,
        "reason": "client_unavailable",
        "observed_at_utc": None,
        "windows": [],
        "cleanup_verified": True,
    }
    if not command:
        return report
    deadline = time.monotonic() + timeout_seconds
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=False,
            cwd=cwd,
            env=env,
            creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0) | 0x4)
            if os.name == "nt"
            else 0,
            start_new_session=os.name != "nt",
        )
    except OSError:
        report["reason"] = "client_start_failed"
        return report
    job: WindowsJob | None = None
    worker: threading.Thread | None = None
    outcome: queue.Queue[tuple[str, list[dict[str, Any]]]] = queue.Queue(maxsize=1)

    def read() -> None:
        try:
            windows = exchange(process, deadline)
            outcome.put(("available" if windows else "no_quota_windows", windows))
        except TimeoutError:
            outcome.put(("timeout", []))
        except (OSError, ValueError, RecursionError, OverflowError, TypeError):
            outcome.put(("unsupported_or_invalid_response", []))

    try:
        if os.name == "nt":
            from ctypes import wintypes

            job = WindowsJob(process)
            native = ctypes.WinDLL("ntdll")
            native.NtResumeProcess.argtypes = [wintypes.HANDLE]
            native.NtResumeProcess.restype = ctypes.c_long
            if native.NtResumeProcess(cast(Any, process)._handle) != 0:
                raise OSError("Unable to resume owned child")
        if time.monotonic() >= deadline:
            raise queue.Empty
        worker = threading.Thread(target=read, name="native-allowance-reader", daemon=True)
        worker.start()
        reason, windows = outcome.get(timeout=max(0.001, deadline - time.monotonic()))
        if time.monotonic() >= deadline:
            reason, windows = "timeout", []
        report["reason"] = reason
        if reason == "available":
            report.update(
                status="available", windows=windows, observed_at_utc=datetime.now(UTC).isoformat()
            )
    except queue.Empty:
        report["reason"] = "timeout"
    except OSError:
        report["reason"] = "client_ownership_failed"
    finally:
        cleanup_deadline = time.monotonic() + 2
        try:
            if job is not None:
                report["cleanup_verified"] = job.stop(2)
            elif os.name != "nt":
                try:
                    cast(Any, os).killpg(process.pid, cast(Any, signal).SIGKILL)
                except ProcessLookupError:
                    pass
            elif process.poll() is None:
                process.kill()
            process.wait(timeout=max(0.001, cleanup_deadline - time.monotonic()))
        except (OSError, subprocess.TimeoutExpired):
            report["cleanup_verified"] = False
        if worker is not None:
            worker.join(timeout=max(0, cleanup_deadline - time.monotonic()))
            report["cleanup_verified"] &= not worker.is_alive()
        for stream in (process.stdin, process.stdout):
            if stream is not None:
                if stream is process.stdout and worker is not None and worker.is_alive():
                    continue  # Closing while a reader holds the pipe lock can block.
                stream.close()
        if not report["cleanup_verified"]:
            report.update(
                status="unknown", reason="cleanup_unverified", windows=[], observed_at_utc=None
            )
    return report
