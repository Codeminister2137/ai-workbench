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
    GOOGLE = "google"


@dataclass(frozen=True, slots=True)
class BackendConfig:
    """Runtime configuration needed to construct a provider chat client."""

    provider: ProviderKind
    model: str
    base_url: str | None = None
    api_key: str | None = None
    timeout_seconds: float = 60.0
    require_free_model: bool = False

    def __post_init__(self) -> None:
        if self.require_free_model and self.provider is not ProviderKind.REQUESTY:
            raise ProviderError(
                "Live free-model verification is currently supported only for Requesty.",
                category=ProviderErrorCategory.CONFIGURATION,
                provider=self.provider.value,
            )
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
        api_key = os.getenv(f"{prefix}_API_KEY") or _provider_api_key(provider)
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
            api_key=api_key,
            timeout_seconds=timeout,
        )


def _provider_api_key(provider: ProviderKind) -> str | None:
    """Return the conventional environment API key for one provider."""

    match provider:
        case ProviderKind.OPENAI:
            return os.getenv("OPENAI_API_KEY")
        case ProviderKind.REQUESTY:
            return os.getenv("REQUESTY_API_KEY")
        case ProviderKind.GOOGLE:
            return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        case ProviderKind.OLLAMA:
            return None
