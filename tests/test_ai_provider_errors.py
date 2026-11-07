"""Shared HTTP-to-provider error mapping (one mapping for all adapters)."""

from urllib.error import HTTPError

import pytest
from ai_provider.errors import ProviderErrorCategory, http_error_to_provider_error


def _http_error(code: int) -> HTTPError:
    return HTTPError("https://provider.example/v1", code, "reason", {}, None)


@pytest.mark.parametrize(
    ("code", "category", "retryable"),
    [
        (401, ProviderErrorCategory.AUTHENTICATION, False),
        (403, ProviderErrorCategory.AUTHENTICATION, False),
        (429, ProviderErrorCategory.RATE_LIMIT, True),
        (500, ProviderErrorCategory.RETRYABLE, True),
        (503, ProviderErrorCategory.RETRYABLE, True),
        (400, ProviderErrorCategory.NON_RETRYABLE, False),
        (404, ProviderErrorCategory.NON_RETRYABLE, False),
    ],
)
def test_status_to_category_mapping(code, category, retryable) -> None:
    err = http_error_to_provider_error(_http_error(code), provider="p", api_label="X")
    assert err.category is category
    assert err.retryable is retryable


def test_message_provider_and_raw_passthrough() -> None:
    exc = _http_error(429)
    err = http_error_to_provider_error(exc, provider="acme", api_label="Chat")
    assert str(err) == "Chat provider returned HTTP 429."
    assert err.provider == "acme"
    assert err.raw_error is exc
