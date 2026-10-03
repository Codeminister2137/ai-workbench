"""Provider error types exposed to callers."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

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
