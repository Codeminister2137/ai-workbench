from __future__ import annotations

import pytest
from ai_provider import (
    OllamaChatClient,
    OpenAICompatibleChatClient,
    ProviderError,
    ProviderErrorCategory,
    ProviderKind,
)
from ai_provider.config import BackendConfig
from ai_provider.factory import create_chat_client


def test_backend_config_loads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_KIND", "ollama")
    monkeypatch.setenv("AI_PROVIDER_MODEL", "llama3.2")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("AI_PROVIDER_TIMEOUT_SECONDS", "5")

    config = BackendConfig.from_env()

    assert config.provider is ProviderKind.OLLAMA
    assert config.model == "llama3.2"
    assert config.base_url == "http://localhost:11434"
    assert config.timeout_seconds == 5


def test_backend_config_rejects_invalid_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_KIND", "not-a-provider")

    with pytest.raises(ProviderError) as error:
        BackendConfig.from_env()

    assert error.value.category is ProviderErrorCategory.CONFIGURATION


def test_backend_config_rejects_invalid_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_TIMEOUT_SECONDS", "soon")

    with pytest.raises(ProviderError) as error:
        BackendConfig.from_env()

    assert error.value.category is ProviderErrorCategory.CONFIGURATION


def test_backend_config_rejects_empty_model() -> None:
    with pytest.raises(ProviderError):
        BackendConfig(provider=ProviderKind.OLLAMA, model=" ")


def test_factory_creates_ollama_client() -> None:
    client = create_chat_client(BackendConfig(provider=ProviderKind.OLLAMA, model="llama3.2"))

    assert isinstance(client, OllamaChatClient)


def test_backend_config_loads_provider_specific_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_PROVIDER_KIND", "requesty")
    monkeypatch.setenv("AI_PROVIDER_MODEL", "openai/gpt-5.1")
    monkeypatch.setenv("REQUESTY_API_KEY", "requesty-key")

    config = BackendConfig.from_env()

    assert config.provider is ProviderKind.REQUESTY
    assert config.api_key == "requesty-key"


def test_backend_config_loads_gemini_api_key_for_google(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_PROVIDER_KIND", "google")
    monkeypatch.setenv("AI_PROVIDER_MODEL", "gemini-3.1-pro")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")

    config = BackendConfig.from_env()

    assert config.provider is ProviderKind.GOOGLE
    assert config.api_key == "gemini-test-key"


def test_factory_creates_google_client() -> None:
    client = create_chat_client(BackendConfig(provider=ProviderKind.GOOGLE, model="gemini-3.1-pro"))

    assert isinstance(client, OpenAICompatibleChatClient)
    assert client.base_url == "https://generativelanguage.googleapis.com/v1beta/openai"


def test_factory_creates_openai_compatible_client() -> None:
    client = create_chat_client(
        BackendConfig(provider=ProviderKind.REQUESTY, model="openai/gpt-5.1")
    )

    assert isinstance(client, OpenAICompatibleChatClient)
