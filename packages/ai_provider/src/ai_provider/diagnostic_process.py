"""Bounded diagnostic execution with retained ownership of native descendants."""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, cast

from ai_provider.process_ownership import WindowsJob


def _posix_group_running(group_id: int) -> bool:
    """Treat Linux zombies as stopped; leave unobservable groups unverified."""
    try:
        cast(Any, os).killpg(group_id, 0)
    except ProcessLookupError:
        return False
    if sys.platform != "linux":
        return True
    # killpg(0) also sees dead members waiting for init to reap them.
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            state, member_group = fields[0], int(fields[2])
        except FileNotFoundError:
            continue
        except (OSError, ValueError, IndexError):
            return True
        if member_group == group_id and state not in {"Z", "X"}:
            return True
    return False


def run_owned_diagnostic(
    command: tuple[str, ...], *, timeout: float
) -> subprocess.CompletedProcess[str]:
    """Capture output without inherited-pipe waits; always verify tree cleanup."""
    with tempfile.TemporaryFile(mode="w+") as stdout, tempfile.TemporaryFile(mode="w+") as stderr:
        process = subprocess.Popen(
            command,
            stdout=stdout,
            stderr=stderr,
            creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0) | 0x4)
            if os.name == "nt"
            else 0,
            start_new_session=os.name != "nt",
        )
        job = None
        try:
            if os.name == "nt":
                from ctypes import wintypes

                job = WindowsJob(process)
                native = ctypes.WinDLL("ntdll")
                native.NtResumeProcess.argtypes = [wintypes.HANDLE]
                native.NtResumeProcess.restype = ctypes.c_long
                if native.NtResumeProcess(cast(Any, process)._handle) != 0:
                    raise OSError("Unable to resume diagnostic child")
            returncode = process.wait(timeout=timeout)
        finally:
            active_error = sys.exception()
            deadline = time.monotonic() + 2
            verified = True
            cleanup_interrupt: KeyboardInterrupt | SystemExit | None = None
            try:
                if job is not None:
                    verified = job.stop(max(0, deadline - time.monotonic()))
                elif os.name != "nt":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                elif process.poll() is None:
                    # Ownership failed while the root was still suspended.
                    process.kill()
            except (KeyboardInterrupt, SystemExit) as exc:
                # Still attempt the bounded root cleanup below before delivering
                # cancellation, and never claim the interrupted tree stop passed.
                cleanup_interrupt = exc
                verified = False
            except Exception:
                verified = False
            try:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=max(0.001, deadline - time.monotonic()))
                if os.name != "nt":
                    while time.monotonic() < deadline:
                        if not _posix_group_running(process.pid):
                            break
                        time.sleep(0.02)
                    else:
                        verified = False
            except (KeyboardInterrupt, SystemExit) as exc:
                cleanup_interrupt = exc
                verified = False
            except (OSError, subprocess.TimeoutExpired):
                verified = False
            if not verified:
                message = "Diagnostic process-tree cleanup could not be verified"
                if isinstance(active_error, (KeyboardInterrupt, SystemExit)):
                    active_error.add_note(message)
                elif cleanup_interrupt is not None:
                    cleanup_interrupt.add_note(message)
                    raise cleanup_interrupt
                else:
                    raise OSError(message)
        stdout.seek(0)
        stderr.seek(0)
        return subprocess.CompletedProcess(command, returncode, stdout.read(), stderr.read())
