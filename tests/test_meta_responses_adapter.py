"""Meta Model API adapter tests; no network or credentials."""

from __future__ import annotations

import json
from io import BytesIO

import pytest
from ai_provider import (
    AIMessage,
    AIRequest,
    AIStreamDelta,
    AIStreamFinal,
    BackendConfig,
    MessageRole,
    PrivacyClass,
    ProviderError,
    ProviderKind,
    create_chat_client,
)
from ai_provider.adapters.meta import MetaResponsesChatClient


class Response(BytesIO):
    status = 200

    def __init__(self, raw):
        if isinstance(raw, bytes):
            payload = raw
        elif isinstance(raw, list):
            lines = (f"data: {json.dumps(row)}\n".encode() for row in raw)
            payload = b"".join(lines) + b"data: [DONE]\n"
        else:
            payload = json.dumps(raw).encode()
        super().__init__(payload)


def _completed(text: str = "hello", *, input_tokens: int = 5, output_tokens: int = 2):
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    }


def test_factory_routes_meta_to_responses_client():
    client = create_chat_client(
        BackendConfig(provider=ProviderKind.META, model="muse-spark-1.3", api_key="test")
    )

    assert isinstance(client, MetaResponsesChatClient)


def test_meta_client_rejects_wrong_provider():
    with pytest.raises(ProviderError, match="Meta responses client requires"):
        MetaResponsesChatClient(
            BackendConfig(provider=ProviderKind.OPENAI, model="muse-spark-1.3", api_key="test")
        )


def test_meta_client_rejects_non_muse_model():
    with pytest.raises(ProviderError, match="must start with 'muse-'"):
        MetaResponsesChatClient(
            BackendConfig(provider=ProviderKind.META, model="gpt-5.1", api_key="test")
        )


def test_meta_client_refuses_contributor_variants():
    with pytest.raises(ProviderError, match="Contributor variants train on request data"):
        MetaResponsesChatClient(
            BackendConfig(
                provider=ProviderKind.META,
                model="muse-spark-1.3-contributor",
                api_key="test",
            )
        )


def test_meta_client_refuses_per_request_contributor_override():
    client = MetaResponsesChatClient(
        BackendConfig(provider=ProviderKind.META, model="muse-spark-1.3", api_key="test")
    )

    with pytest.raises(ProviderError, match="Contributor variants train on request data"):
        client.complete(
            AIRequest(
                messages=(AIMessage(MessageRole.USER, "Hi"),),
                model="muse-spark-1.3-contributor",
                privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
            )
        )


def test_meta_client_posts_to_meta_endpoint_without_storage(monkeypatch):
    captured = {}

    def send(request, *, timeout):
        captured["payload"] = json.loads(request.data.decode())
        captured["url"] = request.full_url
        headers = {key.lower(): value for key, value in request.headers.items()}
        assert headers["authorization"] == "Bearer test-key"
        return Response(_completed())

    monkeypatch.setattr("ai_provider.adapters.openai_responses.urlopen", send)

    client = MetaResponsesChatClient(
        BackendConfig(provider=ProviderKind.META, model="muse-spark-1.3", api_key="test-key")
    )
    response = client.complete(
        AIRequest(
            messages=(AIMessage(MessageRole.USER, "Hi"),),
            privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
            max_output_tokens=64,
        )
    )

    assert captured["url"] == "https://api.meta.ai/v1/responses"
    payload = captured["payload"]
    assert payload["model"] == "muse-spark-1.3"
    assert payload["store"] is False
    assert payload["max_output_tokens"] == 64
    assert payload["input"] == [{"role": "user", "content": "Hi"}]
    assert response.message.content == "hello"
    assert response.backend.provider == "meta"
    assert response.backend.location == "external"
    assert response.usage.input_tokens == 5
    assert response.usage.output_tokens == 2


def test_meta_client_honours_base_url_override(monkeypatch):
    captured = {}

    def send(request, *, timeout):
        captured["url"] = request.full_url
        return Response(_completed())

    monkeypatch.setattr("ai_provider.adapters.openai_responses.urlopen", send)

    client = MetaResponsesChatClient(
        BackendConfig(
            provider=ProviderKind.META,
            model="muse-spark-1.3",
            base_url="https://meta.internal.example/v1/",
            api_key="test-key",
        )
    )
    client.complete(
        AIRequest(
            messages=(AIMessage(MessageRole.USER, "Hi"),),
            privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        )
    )

    assert captured["url"] == "https://meta.internal.example/v1/responses"


def test_meta_client_streams_text_deltas(monkeypatch):
    def send(request, *, timeout):
        return Response(
            [
                {"type": "response.output_text.delta", "delta": "hel"},
                {"type": "response.output_text.delta", "delta": "lo"},
                {"type": "response.completed", "response": _completed("hello")},
            ]
        )

    monkeypatch.setattr("ai_provider.adapters.openai_responses.urlopen", send)

    client = MetaResponsesChatClient(
        BackendConfig(provider=ProviderKind.META, model="muse-spark-1.3", api_key="test-key")
    )
    events = list(
        client.stream(
            AIRequest(
                messages=(AIMessage(MessageRole.USER, "Hi"),),
                privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
            )
        )
    )

    deltas = [event.content for event in events if isinstance(event, AIStreamDelta)]
    assert deltas == ["hel", "lo"]
    assert isinstance(events[-1], AIStreamFinal)
    assert events[-1].response.message.content == "hello"


def test_meta_client_refuses_local_only_privacy_class(monkeypatch):
    def send(request, *, timeout):  # pragma: no cover - must never be called
        raise AssertionError("local-only request must not reach Meta")

    monkeypatch.setattr("ai_provider.adapters.openai_responses.urlopen", send)

    client = MetaResponsesChatClient(
        BackendConfig(provider=ProviderKind.META, model="muse-spark-1.3", api_key="test-key")
    )

    with pytest.raises(ProviderError, match="Local-only requests"):
        client.complete(
            AIRequest(
                messages=(AIMessage(MessageRole.USER, "Hi"),),
                privacy_class=PrivacyClass.LOCAL_ONLY,
            )
        )
