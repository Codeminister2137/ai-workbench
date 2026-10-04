"""Retained process ownership and bounded cleanup for fixed acceptance children."""

from __future__ import annotations

import ctypes
import os
import signal
import socket
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from ai_provider.acceptance_jobs import endpoint


def remaining(deadline: float, clock: Callable[[], float] = time.monotonic) -> float:
    value = deadline - clock()
    if value <= 0:
        raise TimeoutError("Acceptance operation deadline exhausted")
    return value


def process_identity(pid: int) -> str | None:
    """Read process birth identity; a PID alone is not permission to stop a child."""
    if os.name != "nt":
        try:
            return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
        except (OSError, IndexError):
            return None
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        exit_code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)) or exit_code.value != 259:
            return None
        stamps = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(item) for item in stamps)):
            return None
        return str((stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime)
    finally:
        kernel.CloseHandle(handle)


class WindowsJob:
    """An OS-owned job retains the child tree even after its root process exits."""

    def __init__(self, process: subprocess.Popen[Any]):
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_int64),
                ("job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD),
                ("minimum", ctypes.c_size_t),
                ("maximum", ctypes.c_size_t),
                ("active", wintypes.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD),
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("basic", BasicLimits),
                ("io", ctypes.c_uint64 * 6),
                ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t),
                ("peak_process", ctypes.c_size_t),
                ("peak_job", ctypes.c_size_t),
            ]

        class Accounting(ctypes.Structure):
            _fields_ = [
                ("times", ctypes.c_int64 * 4),
                ("faults", wintypes.DWORD),
                ("total", wintypes.DWORD),
                ("active", wintypes.DWORD),
                ("terminated", wintypes.DWORD),
            ]

        self.accounting_type = Accounting
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        self.kernel.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        self.kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError("Unable to create owned process job")
        try:
            limits = ExtendedLimits()
            limits.basic.flags = 0x2000  # Kill descendants when the last job handle closes.
            if not self.kernel.SetInformationJobObject(
                self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
            ):
                raise OSError("Unable to configure owned process job")
            if not self.kernel.AssignProcessToJobObject(self.handle, cast(Any, process)._handle):
                raise OSError("Unable to assign child to owned process job")
        except BaseException:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
            raise

    def stop(self, timeout: float) -> bool:
        if self.handle is None:
            return False
        try:
            if not self.kernel.TerminateJobObject(self.handle, 1):
                return False
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                accounting = self.accounting_type()
                if not self.kernel.QueryInformationJobObject(
                    self.handle, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None
                ):
                    return False
                if accounting.active == 0:
                    return True
                time.sleep(0.02)
            return False
        finally:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class OwnedChild:
    """Original Popen and OS job/group stay owned by one foreground supervisor."""

    def __init__(
        self,
        argv: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        log: Path,
        role: str,
        receipt: Callable[[dict[str, Any]], None],
    ):
        self.role = role
        self.windows_job: WindowsJob | None = None
        with log.open("xb") as output:
            self.process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                shell=False,
                # Assign the suspended root before it can spawn unowned descendants.
                creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0) | 0x4)
                if os.name == "nt"
                else 0,
                start_new_session=os.name != "nt",
            )
        try:
            if os.name == "nt":
                self.windows_job = WindowsJob(self.process)
            self.birth = process_identity(self.process.pid)
            if not self.birth:
                raise OSError("Child birth identity could not be verified")
            receipt({"stage": "process_started", **self.identity})
            if os.name == "nt":
                from ctypes import wintypes

                native = ctypes.WinDLL("ntdll")
                native.NtResumeProcess.argtypes = [wintypes.HANDLE]
                native.NtResumeProcess.restype = ctypes.c_long
                if native.NtResumeProcess(cast(Any, self.process)._handle) != 0:
                    raise OSError("Unable to resume the owned child")
        except BaseException:
            if self.windows_job:
                self.windows_job.stop(2)
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait(timeout=2)
            raise

    @property
    def identity(self) -> dict[str, Any]:
        return {"role": self.role, "pid": self.process.pid, "birth": self.birth}

    def wait(self, deadline: float, clock: Callable[[], float] = time.monotonic) -> int:
        return self.process.wait(timeout=remaining(deadline, clock))

    def stop(self, timeout: float) -> bool:
        if timeout <= 0:
            return False
        deadline = time.monotonic() + timeout
        if self.windows_job:
            # The retained OS job is stronger ownership than a fresh PID lookup.
            verified = self.windows_job.stop(timeout)
        else:
            verified = False
            if self.process.poll() is None and process_identity(self.process.pid) == self.birth:
                cast(Any, os).killpg(self.process.pid, cast(Any, signal).SIGKILL)
                verified = True
        try:
            self.process.wait(timeout=max(0.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            return False
        return verified


def port_unused(url: str) -> bool:
    host, port = endpoint(url)
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as probe:
            if os.name == "nt":
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            probe.bind((host, port))
            return True
    except OSError:
        return False


def listener_owned(url: str, pid: int, *, timeout: float = 2.0) -> bool:
    """Check listener PID/inodes without contacting an unknown HTTP service."""
    host, port = endpoint(url)
    if os.name == "nt":
        output = subprocess.run(
            [
                str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/netstat.exe"),
                "-ano",
                "-p",
                "tcp",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=True,
        ).stdout
        owners = []
        for line in output.splitlines():
            parts = line.split()
            if len(parts) == 5 and parts[0] == "TCP" and parts[3] == "LISTENING":
                address, _, raw_port = parts[1].rpartition(":")
                if raw_port == str(port) and address.strip("[]") == host:
                    owners.append(int(parts[4]))
        return bool(owners) and set(owners) == {pid}
    try:
        table = Path("/proc/net/tcp6" if ":" in host else "/proc/net/tcp").read_text()
        inodes = {
            line.split()[9]
            for line in table.splitlines()[1:]
            if line.split()[3] == "0A" and int(line.split()[1].split(":")[1], 16) == port
        }
        owned = {os.readlink(item) for item in Path(f"/proc/{pid}/fd").iterdir()}
        return bool(inodes) and all(f"socket:[{inode}]" in owned for inode in inodes)
    except (OSError, ValueError, IndexError):
        return False


def verify_runtime_owner(url: str, identity: dict[str, Any], *, timeout: float = 2.0) -> None:
    if (
        identity.get("role") != "runtime"
        or type(identity.get("pid")) is not int
        or not identity.get("birth")
        or process_identity(identity["pid"]) != identity["birth"]
        or not listener_owned(url, identity["pid"], timeout=timeout)
    ):
        raise ValueError("Runtime process/listener ownership is unverifiable; no request sent")
