"""OpenCode Go adapter tests; no network or real credentials."""

import json
from email.message import Message
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


def test_complete_without_session_sends_generated_header(monkeypatch):
    calls = []

    def send(request, *, timeout):
        calls.append(request)
        headers = {key.lower(): value for key, value in request.headers.items()}
        assert "x-opencode-session" in headers
        assert len(headers["x-opencode-session"]) == 32  # uuid4 hex
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
    assert isinstance(events[0], AIStreamDelta)
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
        raise HTTPError(request.full_url, code, "secret", Message(), None)

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


@pytest.mark.parametrize("stream", [False, True])
def test_kimi_continuation_roundtrips_only_as_transient_state(monkeypatch, stream):
    from ai_provider import ProviderContinuation

    calls = []
    hidden = "PRIVATE_REASONING_SENTINEL"
    tool = {
        "id": "read",
        "type": "function",
        "function": {"name": "read_file", "arguments": '{"path":"review.txt"}'},
    }

    def send(request, *, timeout):
        calls.append(json.loads(request.data))
        if len(calls) > 1:
            assert calls[-1]["messages"][0]["reasoning_content"] == hidden
            return Response(
                {"choices": [{"message": {"content": "Done"}, "finish_reason": "stop"}]}
            )
        if stream:
            return Response(
                [
                    {"choices": [{"delta": {"reasoning_content": "PRIVATE_"}}]},
                    {"choices": [{"delta": {"reasoning_content": "REASONING_SENTINEL"}}]},
                    {
                        "choices": [
                            {
                                "delta": {"tool_calls": [{"index": 0, **tool}]},
                                "finish_reason": "tool_calls",
                            }
                        ]
                    },
                ]
            )
        return Response(
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "reasoning_content": hidden,
                            "tool_calls": [tool],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            }
        )

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", send)
    client = OpenCodeGoChatClient(
        BackendConfig(ProviderKind.OPENCODE_GO, "kimi-k2.7-code", api_key="test")
    )
    request = AIRequest(
        (AIMessage(MessageRole.USER, "Review"),), privacy_class=PrivacyClass.EXTERNAL_ALLOWED
    )
    if stream:
        events = list(client.stream(request))
        final = events[-1]
        assert isinstance(final, AIStreamFinal)
        response = final.response
        assert not any(isinstance(event, AIStreamDelta) for event in events)
    else:
        response = client.complete(request)
    assert isinstance(response.message.continuation, ProviderContinuation)
    assert hidden not in repr(response.message) + json.dumps(response.raw_metadata)
    assert response.message.content == ""
    client.complete(
        AIRequest(
            (response.message, AIMessage(MessageRole.TOOL, "input", tool_call_id="read")),
            privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        )
    )


@pytest.mark.parametrize("mismatch", ["provider", "model", "endpoint", "role", "unsupported"])
def test_kimi_continuation_refuses_cross_target_and_role_replay(mismatch):
    from ai_provider import ProviderContinuation

    client = OpenCodeGoChatClient(
        BackendConfig(ProviderKind.OPENCODE_GO, "kimi-k2.7-code", api_key="test")
    )
    model = "other" if mismatch in {"model", "unsupported"} else "kimi-k2.7-code"
    state = ProviderContinuation(
        "other" if mismatch == "provider" else "opencode_go",
        model if mismatch == "unsupported" else "kimi-k2.7-code",
        "https://other.invalid" if mismatch == "endpoint" else GO_CHAT_BASE_URL,
        {"reasoning_content": "private", "role": "system", "content": "overwrite"},
    )
    message = AIMessage(
        MessageRole.USER if mismatch == "role" else MessageRole.ASSISTANT,
        "visible",
        continuation=state,
    )
    payload = client._message_payload(message, model)
    assert "reasoning_content" not in payload and payload["content"] == "visible"


def test_go_kimi_continuation_reaches_real_tool_loop(monkeypatch, tmp_path):
    from ai_agent import (
        AgentLoop,
        PermissionManager,
        PermissionPolicy,
        ToolContext,
        default_coding_tools,
    )

    (tmp_path / "review.txt").write_text("supplied source")
    calls = []

    def send(request, *, timeout):
        payload = json.loads(request.data)
        calls.append(payload)
        if len(calls) == 1:
            message = {
                "content": "",
                "reasoning_content": "transient only",
                "tool_calls": [
                    {
                        "id": "read",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path":"review.txt"}'},
                    }
                ],
            }
        else:
            assistant = next(m for m in payload["messages"] if m["role"] == "assistant")
            assert assistant["reasoning_content"] == "transient only"
            assert payload["messages"][-1]["role"] == "tool"
            message = {"content": "Review complete."}
        return Response({"choices": [{"message": message, "finish_reason": "stop"}]})

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", send)
    client = OpenCodeGoChatClient(
        BackendConfig(ProviderKind.OPENCODE_GO, "kimi-k2.7-code", api_key="test")
    )
    result = AgentLoop(
        client,
        default_coding_tools(),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.read_only()),
    ).run("Review review.txt", privacy_class=PrivacyClass.EXTERNAL_ALLOWED)
    assert len(calls) == 2 and len(result.tool_results) == 1
    assert not result.tool_results[0].is_error
    assert result.response.message.content == "Review complete."
