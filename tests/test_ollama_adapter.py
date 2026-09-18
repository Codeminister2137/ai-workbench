from __future__ import annotations

import json
from typing import Any

import pytest
from ai_provider import (
    AIMessage,
    AIRequest,
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
