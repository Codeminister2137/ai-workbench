"""Read-only local capability snapshot for provider/runtime decisions."""

from __future__ import annotations

import ctypes
import json
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai_provider.ollama_models import (
    LocalOllamaModel,
    RunningOllamaModel,
    list_local_ollama_models,
    list_running_ollama_models,
)
from ai_provider.ollama_runtime import ensure_ollama_server, is_ollama_server_available


@dataclass(frozen=True, slots=True)
class LocalMemoryInfo:
    """Local system memory information."""

    total_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class LocalGpuInfo:
    """Best-effort local GPU information."""

    name: str
    memory_bytes: int | None = None
    memory_source: str | None = None


@dataclass(frozen=True, slots=True)
class LocalDiskInfo:
    """Disk capacity information for one local path."""

    path: Path
    total_bytes: int
    used_bytes: int
    free_bytes: int


@dataclass(frozen=True, slots=True)
class LocalSystemInfo:
    """Basic local machine information relevant to model execution."""

    os_name: str
    os_version: str
    machine: str
    processor: str
    memory: LocalMemoryInfo = field(default_factory=LocalMemoryInfo)
    gpus: tuple[LocalGpuInfo, ...] = ()


@dataclass(frozen=True, slots=True)
class LocalProviderCapabilitySnapshot:
    """Read-only local state useful to provider and future orchestration code."""

    system: LocalSystemInfo
    models_path: Path
    models_disk: LocalDiskInfo | None
    ollama_available: bool
    installed_ollama_models: tuple[LocalOllamaModel, ...]
    running_ollama_models: tuple[RunningOllamaModel, ...]


def get_local_provider_capability_snapshot(
    *,
    models_path: Path | None = None,
    start_ollama: bool = False,
    include_installed_models: bool = True,
    include_running_models: bool = True,
) -> LocalProviderCapabilitySnapshot:
    """Return a read-only snapshot of local AI provider runtime capability."""

    effective_models_path = models_path or _default_ollama_models_path()
    if start_ollama:
        ensure_ollama_server()
    ollama_available = is_ollama_server_available()
    installed_models: tuple[LocalOllamaModel, ...] = ()
    running_models: tuple[RunningOllamaModel, ...] = ()
    if include_installed_models and ollama_available:
        installed_models = list_local_ollama_models()
    if include_running_models and ollama_available:
        running_models = list_running_ollama_models()

    return LocalProviderCapabilitySnapshot(
        system=local_system_info(),
        models_path=effective_models_path,
        models_disk=_disk_info(effective_models_path),
        ollama_available=ollama_available,
        installed_ollama_models=installed_models,
        running_ollama_models=running_models,
    )


def local_system_info() -> LocalSystemInfo:
    """Return best-effort local OS, memory, and GPU information."""

    return LocalSystemInfo(
        os_name=platform.system(),
        os_version=platform.version(),
        machine=platform.machine(),
        processor=platform.processor(),
        memory=LocalMemoryInfo(total_bytes=_total_memory_bytes()),
        gpus=_local_gpus(),
    )


def _default_ollama_models_path() -> Path:
    configured = os.getenv("OLLAMA_MODELS")
    if configured:
        return Path(configured)
    return Path.home() / ".ollama" / "models"


def _disk_info(path: Path) -> LocalDiskInfo | None:
    target = path if path.exists() else path.parent
    if not target.exists():
        return None
    usage = shutil.disk_usage(target)
    return LocalDiskInfo(
        path=path,
        total_bytes=usage.total,
        used_bytes=usage.used,
        free_bytes=usage.free,
    )


def _total_memory_bytes() -> int | None:
    if os.name == "nt":
        return _windows_total_memory_bytes()
    page_size = getattr(os, "sysconf", lambda name: None)("SC_PAGE_SIZE")
    page_count = getattr(os, "sysconf", lambda name: None)("SC_PHYS_PAGES")
    if isinstance(page_size, int) and isinstance(page_count, int):
        return page_size * page_count
    return None


def _windows_total_memory_bytes() -> int | None:
    class MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatusEx()
    status.dwLength = ctypes.sizeof(MemoryStatusEx)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
        return int(status.ullTotalPhys)
    return None


def _local_gpus() -> tuple[LocalGpuInfo, ...]:
    if os.name != "nt":
        return ()
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "Get-CimInstance Win32_VideoController | "
            "Select-Object Name,AdapterRAM | ConvertTo-Json -Compress"
        ),
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ()

    if not completed.stdout.strip():
        return ()
    try:
        raw_items = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return ()

    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    if not isinstance(raw_items, list):
        return ()
    return tuple(_gpu_from_raw(item) for item in raw_items if isinstance(item, dict))


def _gpu_from_raw(raw: dict[str, Any]) -> LocalGpuInfo:
    name = raw.get("Name")
    memory = raw.get("AdapterRAM")
    return LocalGpuInfo(
        name=name if isinstance(name, str) else "Unknown GPU",
        memory_bytes=memory if isinstance(memory, int) and memory > 0 else None,
        memory_source=(
            "win32_videocontroller_adapter_ram" if isinstance(memory, int) and memory > 0 else None
        ),
    )
