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
    chair: str | None = None
    max_rounds: int = 3
    reaction_cap_chars: int = 2000
    max_tokens_per_question: int = 0


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
    names = {member.name for member in members}
    chair = raw.get("chair")
    if chair is not None and chair not in names:
        raise ValueError(f"Council chair {chair!r} is not a member.")
    max_rounds = int(raw.get("max_rounds", 3))
    if not 1 <= max_rounds <= 3:
        raise ValueError("Council max_rounds must be 1-3.")
    reaction_cap = int(raw.get("reaction_cap_chars", 2000))
    if reaction_cap < 100:
        raise ValueError("Council reaction_cap_chars must be >= 100.")
    token_cap = int(raw.get("max_tokens_per_question", 0))
    if token_cap < 0:
        raise ValueError("Council max_tokens_per_question must be >= 0.")

    return CouncilConfig(
        ollama_base_url=raw.get("ollama_base_url"),
        default_conversation=raw.get("default_conversation", "default"),
        members=members,
        chair=chair,
        max_rounds=max_rounds,
        reaction_cap_chars=reaction_cap,
        max_tokens_per_question=token_cap,
    )


def _member_from_json(item: dict[str, Any]) -> CouncilMember:
    return CouncilMember(
        name=item["name"],
        model=item["model"],
        system_prompt=item["system_prompt"],
        temperature=float(item.get("temperature", 0.7)),
    )
