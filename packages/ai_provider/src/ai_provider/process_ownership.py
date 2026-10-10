"""Retained Windows process-tree ownership shared by bounded native clients."""

from __future__ import annotations

import ctypes
import subprocess
import time
from typing import Any, cast


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
