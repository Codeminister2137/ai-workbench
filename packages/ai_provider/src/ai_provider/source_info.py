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


@dataclass(frozen=True, slots=True)
class EndpointAvailability:
    """Observed availability and performance of one provider endpoint.

    This is the shared, provider-neutral record shape for route availability.
    Every source normalizes into it so consumers never branch per source. The
    values are source-reported observations, not quality judgments: a healthy
    endpoint says nothing about the quality of the model behind it.

    Unknown values stay ``None`` rather than being inferred. ``uptime_*
    _percent`` are ratios in the range 0-100 as reported by the source,
    ``latency_seconds`` and ``throughput_tokens_per_second`` carry their unit
    in the name.
    """

    source: str
    model: str
    provider: str
    endpoint: str | None = None
    status: int | None = None
    uptime_1d_percent: float | None = None
    uptime_30m_percent: float | None = None
    latency_seconds: float | None = None
    throughput_tokens_per_second: float | None = None
    quantization: str | None = None
    service_tier: str | None = None
    context_length: int | None = None
    max_completion_tokens: int | None = None
    prices: dict[str, Any] | None = None
    supported_parameters: tuple[str, ...] | None = None
    observed_at_utc: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation without account identity."""

        return {
            "source": self.source,
            "model": self.model,
            "provider": self.provider,
            "endpoint": self.endpoint,
            "status": self.status,
            "uptime_1d_percent": self.uptime_1d_percent,
            "uptime_30m_percent": self.uptime_30m_percent,
            "latency_seconds": self.latency_seconds,
            "throughput_tokens_per_second": self.throughput_tokens_per_second,
            "quantization": self.quantization,
            "service_tier": self.service_tier,
            "context_length": self.context_length,
            "max_completion_tokens": self.max_completion_tokens,
            "prices": self.prices,
            "supported_parameters": (
                list(self.supported_parameters) if self.supported_parameters is not None else None
            ),
            "observed_at_utc": self.observed_at_utc,
        }


@dataclass(frozen=True, slots=True)
class EndpointInventory:
    """Endpoint availability observed for one model at one source.

    ``status`` is one of ``observed``, ``unavailable``, ``unknown``. An
    observation with no advertised endpoints is still ``observed``; the empty
    endpoint list is the finding, and ``reason`` says so.
    """

    status: str
    source: str
    model: str
    endpoints: tuple[EndpointAvailability, ...] = ()
    observed_at_utc: str | None = None
    reason: str | None = None

    def summary(self) -> dict[str, Any]:
        """Return a small availability summary over the observed endpoints."""

        uptimes = [
            endpoint.uptime_1d_percent
            for endpoint in self.endpoints
            if endpoint.uptime_1d_percent is not None
        ]
        contexts = [
            endpoint.context_length
            for endpoint in self.endpoints
            if endpoint.context_length is not None
        ]
        quantizations = sorted(
            {
                endpoint.quantization
                for endpoint in self.endpoints
                if endpoint.quantization is not None
            }
        )
        return {
            "provider_count": len({endpoint.provider for endpoint in self.endpoints}),
            "endpoint_count": len(self.endpoints),
            "best_uptime_1d_percent": max(uptimes) if uptimes else None,
            "worst_uptime_1d_percent": min(uptimes) if uptimes else None,
            "max_context_length": max(contexts) if contexts else None,
            "quantizations": quantizations,
        }

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation without account identity."""

        return {
            "status": self.status,
            "source": self.source,
            "model": self.model,
            "observed_at_utc": self.observed_at_utc,
            "reason": self.reason,
            "summary": self.summary(),
            "endpoints": [endpoint.to_dict() for endpoint in self.endpoints],
        }


@dataclass(frozen=True, slots=True)
class CapabilityScore:
    """One public benchmark result for one model under one agent scaffold.

    A published benchmark result is almost never a property of the model
    alone: the same model appears under several agent scaffolds with different
    scores. The scaffold is therefore part of the record, and a score must
    never be read as a model-only claim.

    ``model`` is the specific model identity the source publishes: a resolved
    model id where the source gives one, otherwise a comparable key derived
    from the published display name. ``model_display`` always keeps the
    source's own spelling. Both are recorded so the normalization stays
    auditable, and ``scale`` names the unit of ``score``.

    ``configuration`` holds the source's run configuration when it materially
    changes the result, such as a reasoning-effort level or an edit format:
    the same model scored under two configurations is two different
    observations. Aider records it as ``edit=<format>`` plus
    ``; reasoning=<level>`` when published, so repeated runs of one model stay
    distinguishable instead of appearing to contradict each other.

    The diagnostic fields record *how reliably* the run behaved, not just how
    often it was right: ``test_cases`` is the size of the published run,
    ``well_formed_percent`` the share of cases that produced a usable answer,
    ``syntax_errors`` and ``context_exhausted`` the counts a source reports for
    the two failure modes our own acceptance criteria care about, and the two
    token counters the run's consumption. A source that does not publish a
    field leaves it ``None`` rather than deriving it.

    These are published, dated, third-party observations. They are a selection
    prior, not acceptance evidence for this repository.
    """

    source: str
    benchmark: str
    split: str
    model: str
    model_display: str
    agent: str | None = None
    agent_org: str | None = None
    score: float | None = None
    scale: str | None = None
    configuration: str | None = None
    measured_at: str | None = None
    verified: bool | None = None
    cost_usd: float | None = None
    warning: str | None = None
    source_url: str | None = None
    observed_at_utc: str | None = None
    test_cases: int | None = None
    well_formed_percent: float | None = None
    syntax_errors: int | None = None
    context_exhausted: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation of one published result."""

        return {
            "source": self.source,
            "benchmark": self.benchmark,
            "split": self.split,
            "model": self.model,
            "model_display": self.model_display,
            "agent": self.agent,
            "agent_org": self.agent_org,
            "score": self.score,
            "scale": self.scale,
            "configuration": self.configuration,
            "measured_at": self.measured_at,
            "verified": self.verified,
            "cost_usd": self.cost_usd,
            "warning": self.warning,
            "source_url": self.source_url,
            "observed_at_utc": self.observed_at_utc,
            "test_cases": self.test_cases,
            "well_formed_percent": self.well_formed_percent,
            "syntax_errors": self.syntax_errors,
            "context_exhausted": self.context_exhausted,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }


@dataclass(frozen=True, slots=True)
class CapabilityPrior:
    """Published capability results collected for one benchmark split.

    ``status`` is one of ``observed``, ``unavailable``, ``unknown``. The
    records are safe to persist: each carries its source URL and the time it
    was observed, so a stored prior stays dated.
    """

    status: str
    source: str
    benchmark: str
    split: str
    scores: tuple[CapabilityScore, ...] = ()
    observed_at_utc: str | None = None
    reason: str | None = None
    source_url: str | None = None

    def summary(self) -> dict[str, Any]:
        """Return counts and the strongest published row for this split.

        The strongest row keeps its agent attached, so the number is never
        read as a model-only claim.
        """

        scored = [score for score in self.scores if score.score is not None]
        best = max(scored, key=lambda score: score.score or 0.0, default=None)
        return {
            "row_count": len(self.scores),
            "model_count": len({score.model for score in self.scores}),
            "agent_count": len({score.agent for score in self.scores if score.agent}),
            "best_score": best.score if best is not None else None,
            "best_score_model": best.model if best is not None else None,
            "best_score_agent": best.agent if best is not None else None,
        }

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation of the collected prior."""

        return {
            "status": self.status,
            "source": self.source,
            "benchmark": self.benchmark,
            "split": self.split,
            "observed_at_utc": self.observed_at_utc,
            "reason": self.reason,
            "source_url": self.source_url,
            "summary": self.summary(),
            "scores": [score.to_dict() for score in self.scores],
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
