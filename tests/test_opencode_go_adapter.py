"""OpenCode Go adapter tests; no network or real credentials."""

import json
from io import BytesIO

import pytest
from ai_provider import (
    AIMessage,
    AIRequest,
    AIStreamFinal,
    BackendConfig,
    MessageRole,
    PrivacyClass,
    ProviderError,
    ProviderKind,
    create_chat_client,
)
from ai_provider.adapters.opencode_go import GO_CHAT_BASE_URL, GO_USER_AGENT, OpenCodeGoChatClient
from ai_provider.errors import ProviderErrorCategory


def test_factory_creates_go_client():
    client = create_chat_client(
        BackendConfig(provider=ProviderKind.OPENCODE_GO, model="kimi-k2.7-code", api_key="test")
    )
    assert isinstance(client, OpenCodeGoChatClient)
    assert client.base_url == GO_CHAT_BASE_URL


def test_backend_identity_is_go():
    client = OpenCodeGoChatClient(
        BackendConfig(provider=ProviderKind.OPENCODE_GO, model="kimi-k2.7-code", api_key="test")
    )
    assert client.backend.provider == "opencode_go"
    assert client.backend.model == "kimi-k2.7-code"
    assert client.backend.location.value == "external"


def test_wrong_provider_kind_refuses():
    with pytest.raises(ProviderError, match="OpenCode Go client requires"):
        OpenCodeGoChatClient(BackendConfig(provider=ProviderKind.OPENAI, model="x", api_key="test"))


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


def test_complete_sends_session_header_and_user_agent(monkeypatch):
    calls = []

    def send(request, *, timeout):
        calls.append(request)
        headers = {key.lower(): value for key, value in request.headers.items()}
        assert headers["authorization"] == "Bearer test-key"
        assert headers["user-agent"] == GO_USER_AGENT
        assert headers["x-opencode-session"] == "session-abc"
        return Response(
            {
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            }
        )

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", send)

    client = OpenCodeGoChatClient(
        BackendConfig(provider=ProviderKind.OPENCODE_GO, model="kimi-k2.7-code", api_key="test-key")
    )
    request = AIRequest(
        messages=(AIMessage(MessageRole.USER, "Hello"),),
        privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        metadata={"opencode_session": "session-abc"},
    )
    response = client.complete(request)
    assert response.message.content == "ok"
    assert response.backend.provider == "opencode_go"
    assert response.usage.total_tokens == 12


def test_complete_without_session_does_not_send_header(monkeypatch):
    calls = []

    def send(request, *, timeout):
        calls.append(request)
        headers = {key.lower(): value for key, value in request.headers.items()}
        assert "x-opencode-session" not in headers
        return Response({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", send)

    client = OpenCodeGoChatClient(
        BackendConfig(provider=ProviderKind.OPENCODE_GO, model="kimi-k2.7-code", api_key="test-key")
    )
    response = client.complete(
        AIRequest(
            messages=(AIMessage(MessageRole.USER, "Hello"),),
            privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        )
    )
    assert response.message.content == "ok"


def test_stream_sends_session_header(monkeypatch):
    def send(request, *, timeout):
        headers = {key.lower(): value for key, value in request.headers.items()}
        assert headers.get("x-opencode-session") == "stream-session"
        return Response(
            [
                {"choices": [{"delta": {"content": "hi"}}]},
                {"choices": [{"delta": {}, "finish_reason": "stop"}]},
            ]
        )

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", send)

    client = OpenCodeGoChatClient(
        BackendConfig(provider=ProviderKind.OPENCODE_GO, model="kimi-k2.7-code", api_key="test-key")
    )
    events = list(
        client.stream(
            AIRequest(
                messages=(AIMessage(MessageRole.USER, "Hello"),),
                privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
                metadata={"opencode_session": "stream-session"},
            )
        )
    )
    assert events[0].content == "hi"
    assert isinstance(events[-1], AIStreamFinal)


def test_local_only_refuses_before_request(monkeypatch):
    monkeypatch.setattr(
        "ai_provider.adapters.openai_compatible.urlopen",
        lambda *a, **k: pytest.fail("Network attempted"),
    )
    client = OpenCodeGoChatClient(
        BackendConfig(provider=ProviderKind.OPENCODE_GO, model="kimi-k2.7-code", api_key="test-key")
    )
    with pytest.raises(ProviderError) as error:
        client.complete(AIRequest(messages=(AIMessage(MessageRole.USER, "Hello"),)))
    assert error.value.category is ProviderErrorCategory.PRIVACY_POLICY


@pytest.mark.parametrize(
    "code,category",
    [(401, ProviderErrorCategory.AUTHENTICATION), (429, ProviderErrorCategory.RATE_LIMIT)],
)
def test_http_errors_are_normalized(monkeypatch, code, category):
    from urllib.error import HTTPError

    def send(request, *, timeout):
        raise HTTPError(request.full_url, code, "secret", {}, None)

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", send)

    client = OpenCodeGoChatClient(
        BackendConfig(provider=ProviderKind.OPENCODE_GO, model="kimi-k2.7-code", api_key="test-key")
    )
    with pytest.raises(ProviderError) as error:
        client.complete(
            AIRequest(
                messages=(AIMessage(MessageRole.USER, "Hello"),),
                privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
            )
        )
    assert error.value.category is category
    assert "secret" not in str(error.value)
