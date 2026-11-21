"""Shared HTTP-to-provider error mapping (one mapping for all adapters)."""

import json
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError

import pytest
from ai_provider.errors import ProviderErrorCategory, http_error_to_provider_error


def _http_error(code: int) -> HTTPError:
    return HTTPError("https://provider.example/v1", code, "reason", Message(), None)


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


def _body_error(body: bytes) -> HTTPError:
    return HTTPError("https://provider.example/v1", 400, "reason", Message(), BytesIO(body))


def test_json_error_detail_is_single_line() -> None:
    exc = _body_error(
        json.dumps({"error": {"message": "unsupported\nparameter", "code": "bad"}}).encode()
    )
    err = http_error_to_provider_error(exc, provider="p", api_label="Chat")
    assert "unsupported" in str(err)
    assert "parameter" in str(err)
    assert "bad" in str(err)
    assert "\n" not in str(err)
    assert err.raw_error is exc


@pytest.mark.parametrize("json_body", [False, True])
def test_oversized_detail_is_truncated(json_body: bool) -> None:
    body = "x" * 2000
    if json_body:
        body = json.dumps({"error": {"message": body}})
    err = http_error_to_provider_error(_body_error(body.encode()), provider="p", api_label="X")
    detail = str(err).split("Response detail: ")[1]
    assert len(detail) == 500
    assert detail.endswith("...")


@pytest.mark.parametrize(
    "sensitive",
    [
        "sk-fixture-credential-123456789",
        "Bearer fixture-credential-123456789",
        "api_key=fixture-credential-123456789",
        "password=fixture-credential-123456789",
        "prompt: private fixture text",
    ],
)
def test_sensitive_error_payload_is_withheld(sensitive: str) -> None:
    body = json.dumps({"error": {"message": sensitive}}).encode()
    err = http_error_to_provider_error(_body_error(body), provider="p", api_label="X")
    assert sensitive not in str(err)
    assert "withheld" in str(err)


def test_known_credentials_are_checked_before_truncation(monkeypatch) -> None:
    secret = "opaque-fixture-credential-123456789"
    monkeypatch.setenv("FIXTURE_API_KEY", secret)
    body = json.dumps({"error": {"message": "x" * 600 + secret}}).encode()
    err = http_error_to_provider_error(_body_error(body), provider="p", api_label="X")
    assert "withheld" in str(err)
    assert secret not in str(err)


def test_explicit_credential_and_echoed_request_are_withheld() -> None:
    for body, credentials in [
        ({"error": {"message": "opaque-credential"}}, ("opaque-credential",)),
        ({"error": {"message": "bad"}, "request": {"messages": ["private text"]}}, ()),
    ]:
        err = http_error_to_provider_error(
            _body_error(json.dumps(body).encode()),
            provider="p",
            api_label="X",
            credentials=credentials,
        )
        assert "withheld" in str(err)
        assert "private text" not in str(err)


def test_failed_body_read_preserves_status() -> None:
    class BrokenBody(BytesIO):
        def read(self, size: int | None = -1):
            raise OSError("private read failure")

    exc = HTTPError("https://provider.example", 400, "reason", Message(), BrokenBody())
    err = http_error_to_provider_error(exc, provider="p", api_label="X")
    assert str(err) == "X provider returned HTTP 400."


@pytest.mark.parametrize("value", ["opaque-credential", "sk-fixture-key", "prompt: private text"])
def test_json_unicode_escapes_cannot_hide_sensitive_values(value: str) -> None:
    escaped = "".join(f"\\u{ord(char):04x}" for char in value)
    body = ('{"error":{"message":"' + escaped + '"}}').encode()
    err = http_error_to_provider_error(
        _body_error(body), provider="p", api_label="X", credentials=("opaque-credential",)
    )
    assert "withheld" in str(err)
    assert value not in str(err)


@pytest.mark.parametrize("body", [b'{"error":', b'{"error": {"message": []}}', b"[]"])
def test_invalid_error_envelopes_preserve_status(body: bytes) -> None:
    err = http_error_to_provider_error(_body_error(body), provider="p", api_label="X")
    assert str(err) == "X provider returned HTTP 400."


def test_diagnostic_read_is_bounded() -> None:
    class CheckedBody(BytesIO):
        def read(self, size: int | None = -1):
            assert size == 16_385
            return super().read(size)

    exc = HTTPError(
        "https://provider.example", 400, "reason", Message(), CheckedBody(b"x" * 100_000)
    )
    err = http_error_to_provider_error(exc, provider="p", api_label="X")
    assert str(err).endswith("...")
