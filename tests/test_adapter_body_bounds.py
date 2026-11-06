from unittest.mock import patch

import pytest
from ai_provider.adapters.ollama import OllamaChatClient
from ai_provider.adapters.openrouter import BASE_URL, OpenRouterFreeChatClient
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.errors import ProviderError, ProviderErrorCategory
from ai_provider.http_transport import MAX_RESPONSE_BYTES as BOUND


class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self, size=-1):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter([])


def _make_ollama_client():
    return OllamaChatClient(
        config=BackendConfig(
            provider=ProviderKind.OLLAMA,
            model="test-model",
            api_key="test",
            base_url="http://localhost:11434",
            timeout_seconds=5,
        )
    )


def _make_openrouter_client():
    return OpenRouterFreeChatClient(
        config=BackendConfig(
            provider=ProviderKind.OPENROUTER,
            model="test-model:free",
            api_key="test",
            base_url=BASE_URL,
            timeout_seconds=5,
        )
    )


def test_ollama_body_bound_exceeded():
    client = _make_ollama_client()
    oversized = b"x" * (BOUND + 1)
    with patch("ai_provider.adapters.ollama.urlopen", return_value=FakeResponse(oversized)):
        with pytest.raises(ProviderError) as excinfo:
            client._post_chat({"model": "test-model"})
    assert excinfo.value.category == ProviderErrorCategory.NON_RETRYABLE


def test_openrouter_body_bound_exceeded():
    client = _make_openrouter_client()
    oversized = b"x" * (BOUND + 1)
    with patch("ai_provider.adapters.openrouter.urlopen", return_value=FakeResponse(oversized)):
        with pytest.raises(ProviderError) as excinfo:
            client._metadata("models")
    assert excinfo.value.category == ProviderErrorCategory.NON_RETRYABLE
