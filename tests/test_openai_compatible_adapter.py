from __future__ import annotations

import json
from typing import Any

import pytest
from ai_provider import (
    AIMessage,
    AIRequest,
    AIStreamDelta,
    AIStreamFinal,
    BackendLocation,
    FinishReason,
    MessageRole,
    OpenAICompatibleChatClient,
    PrivacyClass,
    ProviderError,
    ProviderErrorCategory,
    ProviderKind,
    UsageSource,
)
from ai_provider.config import BackendConfig


class FakeHttpResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self) -> FakeHttpResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class FakeStreamingHttpResponse:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = payloads

    def __enter__(self) -> FakeStreamingHttpResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def __iter__(self):
        for payload in self.payloads:
            yield b"data: " + json.dumps(payload).encode("utf-8") + b"\n\n"
        yield b"data: [DONE]\n\n"


def test_openai_compatible_adapter_posts_chat_completion_and_normalizes_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> FakeHttpResponse:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["authorization"] = request.get_header("Authorization")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeHttpResponse(
            {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Hosted answer"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                    "cost": 0.0002,
                },
            }
        )

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", fake_urlopen)

    client = OpenAICompatibleChatClient(
        BackendConfig(
            provider=ProviderKind.REQUESTY,
            model="openai/gpt-5.1",
            api_key="requesty-key",
            timeout_seconds=9.0,
        )
    )
    response = client.complete(
        AIRequest(
            messages=(
                AIMessage(MessageRole.SYSTEM, "Be precise."),
                AIMessage(MessageRole.USER, "Say hello."),
            ),
            temperature=0.1,
            max_output_tokens=50,
            privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        )
    )

    assert captured["url"] == "https://router.requesty.ai/v1/chat/completions"
    assert captured["timeout"] == 9.0
    assert captured["authorization"] == "Bearer requesty-key"
    assert captured["body"] == {
        "model": "openai/gpt-5.1",
        "messages": [
            {"role": "system", "content": "Be precise."},
            {"role": "user", "content": "Say hello."},
        ],
        "stream": False,
        "temperature": 0.1,
        "max_tokens": 50,
    }
    assert response.message.content == "Hosted answer"
    assert response.backend.provider == "requesty"
    assert response.backend.location is BackendLocation.EXTERNAL
    assert response.usage.source is UsageSource.PROVIDER_REPORTED
    assert response.usage.input_tokens == 11
    assert response.usage.output_tokens == 7
    assert response.usage.total_tokens == 18
    assert response.raw_metadata["usage"]["cost"] == 0.0002
    assert response.finish_reason is FinishReason.STOP


def test_openai_compatible_adapter_uses_openai_default_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> FakeHttpResponse:
        captured["url"] = request.full_url
        return FakeHttpResponse(
            {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
        )

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", fake_urlopen)

    client = OpenAICompatibleChatClient(
        BackendConfig(provider=ProviderKind.OPENAI, model="gpt-5.1", api_key="openai-key")
    )
    client.complete(
        AIRequest(
            messages=(AIMessage(MessageRole.USER, "Hello"),),
            privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        )
    )

    assert captured["url"] == "https://api.openai.com/v1/chat/completions"


def test_openai_compatible_adapter_enforces_external_privacy_before_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Any, timeout: float) -> FakeHttpResponse:
        raise AssertionError("HTTP should not be called")

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", fake_urlopen)

    client = OpenAICompatibleChatClient(
        BackendConfig(provider=ProviderKind.OPENAI, model="gpt-5.1", api_key="openai-key")
    )

    with pytest.raises(ProviderError) as error:
        client.complete(AIRequest(messages=(AIMessage(MessageRole.USER, "Private"),)))

    assert error.value.category is ProviderErrorCategory.PRIVACY_POLICY


def test_openai_compatible_adapter_requires_api_key() -> None:
    client = OpenAICompatibleChatClient(
        BackendConfig(provider=ProviderKind.OPENAI, model="gpt-5.1")
    )

    with pytest.raises(ProviderError) as error:
        client.complete(
            AIRequest(
                messages=(AIMessage(MessageRole.USER, "Hello"),),
                privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
            )
        )

    assert error.value.category is ProviderErrorCategory.CONFIGURATION


def test_openai_compatible_adapter_reads_provider_api_key_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> FakeHttpResponse:
        captured["authorization"] = request.get_header("Authorization")
        return FakeHttpResponse(
            {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
        )

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", fake_urlopen)
    monkeypatch.setenv("OPENAI_API_KEY", "env-openai-key")

    client = OpenAICompatibleChatClient(
        BackendConfig(provider=ProviderKind.OPENAI, model="gpt-5.1")
    )
    client.complete(
        AIRequest(
            messages=(AIMessage(MessageRole.USER, "Hello"),),
            privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        )
    )

    assert captured["authorization"] == "Bearer env-openai-key"


def test_openai_compatible_adapter_streams_deltas_and_final_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> FakeStreamingHttpResponse:
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeStreamingHttpResponse(
            [
                {"choices": [{"delta": {"content": "Hel"}, "finish_reason": None}]},
                {"choices": [{"delta": {"content": "lo"}, "finish_reason": None}]},
                {
                    "choices": [{"delta": {}, "finish_reason": "stop"}],
                    "usage": {
                        "prompt_tokens": 3,
                        "completion_tokens": 2,
                        "total_tokens": 5,
                    },
                },
            ]
        )

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", fake_urlopen)

    client = OpenAICompatibleChatClient(
        BackendConfig(provider=ProviderKind.REQUESTY, model="openai/gpt-5.1", api_key="key")
    )
    events = list(
        client.stream(
            AIRequest(
                messages=(AIMessage(MessageRole.USER, "Hello"),),
                privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
            )
        )
    )

    assert captured["body"]["stream"] is True
    assert [event.content for event in events if isinstance(event, AIStreamDelta)] == [
        "Hel",
        "lo",
    ]
    final = events[-1]
    assert isinstance(final, AIStreamFinal)
    assert final.response.message.content == "Hello"
    assert final.response.backend.provider == "requesty"
    assert final.response.usage.input_tokens == 3
    assert final.response.usage.output_tokens == 2
    assert final.response.finish_reason is FinishReason.STOP
