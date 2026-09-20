from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any

_EXAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "packages"
    / "ai_provider"
    / "examples"
    / "ollama_models.py"
)
_SPEC = importlib.util.spec_from_file_location("ollama_models_example", _EXAMPLE_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_EXAMPLE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _EXAMPLE
_SPEC.loader.exec_module(_EXAMPLE)


def test_start_background_pull_builds_detached_child_command(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}
    log_path = tmp_path / "pull.log"

    class FakeProcess:
        pid = 1234

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        captured["command"] = command
        captured["stdout"] = kwargs["stdout"]
        captured["stderr"] = kwargs["stderr"]
        return FakeProcess()

    monkeypatch.setattr(_EXAMPLE.subprocess, "Popen", fake_popen)
    args = argparse.Namespace(
        pull="qwen2.5-coder:14b",
        log_path=log_path,
        models_path=Path("D:/AI/Ollama/models"),
        min_free_gb=40.0,
        max_download_gb=80.0,
        timeout_seconds=120.0,
        base_url=None,
        start_ollama=True,
    )

    job = _EXAMPLE._start_background_pull(args)

    assert job.pid == 1234
    assert job.log_path == log_path
    assert "--foreground-child" in captured["command"]
    assert "--background" not in captured["command"]
    assert captured["command"][-1] == "--start-ollama"
    assert captured["stderr"] == _EXAMPLE.subprocess.STDOUT
    assert captured["stdout"].closed is True
