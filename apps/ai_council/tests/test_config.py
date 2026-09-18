from __future__ import annotations

import json

import pytest

from config import load_config
from tests.helpers import write_config


def test_loads_members_from_json(tmp_path) -> None:
    config_path = tmp_path / "council.json"
    write_config(config_path, model="mistral")

    config = load_config(config_path)

    assert config.default_conversation == "test-conversation"
    assert config.ollama_base_url is None
    assert [member.name for member in config.members] == ["Analyst", "Skeptic"]
    assert [member.model for member in config.members] == ["mistral", "mistral"]


def test_rejects_config_without_members(tmp_path) -> None:
    config_path = tmp_path / "council.json"
    config_path.write_text(json.dumps({"members": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="at least one member"):
        load_config(config_path)


def test_missing_config_has_actionable_error(tmp_path) -> None:
    missing_path = tmp_path / "missing.json"

    with pytest.raises(FileNotFoundError, match="Missing"):
        load_config(missing_path)
