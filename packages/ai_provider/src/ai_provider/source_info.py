"""Common source-information contract for on-demand provider metadata.

This is a small, source-neutral interface implemented by provider-specific
collectors. It keeps model inventory, published limits, response usage and
account allowance observation separate and explicit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from ai_provider.contracts import ModelCapabilities, UsageMetadata


@dataclass(frozen=True, slots=True)
class ModelInventoryItem:
    """One model discovered from an official source endpoint.

    Capacities and prices are source-reported or published values, not quality
    judgments. Unknown fields stay ``None`` rather than inferred defaults.
    """

    id: str
    source: str
    endpoint: str | None = None
    capabilities: ModelCapabilities | None = None
    context_window_tokens: int | None = None
    prices: dict[str, Any] | None = None
    observed_at_utc: str | None = None
    protocol: str | None = None
    trains_on_request_data: bool | None = None
    requires_global_regions: bool | None = None


@dataclass(frozen=True, slots=True)
class ModelInventory:
    """Result of listing models from one source."""

    status: str
    source: str
    models: tuple[ModelInventoryItem, ...] = ()
    observed_at_utc: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation without raw provider secrets."""

        return {
            "status": self.status,
            "source": self.source,
            "observed_at_utc": self.observed_at_utc,
            "reason": self.reason,
            "models": [
                {
                    "id": model.id,
                    "endpoint": model.endpoint,
                    "capabilities": (
                        {
                            name: getattr(model.capabilities, name)
                            for name in (
                                "chat",
                                "streaming",
                                "tools",
                                "structured_output",
                                "multimodal_input",
                                "embeddings",
                            )
                        }
                        if model.capabilities is not None
                        else None
                    ),
                    "context_window_tokens": model.context_window_tokens,
                    "prices": model.prices,
                    "observed_at_utc": model.observed_at_utc,
                    "protocol": model.protocol,
                    "trains_on_request_data": model.trains_on_request_data,
                    "requires_global_regions": model.requires_global_regions,
                }
                for model in self.models
            ],
        }


@dataclass(frozen=True, slots=True)
class AccountAllowance:
    """Account remaining/spend observation from one source.

    ``status`` is one of ``observed``, ``unavailable``, ``unknown``.
    ``windows`` holds source-specific bucket objects without account identity.
    """

    status: str
    source: str
    windows: tuple[dict[str, Any], ...] = ()
    observed_at_utc: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation without account identity."""

        return {
            "status": self.status,
            "source": self.source,
            "observed_at_utc": self.observed_at_utc,
            "reason": self.reason,
            "windows": [dict(window) for window in self.windows],
        }


class SourceInfo(Protocol):
    """On-demand collector for a single source's metadata."""

    @property
    def source(self) -> str:
        """Return the source identifier used in observations."""
        ...

    def list_models(
        self,
        *,
        timeout_seconds: float = 15,
    ) -> ModelInventory:
        """List models from an official source endpoint."""
        ...

    def account_allowance(
        self,
        *,
        timeout_seconds: float = 15,
    ) -> AccountAllowance:
        """Read account allowance if the source exposes a supported endpoint."""
        ...


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class ResponseUsage:
    """Usage normalized from one provider response."""

    usage: UsageMetadata
    source: str
    observed_at_utc: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "observed_at_utc": self.observed_at_utc,
            "input_tokens": self.usage.input_tokens,
            "output_tokens": self.usage.output_tokens,
            "total_tokens": self.usage.total_tokens,
            "reported_cost_usd": self.usage.reported_cost_usd,
            "usage_source": self.usage.source.value,
        }
