from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum


class ProviderKind(StrEnum):
    OLLAMA = "ollama"
    REQUESTY = "requesty"
    OPENAI = "openai"


@dataclass(frozen=True, slots=True)
class BackendConfig:
    provider: ProviderKind
    model: str
    base_url: str | None = None
    timeout_seconds: float = 60.0

    @classmethod
    def from_env(cls, prefix: str = "AI_PROVIDER") -> BackendConfig:
        provider = ProviderKind(os.getenv(f"{prefix}_KIND", ProviderKind.OLLAMA.value))
        model = os.getenv(f"{prefix}_MODEL", "llama3.2")
        base_url = os.getenv(f"{prefix}_BASE_URL")
        timeout = float(os.getenv(f"{prefix}_TIMEOUT_SECONDS", "60"))
        return cls(
            provider=provider,
            model=model,
            base_url=base_url,
            timeout_seconds=timeout,
        )
