"""Tests for the skill-registry generator (docs stay in sync with tools)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/generate_skill_registry.py"


def _load():
    spec = importlib.util.spec_from_file_location("gen_registry", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_render_lists_known_tools() -> None:
    gen = _load()
    rendered = gen.render()
    for name in ("read_file", "edit_file", "run_command", "grep_search"):
        assert f"| {name} |" in rendered


def test_committed_registry_is_current() -> None:
    gen = _load()
    assert gen.render() == (ROOT / "docs/skills-registry.md").read_text(encoding="utf-8")


def test_check_mode_passes() -> None:
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stdout + done.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
