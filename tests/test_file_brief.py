"""Tests for scripts/file-brief.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "file-brief.py"


def _load():
    spec = importlib.util.spec_from_file_location("file_brief", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_payload_carries_options() -> None:
    mod = _load()
    payload = mod.build_payload(title="Merge brief: x", body="b", options=["Merge now", "Hold"])
    assert payload["options"] == ["Merge now", "Hold"]
    assert payload["type"] == "decision"
    assert payload["created_by"] == "supervisor"
    assert payload["assignee"] == "owner"


def test_decision_requires_two_options() -> None:
    mod = _load()
    with pytest.raises(ValueError, match="at least two"):
        mod.build_payload(title="t", body="b", options=["Only one"])
    with pytest.raises(ValueError, match="title is required"):
        mod.build_payload(title="  ", body="b", options=["A", "B"])
    # Non-decision items may carry zero options.
    payload = mod.build_payload(title="t", body="b", options=[], item_type="note")
    assert payload["options"] == []


def test_dry_run_prints_payload(capsys) -> None:
    mod = _load()
    code = mod.main(["--title", "t", "--body", "b", "--option", "A", "--option", "B", "--dry-run"])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["options"] == ["A", "B"]


def test_main_rejects_optionless_decision(capsys) -> None:
    mod = _load()
    assert mod.main(["--title", "t", "--body", "b"]) == 2
    assert "at least two" in capsys.readouterr().err


def test_tier_metadata_optional_and_validated() -> None:
    mod = _load()
    payload = mod.build_payload(title="t", body="b", options=["A", "B"], tier="tier2")
    assert payload["metadata"] == {"tier": "tier2"}
    plain = mod.build_payload(title="t", body="b", options=["A", "B"])
    assert "metadata" not in plain
    with pytest.raises(ValueError, match="tier"):
        mod.build_payload(title="t", body="b", options=["A", "B"], tier="tier9")
