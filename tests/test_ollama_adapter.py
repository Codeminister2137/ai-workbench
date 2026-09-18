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
    OllamaChatClient,
    ProviderError,
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
            yield json.dumps(payload).encode("utf-8") + b"\n"


def test_ollama_adapter_posts_neutral_request_and_normalizes_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> FakeHttpResponse:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeHttpResponse(
            {
                "message": {"role": "assistant", "content": "Hello from Ollama"},
                "done_reason": "stop",
                "prompt_eval_count": 7,
                "eval_count": 5,
            }
        )

    monkeypatch.setattr("ai_provider.adapters.ollama.urlopen", fake_urlopen)

    client = OllamaChatClient(
        BackendConfig(
            provider=ProviderKind.OLLAMA,
            model="llama3.2",
            base_url="http://ollama.test",
            timeout_seconds=12.0,
        )
    )
    response = client.complete(
        AIRequest(
            messages=(
                AIMessage(MessageRole.SYSTEM, "Be concise."),
                AIMessage(MessageRole.USER, "Say hello."),
            ),
            temperature=0.2,
            max_output_tokens=20,
        )
    )

    assert captured["url"] == "http://ollama.test/api/chat"
    assert captured["timeout"] == 12.0
    assert captured["body"] == {
        "model": "llama3.2",
        "messages": [
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Say hello."},
        ],
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 20},
    }
    assert response.message.content == "Hello from Ollama"
    assert response.backend.provider == "ollama"
    assert response.backend.location is BackendLocation.LOCAL
    assert response.usage.source is UsageSource.PROVIDER_REPORTED
    assert response.usage.input_tokens == 7
    assert response.usage.output_tokens == 5
    assert response.usage.total_tokens == 12
    assert response.finish_reason is FinishReason.STOP


def test_ollama_adapter_streams_deltas_and_final_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> FakeStreamingHttpResponse:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeStreamingHttpResponse(
            [
                {"message": {"role": "assistant", "content": "Hel"}, "done": False},
                {"message": {"role": "assistant", "content": "lo"}, "done": False},
                {
                    "message": {"role": "assistant", "content": ""},
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": 3,
                    "eval_count": 2,
                },
            ]
        )

    monkeypatch.setattr("ai_provider.adapters.ollama.urlopen", fake_urlopen)

    client = OllamaChatClient(
        BackendConfig(
            provider=ProviderKind.OLLAMA,
            model="llama3.2",
            base_url="http://ollama.test",
            timeout_seconds=12.0,
        )
    )
    events = list(
        client.stream(
            AIRequest(
                messages=(AIMessage(MessageRole.USER, "Say hello."),),
                temperature=0.2,
                max_output_tokens=20,
            )
        )
    )

    assert captured["url"] == "http://ollama.test/api/chat"
    assert captured["timeout"] == 12.0
    assert captured["body"] == {
        "model": "llama3.2",
        "messages": [{"role": "user", "content": "Say hello."}],
        "stream": True,
        "options": {"temperature": 0.2, "num_predict": 20},
    }
    assert [event.content for event in events if isinstance(event, AIStreamDelta)] == [
        "Hel",
        "lo",
    ]
    final = events[-1]
    assert isinstance(final, AIStreamFinal)
    assert final.response.message.content == "Hello"
    assert final.response.backend.provider == "ollama"
    assert final.response.backend.capabilities.streaming is True
    assert final.response.usage.source is UsageSource.PROVIDER_REPORTED
    assert final.response.usage.input_tokens == 3
    assert final.response.usage.output_tokens == 2
    assert final.response.usage.total_tokens == 5
    assert final.response.finish_reason is FinishReason.STOP


def test_ollama_adapter_stream_final_chunk_may_omit_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Any, timeout: float) -> FakeStreamingHttpResponse:
        return FakeStreamingHttpResponse(
            [
                {"message": {"role": "assistant", "content": "ok"}, "done": False},
                {"done": True, "prompt_eval_count": 1, "eval_count": 1},
            ]
        )

    monkeypatch.setattr("ai_provider.adapters.ollama.urlopen", fake_urlopen)

    client = OllamaChatClient(BackendConfig(provider=ProviderKind.OLLAMA, model="llama3.2"))
    events = list(client.stream(AIRequest(messages=(AIMessage(MessageRole.USER, "Hello"),))))

    final = events[-1]
    assert isinstance(final, AIStreamFinal)
    assert final.response.message.content == "ok"


def test_ollama_adapter_allows_request_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> FakeHttpResponse:
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeHttpResponse({"message": {"content": "ok"}})

    monkeypatch.setattr("ai_provider.adapters.ollama.urlopen", fake_urlopen)

    client = OllamaChatClient(BackendConfig(provider=ProviderKind.OLLAMA, model="default-model"))
    response = client.complete(
        AIRequest(
            messages=(AIMessage(MessageRole.USER, "Hello"),),
            model="override-model",
        )
    )

    assert captured["body"]["model"] == "override-model"
    assert response.backend.model == "override-model"


def test_ollama_adapter_wraps_connection_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: Any, timeout: float) -> FakeHttpResponse:
        raise TimeoutError

    monkeypatch.setattr("ai_provider.adapters.ollama.urlopen", fake_urlopen)

    client = OllamaChatClient(BackendConfig(provider=ProviderKind.OLLAMA, model="llama3.2"))

    with pytest.raises(ProviderError) as error:
        client.complete(AIRequest(messages=(AIMessage(MessageRole.USER, "Hello"),)))

    assert error.value.provider == "ollama"
    assert error.value.retryable is True


def test_ollama_adapter_stream_wraps_connection_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Any, timeout: float) -> FakeHttpResponse:
        raise TimeoutError

    monkeypatch.setattr("ai_provider.adapters.ollama.urlopen", fake_urlopen)

    client = OllamaChatClient(BackendConfig(provider=ProviderKind.OLLAMA, model="llama3.2"))

    with pytest.raises(ProviderError) as error:
        list(client.stream(AIRequest(messages=(AIMessage(MessageRole.USER, "Hello"),))))

    assert error.value.provider == "ollama"
    assert error.value.retryable is True


def test_ollama_adapter_rejects_unexpected_response_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Any, timeout: float) -> FakeHttpResponse:
        return FakeHttpResponse({"done_reason": "stop"})

    monkeypatch.setattr("ai_provider.adapters.ollama.urlopen", fake_urlopen)

    client = OllamaChatClient(BackendConfig(provider=ProviderKind.OLLAMA, model="llama3.2"))

    with pytest.raises(ProviderError):
        client.complete(AIRequest(messages=(AIMessage(MessageRole.USER, "Hello"),)))


def test_ollama_adapter_stream_rejects_unexpected_chunk_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Any, timeout: float) -> FakeStreamingHttpResponse:
        return FakeStreamingHttpResponse([{"done": False}])

    monkeypatch.setattr("ai_provider.adapters.ollama.urlopen", fake_urlopen)

    client = OllamaChatClient(BackendConfig(provider=ProviderKind.OLLAMA, model="llama3.2"))

    with pytest.raises(ProviderError):
        list(client.stream(AIRequest(messages=(AIMessage(MessageRole.USER, "Hello"),))))


def test_ollama_adapter_stream_requires_final_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: Any, timeout: float) -> FakeStreamingHttpResponse:
        return FakeStreamingHttpResponse(
            [{"message": {"role": "assistant", "content": "partial"}, "done": False}]
        )

    monkeypatch.setattr("ai_provider.adapters.ollama.urlopen", fake_urlopen)

    client = OllamaChatClient(BackendConfig(provider=ProviderKind.OLLAMA, model="llama3.2"))

    with pytest.raises(ProviderError, match="without a final response"):
        list(client.stream(AIRequest(messages=(AIMessage(MessageRole.USER, "Hello"),))))
