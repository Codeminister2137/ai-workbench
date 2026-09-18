from __future__ import annotations

from enum import StrEnum


class ProviderErrorCategory(StrEnum):
    CONFIGURATION = "configuration"
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"
    PRIVACY_POLICY = "privacy_policy"
    UNKNOWN = "unknown"


class ProviderError(RuntimeError):
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
