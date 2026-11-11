"""Provider error types exposed to callers."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ai_provider.contracts import AIMessage


class ProviderErrorCategory(StrEnum):
    """Stable categories callers can use for provider error handling."""

    CONFIGURATION = "configuration"
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    USAGE_LIMIT = "usage_limit"
    TIMEOUT = "timeout"
    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"
    PRIVACY_POLICY = "privacy_policy"
    UNKNOWN = "unknown"


class ProviderError(RuntimeError):
    """Provider-layer exception with normalized category metadata."""

    def __init__(
        self,
        message: str,
        *,
        category: ProviderErrorCategory = ProviderErrorCategory.UNKNOWN,
        retryable: bool = False,
        provider: str | None = None,
        raw_error: object | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.retryable = retryable
        self.provider = provider
        self.raw_error = raw_error
        self.partial_messages: tuple[AIMessage, ...] = ()
        # Partial tool effects captured before the failure. Any-typed:
        # the provider layer cannot import ai_agent's ToolResult.
        self.tool_results: tuple[Any, ...] = ()


def http_error_to_provider_error(exc, *, provider: str, api_label: str) -> ProviderError:
    """Map an HTTPError to a categorized ProviderError (shared adapter helper).

    Status mapping is provider-agnostic; only the provider id and the API
    label in the message vary per adapter. `exc` needs a numeric `code`.
    """
    if exc.code in {401, 403}:
        category = ProviderErrorCategory.AUTHENTICATION
    elif exc.code == 429:
        category = ProviderErrorCategory.RATE_LIMIT
    elif 500 <= exc.code < 600:
        category = ProviderErrorCategory.RETRYABLE
    else:
        category = ProviderErrorCategory.NON_RETRYABLE
    return ProviderError(
        f"{api_label} provider returned HTTP {exc.code}.",
        category=category,
        retryable=category in {ProviderErrorCategory.RATE_LIMIT, ProviderErrorCategory.RETRYABLE},
        provider=provider,
        raw_error=exc,
    )


class ToolCallFormatError(ProviderError):
    """Known malformed generated arguments, before any call in that response runs.

    This permits model feedback, not transport retry or replay of earlier tools.
    Adapters must not use this signal for unknown failures or uncertain effects.
    """

    def __init__(self, *, provider: str) -> None:
        super().__init__(
            "Model returned malformed tool arguments; no executable call was delivered.",
            category=ProviderErrorCategory.NON_RETRYABLE,
            provider=provider,
        )


class TruncatedOutputError(ProviderError):
    """Model stopped on length; the returned text is a partial prefix.

    Retryable with a larger output budget (see thinker_output_budget),
    never by reusing the partial text as complete.
    """

    def __init__(self, *, provider: str, budget: int | None = None) -> None:
        detail = f" (budget was {budget} tokens)" if budget else ""
        super().__init__(
            f"Model output truncated on length{detail}; retry with a larger budget.",
            category=ProviderErrorCategory.RETRYABLE,
            provider=provider,
        )
