from __future__ import annotations

import subprocess
from pathlib import Path

from ai_provider import LocalOllamaModel, RunningOllamaModel
from ai_provider.local_capabilities import (
    LocalGpuInfo,
    _gpu_from_raw,
    get_local_provider_capability_snapshot,
)


def test_local_capability_snapshot_composes_ollama_state(
    monkeypatch,
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "models"
    model_path.mkdir()
    installed_model = LocalOllamaModel(
        name="qwen3:14b",
        model="qwen3:14b",
        size_bytes=9,
    )
    running_model = RunningOllamaModel(
        name="qwen3:14b",
        model="qwen3:14b",
        size_bytes=9,
        size_vram_bytes=7,
    )

    monkeypatch.setattr(
        "ai_provider.local_capabilities.is_ollama_server_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "ai_provider.local_capabilities.get_ollama_version",
        lambda: None,
    )
    monkeypatch.setattr(
        "ai_provider.local_capabilities.list_local_ollama_models",
        lambda: (installed_model,),
    )
    monkeypatch.setattr(
        "ai_provider.local_capabilities.list_running_ollama_models",
        lambda: (running_model,),
    )
    monkeypatch.setattr(
        "ai_provider.local_capabilities.local_system_info",
        lambda: _fake_system_info(),
    )

    snapshot = get_local_provider_capability_snapshot(
        models_path=model_path,
    )

    assert snapshot.models_path == model_path
    assert snapshot.models_disk is not None
    assert snapshot.ollama_available is True
    assert snapshot.ollama_version is None
    assert snapshot.installed_ollama_models == (installed_model,)
    assert snapshot.running_ollama_models == (running_model,)


def test_local_capability_snapshot_uses_user_ollama_models_env(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path))
    monkeypatch.setattr(
        "ai_provider.local_capabilities.is_ollama_server_available",
        lambda: False,
    )
    monkeypatch.setattr(
        "ai_provider.local_capabilities.local_system_info",
        lambda: _fake_system_info(),
    )

    snapshot = get_local_provider_capability_snapshot(include_installed_models=False)

    assert snapshot.models_path == tmp_path
    assert snapshot.installed_ollama_models == ()


def test_local_capability_snapshot_can_start_ollama_without_listing_models(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr("ai_provider.local_capabilities.get_ollama_version", lambda: "test-version")

    monkeypatch.setattr(
        "ai_provider.local_capabilities.ensure_ollama_server",
        lambda: calls.append("started"),
    )
    monkeypatch.setattr(
        "ai_provider.local_capabilities.is_ollama_server_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "ai_provider.local_capabilities.local_system_info",
        lambda: _fake_system_info(),
    )

    snapshot = get_local_provider_capability_snapshot(
        models_path=tmp_path,
        include_installed_models=False,
        include_running_models=False,
        start_ollama=True,
    )

    assert calls == ["started"]
    assert snapshot.ollama_available is True
    assert snapshot.ollama_version == "test-version"
    assert snapshot.installed_ollama_models == ()


def test_gpu_from_raw_ignores_missing_memory() -> None:
    gpu = _gpu_from_raw({"Name": "AMD Radeon RX 7800 XT", "AdapterRAM": None})

    assert gpu == LocalGpuInfo(name="AMD Radeon RX 7800 XT", memory_bytes=None)


def test_gpu_from_raw_labels_unverified_windows_memory_source() -> None:
    gpu = _gpu_from_raw({"Name": "AMD Radeon RX 7800 XT", "AdapterRAM": 4 * 1024**3})

    assert gpu.memory_bytes == 4 * 1024**3
    assert gpu.memory_source == "win32_videocontroller_adapter_ram"


def test_local_gpu_probe_tolerates_powershell_failure(monkeypatch) -> None:
    import ai_provider.local_capabilities as capabilities

    def fake_run(*args, **kwargs):
        raise subprocess.SubprocessError

    monkeypatch.setattr(capabilities.os, "name", "nt")
    monkeypatch.setattr(capabilities.subprocess, "run", fake_run)

    assert capabilities._local_gpus() == ()


def _fake_system_info():
    from ai_provider.local_capabilities import LocalSystemInfo

    return LocalSystemInfo(
        os_name="TestOS",
        os_version="1",
        machine="x86_64",
        processor="test",
    )
