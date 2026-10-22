"""Free-only OpenRouter transport using the shared Chat Completions protocol.

Prices and account capacity are refreshed before every model call. No key
metadata is retained, no gateway model fallback or paid plugins are requested,
and missing evidence refuses inference. This is admission evidence, not quality.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

from ai_provider.adapters.openai_compatible import OpenAICompatibleChatClient
from ai_provider.config import ProviderKind
from ai_provider.contracts import (
    AIMessage,
    AIRequest,
    MessageRole,
    PrivacyClass,
    ProviderContinuation,
)
from ai_provider.errors import ProviderError, ProviderErrorCategory
from ai_provider.http_transport import urlopen
from ai_provider.turn_usage import observe_usage

BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterFreeChatClient(OpenAICompatibleChatClient):
    """Distinct OpenRouter identity with mandatory free and privacy guards."""

    def __post_init__(self) -> None:
        if self.config.provider is not ProviderKind.OPENROUTER or self.base_url != BASE_URL:
            raise self._refusal("OpenRouter free access requires its official API endpoint.")

    def _continuation(self, message: dict[str, Any], model: str) -> ProviderContinuation | None:
        details = message.get("reasoning_details")
        reasoning = message.get("reasoning")
        if isinstance(details, list) and details:
            payload = {"reasoning_details": deepcopy(details)}
        elif isinstance(reasoning, str) and reasoning:
            payload = {"reasoning": reasoning}
        else:
            return None
        return ProviderContinuation(self.backend.provider, model, self.base_url, payload)

    def _message_payload(self, message: AIMessage, model: str) -> dict[str, Any]:
        payload = super()._message_payload(message, model)
        state = message.continuation
        if (
            message.role is MessageRole.ASSISTANT
            and state is not None
            and (state.provider, state.model, state.base_url)
            == (self.backend.provider, model, self.base_url)
        ):
            # Whitelist fields; adapter-owned state cannot replace role/content/tools.
            for key in ("reasoning_details", "reasoning"):
                if key in state.payload:
                    payload[key] = deepcopy(state.payload[key])
        return payload

    def _collect_continuation(self, state: dict[str, Any], delta: dict[str, Any]) -> None:
        reasoning = delta.get("reasoning")
        if isinstance(reasoning, str):
            state["reasoning"] = state.get("reasoning", "") + reasoning
        details = delta.get("reasoning_details")
        if not isinstance(details, list):
            return
        blocks = state.setdefault("reasoning_details", [])
        for fragment in details:
            if not isinstance(fragment, dict):
                raise self._refusal("Invalid streamed reasoning detail; continuation unavailable.")
            index = fragment.get("index")
            previous = next(
                (item for item in blocks if index is not None and item.get("index") == index), None
            )
            if previous is None:
                blocks.append(deepcopy(fragment))
                continue
            for key, value in fragment.items():
                if key in {"text", "data", "signature"} and isinstance(value, str):
                    previous[key] = previous.get(key, "") + value
                elif key in previous and previous[key] != value:
                    raise self._refusal("Inconsistent streamed reasoning detail.")
                else:
                    previous[key] = deepcopy(value)

    def _safe_metadata(self, raw: dict[str, Any]) -> dict[str, Any]:
        def clean(value: Any) -> Any:
            if isinstance(value, dict):
                return {
                    key: clean(item)
                    for key, item in value.items()
                    if key not in {"reasoning", "reasoning_details", "reasoning_content"}
                }
            if isinstance(value, list):
                return [clean(item) for item in value]
            return value

        return clean(raw)

    def _refusal(self, message: str) -> ProviderError:
        return ProviderError(
            message,
            category=ProviderErrorCategory.CONFIGURATION,
            provider=self.config.provider.value,
        )

    def _metadata(self, path: str) -> dict[str, Any]:
        request = Request(f"{self.base_url}/{path}", headers=self._headers(), method="GET")
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise self._http_error(exc) from exc
        except (URLError, TimeoutError, ValueError, UnicodeDecodeError) as exc:
            raise self._refusal(
                "Could not verify OpenRouter metadata; inference was not sent."
            ) from exc
        if not isinstance(raw, dict):
            raise self._refusal("Invalid OpenRouter metadata; inference was not sent.")
        return raw

    def _verify_request_model(self, request: AIRequest) -> None:
        # Low-risk may still be private. Only a caller's explicit full-input
        # attestation permits uncertain training/retention of public material.
        public_or_synthetic = (
            request.privacy_class is PrivacyClass.PUBLIC_OR_LOW_RISK
            and request.metadata.get("public_or_synthetic") is True
        )
        self._verify_free_model(
            request.model or self.config.model, public_or_synthetic=public_or_synthetic
        )

    def _verify_free_model(self, model: str, *, public_or_synthetic: bool = False) -> None:
        # A named variant fixes model identity; gateway routers/auto aliases do not.
        if not model.endswith(":free") or model.startswith("openrouter/"):
            raise self._refusal("OpenRouter requires an exact named :free model.")
        rows = self._metadata("models").get("data")
        matches = (
            [row for row in rows if isinstance(row, dict) and row.get("id") == model]
            if isinstance(rows, list)
            else []
        )
        if len(matches) != 1 or not _free_pricing(matches[0].get("pricing")):
            raise self._refusal("OpenRouter model is not verified free; inference was not sent.")
        parameters = matches[0].get("supported_parameters")
        if not isinstance(parameters, list) or "tools" not in parameters:
            raise self._refusal("OpenRouter tool support is unverified; inference was not sent.")
        self._verify_free_quota(public_or_synthetic=public_or_synthetic)

    def _verify_free_quota(self, *, public_or_synthetic: bool = False) -> None:
        raw = self._metadata("key").get("data")
        # Pricing excludes data-policy routing from Free, while routing docs are
        # unqualified. Never assume the requested privacy filter is enforced there.
        if not public_or_synthetic and (
            not isinstance(raw, dict) or raw.get("is_free_tier") is not False
        ):
            raise self._refusal(
                "OpenRouter Free-plan privacy-filter entitlement is unverified; "
                "inference was not sent. Resolve the documentation conflict first."
            )
        quota = raw.get("free_model_daily_requests") if isinstance(raw, dict) else None
        if not isinstance(quota, dict):
            raise self._refusal("OpenRouter free quota is unknown; inference was not sent.")
        used, limit, remaining = (quota.get(name) for name in ("used", "limit", "remaining"))
        if (
            type(used) is not int
            or type(limit) is not int
            or type(remaining) is not int
            or min(used, limit, remaining) < 0
            or used > limit
            or remaining != limit - used
        ):
            raise self._refusal("OpenRouter free quota is invalid; inference was not sent.")
        if remaining == 0:
            raise ProviderError(
                "OpenRouter daily free allowance is exhausted; inference was not sent.",
                category=ProviderErrorCategory.USAGE_LIMIT,
                provider=self.config.provider.value,
                retryable=False,
            )

    def _chat_payload(self, request: AIRequest, *, stream: bool) -> dict[str, Any]:
        # The request-aware override enforces admission even for direct configs
        # which omit require_free_model; base payload construction calls it once.
        payload = super()._chat_payload(request, stream=stream)
        payload["provider"] = {
            "require_parameters": True,
            "data_collection": "deny",
            "max_price": {"prompt": 0, "completion": 0, "request": 0, "image": 0},
        }
        return payload

    def _post_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw = super()._post_chat(payload)
        if isinstance(raw, dict):
            observe_usage(self._usage_from_response(raw))
        self._check_error(raw)
        return raw

    def _http_error(self, exc: HTTPError) -> ProviderError:
        if exc.code == 402:
            return ProviderError(
                "OpenRouter account access is blocked by a credit limit; no paid retry.",
                category=ProviderErrorCategory.USAGE_LIMIT,
                provider=self.config.provider.value,
            )
        return super()._http_error(exc)

    def _stream_chat(self, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
        finished: object = None
        for raw in super()._stream_chat(payload):
            if isinstance(raw.get("usage"), dict):
                observe_usage(self._usage_from_response(raw))
            self._check_error(raw)
            choices = raw.get("choices")
            if isinstance(choices, list) and len(choices) == 1:
                choice = choices[0]
                if isinstance(choice, dict):
                    # OpenRouter's final usage receipt repeats the finish reason
                    # with an empty delta. Do not admit new content/tool fragments.
                    if (
                        finished is not None
                        and choice.get("finish_reason") == finished
                        and choice.get("delta") == {}
                        and isinstance(raw.get("usage"), dict)
                    ):
                        yield {**raw, "choices": []}
                        continue
                    if choice.get("finish_reason") is not None:
                        finished = choice["finish_reason"]
            yield raw

    def _check_error(self, raw: object) -> None:
        if not isinstance(raw, dict):
            raise ProviderError(
                "Invalid OpenRouter response.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider=self.config.provider.value,
            )
        error = raw.get("error")
        if error is None:
            choices = raw.get("choices")
            if isinstance(choices, list):
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    error = choice.get("error")
                    if error is not None:
                        break
                    if choice.get("finish_reason") == "error":
                        # An error finish without details still refuses partial output.
                        error = {}
                        break
            if error is None:
                return
        code = error.get("code") if isinstance(error, dict) else None
        category = (
            ProviderErrorCategory.AUTHENTICATION
            if code in (401, 403)
            else ProviderErrorCategory.USAGE_LIMIT
            if code == 402
            else ProviderErrorCategory.RATE_LIMIT
            if code == 429
            else ProviderErrorCategory.RETRYABLE
            if type(code) is int and 500 <= code < 600
            else ProviderErrorCategory.NON_RETRYABLE
        )
        # Do not propagate remote error text which can contain echoed input.
        raise ProviderError(
            "OpenRouter returned an error response.",
            category=category,
            provider=self.config.provider.value,
            retryable=category
            in {ProviderErrorCategory.RATE_LIMIT, ProviderErrorCategory.RETRYABLE},
        )


def _free_pricing(raw: object) -> bool:
    """Require prompt/completion and every advertised additional price to be zero."""
    if not isinstance(raw, dict) or not {"prompt", "completion"}.issubset(raw):
        return False
    for value in raw.values():
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            return False
        try:
            price = Decimal(str(value))
        except InvalidOperation:
            return False
        if not price.is_finite() or price != 0:
            return False
    return True
