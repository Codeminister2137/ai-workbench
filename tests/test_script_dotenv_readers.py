"""Tests for the script dotenv readers delegating to the central helper."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _find_scripts_dir() -> Path:
    here = Path(__file__).resolve()
    for ancestor in [here.parent, *here.parents]:
        candidate = ancestor / "scripts" / "plan-with-supervisor.py"
        if candidate.is_file():
            return ancestor / "scripts"
    return here.parents[1] / "scripts"


SCRIPTS_DIR = _find_scripts_dir()


def _load_script_module(name: str, filename: str):
    path = SCRIPTS_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_supervised_module = _load_script_module(
    "baseten_supervised_develop_under_test", "baseten-supervised-develop.py"
)
_plan_module = _load_script_module("plan_with_supervisor_under_test", "plan-with-supervisor.py")

SUPERVISED_KEY = "BASETEN_HACKATHON_API_KEY"
PLAN_KEY = "BASETEN_HACKATHON_API_KEY"


def _write_env(root: Path, text: str) -> None:
    (root / ".env").write_text(text, encoding="utf-8")


def test_supervised_read_key_happy_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(_supervised_module, "ROOT", tmp_path)
    _write_env(tmp_path, f"{SUPERVISED_KEY}=sk-test-123\n")
    assert _supervised_module.read_key() == "sk-test-123"


def test_supervised_read_key_missing_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(_supervised_module, "ROOT", tmp_path)
    assert not (tmp_path / ".env").exists()
    with pytest.raises(ValueError):
        _supervised_module.read_key()


def test_supervised_read_key_missing_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(_supervised_module, "ROOT", tmp_path)
    _write_env(tmp_path, "SOME_OTHER_KEY=value\n")
    with pytest.raises(ValueError):
        _supervised_module.read_key()


def test_supervised_read_key_empty_value(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(_supervised_module, "ROOT", tmp_path)
    _write_env(tmp_path, f"{SUPERVISED_KEY}=\n")
    with pytest.raises(ValueError):
        _supervised_module.read_key()


def test_supervised_read_key_duplicate_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(_supervised_module, "ROOT", tmp_path)
    _write_env(
        tmp_path,
        f"{SUPERVISED_KEY}=first-value\n{SUPERVISED_KEY}=second-value\n",
    )
    with pytest.raises(ValueError):
        _supervised_module.read_key()


def test_plan_read_key_happy_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(_plan_module, "ROOT", tmp_path)
    _write_env(tmp_path, f"{PLAN_KEY}=sk-test-456\n")
    assert _plan_module._read_key() == "sk-test-456"


def test_plan_read_key_missing_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(_plan_module, "ROOT", tmp_path)
    assert not (tmp_path / ".env").exists()
    with pytest.raises(ValueError):
        _plan_module._read_key()


def test_plan_read_key_missing_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(_plan_module, "ROOT", tmp_path)
    _write_env(tmp_path, "SOME_OTHER_KEY=value\n")
    with pytest.raises(ValueError):
        _plan_module._read_key()


def test_plan_read_key_empty_value(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(_plan_module, "ROOT", tmp_path)
    _write_env(tmp_path, f"{PLAN_KEY}=   \n")
    with pytest.raises(ValueError):
        _plan_module._read_key()


def test_plan_read_key_duplicate_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(_plan_module, "ROOT", tmp_path)
    _write_env(
        tmp_path,
        f"{PLAN_KEY}=first-value\n{PLAN_KEY}=second-value\n",
    )
    with pytest.raises(ValueError):
        _plan_module._read_key()
