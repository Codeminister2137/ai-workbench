"""Shared reasoning-metadata scrub: one key set for all delegating adapters."""

import pytest
from ai_provider.adapters.baseten import BasetenChatClient
from ai_provider.adapters.openai_compatible import (
    OpenAICompatibleChatClient,
    strip_reasoning_metadata,
)
from ai_provider.adapters.opencode_go import OpenCodeGoChatClient
from ai_provider.adapters.openrouter import OpenRouterFreeChatClient
from ai_provider.config import BackendConfig, ProviderKind

RAW = {
    "id": "chatcmpl-1",
    "reasoning_content": "secret chain",
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "reasoning": "drop me"},
    "choices": [
        {"message": {"content": "hi", "reasoning_details": {"x": 1}}},
        {"message": {"content": "yo"}},
    ],
}


def test_helper_strips_all_three_keys_recursively() -> None:
    cleaned = strip_reasoning_metadata(RAW)
    assert "reasoning_content" not in cleaned
    assert "reasoning" not in cleaned["usage"]
    assert "reasoning_details" not in cleaned["choices"][0]["message"]
    assert cleaned["usage"]["prompt_tokens"] == 10
    assert cleaned["usage"]["completion_tokens"] == 5
    assert cleaned["choices"][1]["message"]["content"] == "yo"
    assert len(cleaned) == 3


def test_helper_leaves_scalars_and_empty_containers() -> None:
    assert strip_reasoning_metadata("x") == "x"
    assert strip_reasoning_metadata(7) == 7
    assert strip_reasoning_metadata({}) == {}
    assert strip_reasoning_metadata([]) == []


def _client(cls, provider, base_url="https://probe.invalid/v1"):
    return cls(
        BackendConfig(
            provider=provider,
            model="probe-model",
            base_url=base_url,
            api_key="probe",
            timeout_seconds=5,
        )
    )


@pytest.mark.parametrize(
    ("cls", "provider", "base_url"),
    [
        (BasetenChatClient, ProviderKind.BASETEN, "https://probe.invalid/v1"),
        (OpenCodeGoChatClient, ProviderKind.OPENCODE_GO, "https://probe.invalid/v1"),
        (
            OpenRouterFreeChatClient,
            ProviderKind.OPENROUTER,
            "https://openrouter.ai/api/v1",
        ),
    ],
)
def test_delegating_adapters_share_exact_scrub(cls, provider, base_url) -> None:
    client = _client(cls, provider, base_url)
    assert client._safe_metadata(RAW) == strip_reasoning_metadata(RAW)


def test_base_adapter_keeps_identity_scrub() -> None:
    client = _client(OpenAICompatibleChatClient, ProviderKind.OPENAI)
    assert client._safe_metadata(RAW) == RAW
