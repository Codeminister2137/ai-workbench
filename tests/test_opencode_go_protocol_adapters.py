"""OpenCode Go Responses/Messages adapter tests; no network or credentials."""

from __future__ import annotations

import json
from io import BytesIO

import pytest
from ai_provider import (
    AIMessage,
    AIRequest,
    BackendConfig,
    MessageRole,
    PrivacyClass,
    ProviderKind,
    create_chat_client,
)
from ai_provider.adapters.anthropic_messages import AnthropicMessagesChatClient
from ai_provider.adapters.openai_responses import OpenAIResponsesChatClient
from ai_provider.adapters.opencode_go import OpenCodeGoChatClient
from ai_provider.adapters.opencode_go_messages import OpenCodeGoMessagesClient
from ai_provider.adapters.opencode_go_responses import OpenCodeGoResponsesClient
from ai_provider.errors import ProviderError


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


def test_factory_routes_chat_models_to_chat_client():
    client = create_chat_client(
        BackendConfig(provider=ProviderKind.OPENCODE_GO, model="kimi-k2.7-code", api_key="test")
    )
    assert isinstance(client, OpenCodeGoChatClient)


def test_factory_routes_responses_models_to_responses_client():
    client = create_chat_client(
        BackendConfig(provider=ProviderKind.OPENCODE_GO, model="grok-4.6", api_key="test")
    )
    assert isinstance(client, OpenCodeGoResponsesClient)


def test_factory_routes_deepseek_to_responses_client():
    client = create_chat_client(
        BackendConfig(provider=ProviderKind.OPENCODE_GO, model="deepseek-v4-pro", api_key="test")
    )
    assert isinstance(client, OpenCodeGoResponsesClient)


def test_factory_routes_messages_models_to_messages_client():
    client = create_chat_client(
        BackendConfig(provider=ProviderKind.OPENCODE_GO, model="claude-haiku-5-5", api_key="test")
    )
    assert isinstance(client, OpenCodeGoMessagesClient)


def test_opencode_go_responses_client_rejects_wrong_provider():
    with pytest.raises(ProviderError, match="OpenCode Go responses client requires"):
        OpenCodeGoResponsesClient(
            BackendConfig(provider=ProviderKind.OPENAI, model="x", api_key="test")
        )


def test_opencode_go_messages_client_rejects_wrong_provider():
    with pytest.raises(ProviderError, match="OpenCode Go messages client requires"):
        OpenCodeGoMessagesClient(
            BackendConfig(provider=ProviderKind.OPENAI, model="x", api_key="test")
        )


def test_responses_client_sends_session_header(monkeypatch):
    calls = []

    def send(request, *, timeout):
        calls.append(request)
        headers = {key.lower(): value for key, value in request.headers.items()}
        assert headers["authorization"] == "Bearer test-key"
        assert headers["user-agent"] == "ai_projects/0.1.0"
        assert headers["x-opencode-session"] == "session-resp"
        assert request.full_url == "https://opencode.ai/inference/go/v1/responses"
        return Response(
            {
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "hello"}],
                    }
                ],
                "usage": {"input_tokens": 5, "output_tokens": 2},
            }
        )

    monkeypatch.setattr("ai_provider.adapters.openai_responses.urlopen", send)

    client = OpenCodeGoResponsesClient(
        BackendConfig(provider=ProviderKind.OPENCODE_GO, model="grok-4.6", api_key="test-key")
    )
    response = client.complete(
        AIRequest(
            messages=(AIMessage(MessageRole.USER, "Hi"),),
            privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
            metadata={"opencode_session": "session-resp"},
        )
    )
    assert response.message.content == "hello"
    assert response.backend.provider == "opencode_go"
    assert response.usage.input_tokens == 5


def test_messages_client_sends_session_header(monkeypatch):
    calls = []

    def send(request, *, timeout):
        calls.append(request)
        headers = {key.lower(): value for key, value in request.headers.items()}
        assert headers["authorization"] == "Bearer test-key"
        assert headers["user-agent"] == "ai_projects/0.1.0"
        assert headers["x-opencode-session"] == "session-msg"
        assert request.full_url == "https://opencode.ai/inference/go/v1/messages"
        return Response(
            {
                "content": [{"type": "text", "text": "hello"}],
                "usage": {"input_tokens": 5, "output_tokens": 2},
                "stop_reason": "end_turn",
            }
        )

    monkeypatch.setattr("ai_provider.adapters.anthropic_messages.urlopen", send)

    client = OpenCodeGoMessagesClient(
        BackendConfig(
            provider=ProviderKind.OPENCODE_GO, model="claude-haiku-5-5", api_key="test-key"
        )
    )
    response = client.complete(
        AIRequest(
            messages=(AIMessage(MessageRole.USER, "Hi"),),
            privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
            metadata={"opencode_session": "session-msg"},
        )
    )
    assert response.message.content == "hello"
    assert response.backend.provider == "opencode_go"
    assert response.usage.input_tokens == 5


def test_responses_stream_yields_text_and_final(monkeypatch):
    from ai_provider.contracts import AIStreamFinal

    def send(request, *, timeout):
        return Response(
            [
                {"type": "response.created"},
                {"type": "response.output_text.delta", "delta": "hi"},
                {
                    "type": "response.completed",
                    "response": {"usage": {"input_tokens": 3, "output_tokens": 1}},
                },
            ]
        )

    monkeypatch.setattr("ai_provider.adapters.openai_responses.urlopen", send)

    client = OpenCodeGoResponsesClient(
        BackendConfig(provider=ProviderKind.OPENCODE_GO, model="grok-4.6", api_key="test-key")
    )
    events = list(
        client.stream(
            AIRequest(
                messages=(AIMessage(MessageRole.USER, "Hi"),),
                privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
            )
        )
    )
    assert events[0].content == "hi"
    assert isinstance(events[-1], AIStreamFinal)


def test_messages_stream_yields_text_and_final(monkeypatch):
    from ai_provider.contracts import AIStreamFinal

    def send(request, *, timeout):
        return Response(
            [
                {"type": "message_start"},
                {"type": "content_block_delta", "delta": {"text": "hi"}},
                {"type": "message_delta", "usage": {"output_tokens": 1}},
                {"type": "message_stop"},
            ]
        )

    monkeypatch.setattr("ai_provider.adapters.anthropic_messages.urlopen", send)

    client = OpenCodeGoMessagesClient(
        BackendConfig(
            provider=ProviderKind.OPENCODE_GO, model="claude-haiku-5-5", api_key="test-key"
        )
    )
    events = list(
        client.stream(
            AIRequest(
                messages=(AIMessage(MessageRole.USER, "Hi"),),
                privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
            )
        )
    )
    assert events[0].content == "hi"
    assert isinstance(events[-1], AIStreamFinal)


def test_generic_openai_responses_base_has_openai_base_url(monkeypatch):
    def send(request, *, timeout):
        assert request.full_url == "https://api.openai.com/v1/responses"
        return Response({"output": [], "usage": {"input_tokens": 1, "output_tokens": 1}})

    monkeypatch.setattr("ai_provider.adapters.openai_responses.urlopen", send)

    client = OpenAIResponsesChatClient(
        BackendConfig(provider=ProviderKind.OPENAI, model="gpt-5", api_key="test-key")
    )
    client.complete(
        AIRequest(
            messages=(AIMessage(MessageRole.USER, "Hi"),),
            privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        )
    )


def test_generic_anthropic_messages_base_has_anthropic_base_url(monkeypatch):
    def send(request, *, timeout):
        assert request.full_url == "https://api.anthropic.com/v1/messages"
        return Response({"content": [], "usage": {"input_tokens": 1, "output_tokens": 1}})

    monkeypatch.setattr("ai_provider.adapters.anthropic_messages.urlopen", send)

    client = AnthropicMessagesChatClient(
        BackendConfig(provider=ProviderKind.OPENAI, model="claude-sonnet", api_key="test-key")
    )
    client.complete(
        AIRequest(
            messages=(AIMessage(MessageRole.USER, "Hi"),),
            privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        )
    )
