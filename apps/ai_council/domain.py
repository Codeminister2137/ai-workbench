from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CouncilMember:
    name: str
    model: str
    system_prompt: str
    temperature: float = 0.7
