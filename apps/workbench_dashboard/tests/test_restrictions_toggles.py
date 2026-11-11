"""Owner restriction toggles: store, API validation, executor enforcement."""

from __future__ import annotations

from typing import cast

import pytest
from restrictions import describe_toggles, load_toggles, save_toggle


def test_defaults_when_missing_or_corrupt(tmp_path) -> None:
    toggles = load_toggles(tmp_path)
    assert toggles == {
        "auto_routing": False,
        "shell_tools": True,
        "sandbox": False,
        "delegation": False,
    }
    (tmp_path / "restrictions.json").write_text("not json", encoding="utf-8")
    assert load_toggles(tmp_path)["sandbox"] is False


def test_round_trip_and_validation(tmp_path) -> None:
    toggles = save_toggle(tmp_path, "sandbox", True)
    assert toggles["sandbox"] is True
    assert load_toggles(tmp_path)["sandbox"] is True
    with pytest.raises(ValueError, match="Unknown restriction toggle"):
        save_toggle(tmp_path, "nope", True)
    with pytest.raises(ValueError, match="boolean"):
        # Intentionally mistyped: validation must reject non-booleans.
        save_toggle(tmp_path, "sandbox", cast(bool, "yes"))


def test_describe_lists_all_with_text(tmp_path) -> None:
    described = describe_toggles(load_toggles(tmp_path))
    assert [item["name"] for item in described] == [
        "auto_routing",
        "shell_tools",
        "sandbox",
        "delegation",
    ]
    assert all(item["description"] for item in described)
