from __future__ import annotations

import pytest
from ai_provider import OllamaChatClient, ProviderError, ProviderErrorCategory, ProviderKind
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


def test_factory_rejects_unimplemented_providers() -> None:
    config = BackendConfig(provider=ProviderKind.REQUESTY, model="some-model")

    with pytest.raises(ProviderError) as error:
        create_chat_client(config)

    assert error.value.category is ProviderErrorCategory.CONFIGURATION
