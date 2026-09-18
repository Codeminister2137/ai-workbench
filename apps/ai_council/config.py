from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from domain import CouncilMember

DEFAULT_CONFIG_PATH = Path("council.json")
EXAMPLE_CONFIG_PATH = Path("council.example.json")


@dataclass(frozen=True)
class CouncilConfig:
    ollama_base_url: str | None
    default_conversation: str
    members: list[CouncilMember]


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> CouncilConfig:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Copy {EXAMPLE_CONFIG_PATH} to {DEFAULT_CONFIG_PATH} "
            "and edit it locally."
        )

    raw = json.loads(path.read_text(encoding="utf-8"))
    members = [_member_from_json(item) for item in raw.get("members", [])]
    if not members:
        raise ValueError("Council config must define at least one member.")

    return CouncilConfig(
        ollama_base_url=raw.get("ollama_base_url"),
        default_conversation=raw.get("default_conversation", "default"),
        members=members,
    )


def _member_from_json(item: dict[str, Any]) -> CouncilMember:
    return CouncilMember(
        name=item["name"],
        model=item["model"],
        system_prompt=item["system_prompt"],
        temperature=float(item.get("temperature", 0.7)),
    )
