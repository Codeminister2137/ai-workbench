"""Offline Baseten contracts; every transport is replaced before a request."""

from __future__ import annotations

import json
from collections.abc import Iterator
from email.message import Message
from typing import Any
from urllib.error import HTTPError

import pytest
from ai_provider import (
    AIMessage,
    AIRequest,
    AIStreamDelta,
    AIStreamFinal,
    AIToolDefinition,
    AIToolParameter,
    BackendConfig,
    BackendLocation,
    FinishReason,
    MessageRole,
    PrivacyClass,
    ProviderError,
    ProviderErrorCategory,
    ProviderKind,
    create_chat_client,
)
from ai_provider.adapters.baseten import BasetenChatClient, baseten_hackathon_config

EVENT_KEY = "synthetic-event-credential-only"


class FakeResponse:
    def __init__(self, *payloads: dict[str, Any]) -> None:
        self.payloads = payloads

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payloads[0]).encode()

    def __iter__(self) -> Iterator[bytes]:
        for payload in self.payloads:
            yield b"data: " + json.dumps(payload).encode() + b"\n\n"
        yield b"data: [DONE]\n\n"


@pytest.fixture(autouse=True)
def no_live_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        pytest.fail("Unexpected live transport")

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", refuse)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> BasetenChatClient:
    monkeypatch.setenv("BASETEN_HACKATHON_API_KEY", EVENT_KEY)
    monkeypatch.setenv("BASETEN_API_KEY", "synthetic-personal-credential-only")
    result = create_chat_client(baseten_hackathon_config(timeout_seconds=7))
    assert isinstance(result, BasetenChatClient)
    return result


def request(**kwargs: Any) -> AIRequest:
    return AIRequest(
        messages=(AIMessage(MessageRole.USER, "Read the synthetic fixture."),),
        privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        **kwargs,
    )


@pytest.mark.parametrize("key", [None, "", "   "])
def test_event_config_never_substitutes_another_key(
    monkeypatch: pytest.MonkeyPatch, key: str | None
) -> None:
    monkeypatch.delenv("BASETEN_HACKATHON_API_KEY", raising=False)
    if key is not None:
        monkeypatch.setenv("BASETEN_HACKATHON_API_KEY", key)
    monkeypatch.setenv("BASETEN_API_KEY", "synthetic-personal-credential-only")
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "synthetic-generic-credential-only")
    with pytest.raises(ProviderError, match="no personal-key fallback") as error:
        baseten_hackathon_config()
    assert error.value.category is ProviderErrorCategory.CONFIGURATION


def test_baseten_factory_identity_and_explicit_event_config(client: BasetenChatClient) -> None:
    assert client.backend.provider == "baseten"
    assert client.backend.model == "meta-models/muse-spark-open-1026"
    assert client.backend.location is BackendLocation.EXTERNAL
    assert client.base_url == "https://inference.baseten.co/v1"
    assert client.api_key == EVENT_KEY
    assert client.backend.capabilities.tools


def test_ordinary_baseten_env_is_separate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_KIND", "baseten")
    monkeypatch.setenv("AI_PROVIDER_MODEL", "meta-models/muse-spark-open")
    monkeypatch.delenv("AI_PROVIDER_API_KEY", raising=False)
    monkeypatch.setenv("BASETEN_API_KEY", "synthetic-personal-credential-only")
    monkeypatch.setenv("BASETEN_HACKATHON_API_KEY", EVENT_KEY)
    config = BackendConfig.from_env()
    assert config.api_key == "synthetic-personal-credential-only"
    assert isinstance(create_chat_client(config), BasetenChatClient)


def test_adapter_rejects_wrong_provider() -> None:
    with pytest.raises(ProviderError, match="ProviderKind.BASETEN"):
        BasetenChatClient(BackendConfig(provider=ProviderKind.OPENAI, model="fixture"))


def test_completion_and_tool_result_round_trip(
    client: BasetenChatClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    bodies: list[dict[str, Any]] = []

    def transport(http_request: Any, timeout: float) -> FakeResponse:
        assert http_request.full_url == "https://inference.baseten.co/v1/chat/completions"
        assert http_request.get_header("Authorization") == f"Bearer {EVENT_KEY}"
        assert timeout == 7
        bodies.append(json.loads(http_request.data))
        if len(bodies) == 1:
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "reasoning_content": "private synthetic reasoning",
                                "tool_calls": [
                                    {
                                        "id": "call-1",
                                        "type": "function",
                                        "function": {
                                            "name": "read_fixture",
                                            "arguments": '{"path":"sample.txt"}',
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 20,
                        "completion_tokens": 12,
                        "total_tokens": 32,
                        "completion_tokens_details": {"reasoning_tokens": 9},
                    },
                }
            )
        return FakeResponse(
            {"choices": [{"message": {"content": "Fixture read."}, "finish_reason": "stop"}]}
        )

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", transport)
    tool = AIToolDefinition(
        name="read_fixture",
        description="Read a fixture",
        parameters=(AIToolParameter("path", "string", "Fixture path"),),
    )
    first = client.complete(request(tools=(tool,), max_output_tokens=64))
    assert first.finish_reason is FinishReason.UNKNOWN
    assert first.message.content == ""
    assert first.tool_calls[0].arguments == {"path": "sample.txt"}
    assert first.usage.output_tokens == 12  # Includes reasoning; do not add 9 again.
    assert first.usage.total_tokens == 32
    assert "private synthetic reasoning" not in json.dumps(first.raw_metadata)
    assert first.message.continuation is None
    final = client.complete(
        AIRequest(
            messages=(
                AIMessage(MessageRole.USER, "Read the synthetic fixture."),
                first.message,
                AIMessage(MessageRole.TOOL, "synthetic file content", tool_call_id="call-1"),
            ),
            privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        )
    )
    assert final.message.content == "Fixture read."
    assert bodies[0]["model"] == "meta-models/muse-spark-open-1026"
    assert bodies[0]["max_tokens"] == 64
    assert bodies[0]["tools"][0]["function"]["name"] == "read_fixture"
    assert bodies[1]["messages"][1]["tool_calls"][0]["id"] == "call-1"
    assert bodies[1]["messages"][2] == {
        "role": "tool",
        "content": "synthetic file content",
        "tool_call_id": "call-1",
    }


def test_stream_keeps_usage_and_tools_without_reasoning_metadata(
    client: BasetenChatClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def transport(http_request: Any, timeout: float) -> FakeResponse:
        body = json.loads(http_request.data)
        assert body["stream_options"] == {"include_usage": True}
        return FakeResponse(
            {
                "choices": [
                    {"delta": {"reasoning_content": "hidden thought"}, "finish_reason": None}
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "content": "Checking",
                            "reasoning": ["hidden thought"],
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call-2",
                                    "type": "function",
                                    "function": {
                                        "name": "read_fixture",
                                        "arguments": '{"path":',
                                    },
                                }
                            ],
                        },
                        "finish_reason": None,
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {
                                        "arguments": '"sample.txt"}',
                                    },
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
            {
                "choices": [],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 15,
                    "total_tokens": 25,
                    "completion_tokens_details": {"reasoning_tokens": 11},
                },
            },
        )

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", transport)
    events = list(client.stream(request()))
    deltas = [event for event in events if isinstance(event, AIStreamDelta)]
    assert [event.content for event in deltas] == ["Checking"]
    assert "hidden thought" not in json.dumps([event.raw_metadata for event in deltas])
    final = events[-1]
    assert isinstance(final, AIStreamFinal)
    assert final.response.message.content == "Checking"
    assert final.response.tool_calls[0].arguments == {"path": "sample.txt"}
    assert final.response.usage.output_tokens == 15
    assert final.response.usage.total_tokens == 25
    assert final.response.message.continuation is None


@pytest.mark.parametrize("stream", [False, True])
def test_event_model_override_refused_before_transport(
    client: BasetenChatClient, stream: bool
) -> None:
    with pytest.raises(ProviderError, match="exact event model"):
        if stream:
            list(client.stream(request(model="meta-models/muse-spark-open")))
        else:
            client.complete(request(model="meta-models/muse-spark-open"))


@pytest.mark.parametrize("stream", [False, True])
def test_credentials_refused_before_transport(client: BasetenChatClient, stream: bool) -> None:
    unsafe = AIRequest(
        messages=(AIMessage(MessageRole.USER, EVENT_KEY),),
        privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
    )
    with pytest.raises(ProviderError, match="Credential-bearing") as error:
        if stream:
            list(client.stream(unsafe))
        else:
            client.complete(unsafe)
    assert error.value.raw_error is None
    assert EVENT_KEY not in str(error.value)


def test_private_input_refused_before_transport(client: BasetenChatClient) -> None:
    with pytest.raises(ProviderError) as error:
        client.complete(AIRequest(messages=(AIMessage(MessageRole.USER, "private fixture"),)))
    assert error.value.category is ProviderErrorCategory.PRIVACY_POLICY


@pytest.mark.parametrize("status", [401, 402, 403, 429])
@pytest.mark.parametrize("stream", [False, True])
def test_http_refusal_does_not_retry_or_change_credential(
    client: BasetenChatClient, monkeypatch: pytest.MonkeyPatch, status: int, stream: bool
) -> None:
    calls = 0

    def transport(http_request: Any, timeout: float) -> FakeResponse:
        nonlocal calls
        calls += 1
        assert http_request.get_header("Authorization") == f"Bearer {EVENT_KEY}"
        raise HTTPError(http_request.full_url, status, "synthetic refusal", Message(), None)

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", transport)
    with pytest.raises(ProviderError) as error:
        if stream:
            list(client.stream(request()))
        else:
            client.complete(request())
    assert calls == 1
    assert error.value.provider == "baseten"
    assert EVENT_KEY not in str(error.value)
    assert error.value.retryable is (status == 429)
    if status in {401, 403}:
        # The established category covers both failures; it cannot identify
        # whether an event key is invalid or lacks permission on another API.
        assert error.value.category is ProviderErrorCategory.AUTHENTICATION
