"""Backend configuration for provider chat clients."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum

from ai_provider.errors import ProviderError, ProviderErrorCategory


class ProviderKind(StrEnum):
    """Provider identifiers supported by configuration and factories."""

    OLLAMA = "ollama"
    REQUESTY = "requesty"
    OPENAI = "openai"


@dataclass(frozen=True, slots=True)
class BackendConfig:
    """Runtime configuration needed to construct a provider chat client."""

    provider: ProviderKind
    model: str
    base_url: str | None = None
    timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ProviderError(
                "Backend model must not be empty.",
                category=ProviderErrorCategory.CONFIGURATION,
                provider=self.provider.value,
            )
        if self.timeout_seconds <= 0:
            raise ProviderError(
                "Backend timeout must be greater than zero seconds.",
                category=ProviderErrorCategory.CONFIGURATION,
                provider=self.provider.value,
            )

    @classmethod
    def from_env(cls, prefix: str = "AI_PROVIDER") -> BackendConfig:
        """Build backend configuration from environment variables."""

        provider_value = os.getenv(f"{prefix}_KIND", ProviderKind.OLLAMA.value)
        try:
            provider = ProviderKind(provider_value)
        except ValueError as exc:
            raise ProviderError(
                f"Unsupported provider kind: {provider_value}.",
                category=ProviderErrorCategory.CONFIGURATION,
                provider=provider_value,
                raw_error=exc,
            ) from exc

        model = os.getenv(f"{prefix}_MODEL", "llama3.2").strip()
        base_url = os.getenv(f"{prefix}_BASE_URL")
        timeout_value = os.getenv(f"{prefix}_TIMEOUT_SECONDS", "60")
        try:
            timeout = float(timeout_value)
        except ValueError as exc:
            raise ProviderError(
                f"Invalid timeout value for {prefix}_TIMEOUT_SECONDS: {timeout_value}.",
                category=ProviderErrorCategory.CONFIGURATION,
                provider=provider.value,
                raw_error=exc,
            ) from exc
        return cls(
            provider=provider,
            model=model,
            base_url=base_url,
            timeout_seconds=timeout,
        )
