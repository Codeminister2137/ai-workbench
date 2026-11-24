"""Provider error types exposed to callers."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
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


_SAFE_TOKEN = re.compile(r"[A-Za-z0-9_.-]{1,64}")

_SENSITIVE_TOKEN_PARTS = (
    "sk-",
    "api",
    "key",
    "secret",
    "token",
    "password",
    "bearer",
    "auth",
    "private",
    "credential",
)
"""Substrings that disqualify an otherwise well-shaped token.

An identifier-shaped value can still be a credential echo (observed:
provider-style secret in an error code field). Dropped tokens lose no
classification the status code does not already carry (auth failures
arrive as 401/403; this channel exists for 400-subclassification whose
codes never contain these words).
"""


def _safe_envelope_tokens(payload: object) -> dict[str, str]:
    """Validated error type/code tokens; safe even when the message is not.

    Only short identifier-shaped provider tokens without sensitive
    substrings pass; anything else is dropped so a hostile or echoing
    envelope cannot smuggle content out through the classification
    channel.
    """
    if not isinstance(payload, dict):
        return {}
    error = payload.get("error")
    if not isinstance(error, dict):
        return {}
    tokens = {}
    for key in ("type", "code"):
        value = error.get(key)
        if not isinstance(value, str) or not _SAFE_TOKEN.fullmatch(value):
            continue
        lowered = value.lower()
        if any(part in lowered for part in _SENSITIVE_TOKEN_PARTS):
            continue
        tokens[key] = value
    return tokens


def _http_error_detail(exc, *, credentials: Iterable[str | None]) -> tuple[str, dict[str, str]]:
    """Expose bounded error diagnostics, failing closed on sensitive payloads.

    Never inspect request objects, headers or exception reprs. JSON response
    envelopes contribute only error message/type/code, not echoed request fields.
    Returns (detail, safe_tokens): validated type/code tokens survive even a
    withheld message so verdict classification keeps working on scrubbed errors.
    """
    from ai_provider.credential_guard import contains_credentials

    sensitive = re.compile(
        r"(?i)(?:bearer\s+|\bsk-[\w-]+|api[_ -]?key|authorization|"
        r"password|secret|\btoken\b|access_token|private_key|"
        r"\bprompt\b|\bmessages\b|\brequest\b|\binput\b|\bcontent\b)"
    )
    credentials = tuple(credentials)
    try:
        body = exc.read(16_385)
        if not body:
            return "", {}
        text = body.decode("utf-8", errors="replace")
        tokens: dict[str, str] = {}
        payload: object = None
        if text.lstrip().startswith(("{", "[")):
            # A partial JSON document cannot be safely filtered for echoed inputs.
            if len(body) > 16_384:
                return "[response detail withheld]", {}
            try:
                payload = json.loads(text)
            except ValueError:
                return "", {}
            tokens = _safe_envelope_tokens(payload)

        def _withheld() -> tuple[str, dict[str, str]]:
            if tokens:
                tagged = " ".join(f"{key}={value}" for key, value in tokens.items())
                return f"[response detail withheld: {tagged}]", tokens
            return "[response detail withheld]", tokens

        if contains_credentials(text, extra=credentials) or sensitive.search(text):
            return _withheld()
        if payload is not None:
            # JSON escapes can conceal credential values and sensitive field names.
            decoded = json.dumps(payload, ensure_ascii=False)
            if contains_credentials(payload, extra=credentials) or sensitive.search(decoded):
                return _withheld()
            if not isinstance(payload, dict) or "error" not in payload:
                return "", {}
            error = payload["error"]
            if isinstance(error, dict):
                error = {key: error[key] for key in ("message", "type", "code") if key in error}
                if any(not isinstance(value, (str, int, type(None))) for value in error.values()):
                    return "", {}
            elif not isinstance(error, str):
                return "", {}
            text = json.dumps(error, ensure_ascii=False)
        text = " ".join(text.split())
        detail = text if len(text) <= 500 else text[:497] + "..."
        return detail, tokens
    except Exception:
        # A diagnostic read/parse failure must not replace the original status.
        return "", {}


def http_error_to_provider_error(
    exc, *, provider: str, api_label: str, credentials: Iterable[str | None] = ()
) -> ProviderError:
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
    detail, tokens = _http_error_detail(exc, credentials=credentials)
    message = f"{api_label} provider returned HTTP {exc.code}."
    if detail:
        message += f" Response detail: {detail}"
    if exc.code == 400 and (
        tokens.get("code") == "context_length_exceeded"
        or tokens.get("type") == "context_length_exceeded"
    ):
        # The request fits nowhere on this route, but a longer-context
        # route may serve it: capability reroute, not terminal failure.
        # The marker sentence is the FallbackSession capability signal.
        category = ProviderErrorCategory.RETRYABLE
        message += " Route to a longer-context model."
    return ProviderError(
        message,
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
