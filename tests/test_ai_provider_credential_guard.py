"""Known credentials cannot enter protocol requests, including streaming calls."""

from dataclasses import replace

import pytest
from ai_provider import AIMessage, AIRequest, MessageRole, PrivacyClass
from ai_provider.adapters.anthropic_messages import AnthropicMessagesChatClient
from ai_provider.adapters.meta import MetaResponsesChatClient
from ai_provider.adapters.modal import ModalRuntimeChatClient
from ai_provider.adapters.ollama import OllamaChatClient
from ai_provider.adapters.openai_compatible import OpenAICompatibleChatClient
from ai_provider.adapters.openai_responses import OpenAIResponsesChatClient
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.credential_guard import contains_credentials, enforce_credential_policy
from ai_provider.errors import ProviderError, ProviderErrorCategory

SECRET = "synthetic-credential-never-send-12345"


@pytest.mark.parametrize(
    "value",
    [SECRET, {SECRET: "key name"}, {"nested": [{"value": SECRET}]}, (SECRET,)],
)
def test_known_values_are_detected_without_diagnostic_echo(monkeypatch, value):
    monkeypatch.setenv("SYNTHETIC_API_KEY", SECRET)
    with pytest.raises(ProviderError) as caught:
        enforce_credential_policy(value)
    error = caught.value
    assert error.category is ProviderErrorCategory.PRIVACY_POLICY
    assert not error.retryable and not error.partial_messages and error.raw_error is None
    assert SECRET not in str(error)


def test_explicit_and_json_escaped_credentials_and_cycles():
    secret = 'synthetic-quote-"-credential'
    assert contains_credentials(
        'tool JSON: {"key": "synthetic-quote-\\"-credential"}', extra=(secret,)
    )
    assert contains_credentials("short", extra=("short",))
    assert contains_credentials(SECRET, extra=("  " + SECRET + "  ",))
    cyclic = []
    cyclic.append(cyclic)
    assert not contains_credentials(cyclic, extra=(SECRET,))
    assert not contains_credentials("ordinary request", extra=(SECRET,))


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("kind", ["chat", "responses", "messages", "meta", "modal", "ollama"])
def test_protocols_refuse_before_any_transport(monkeypatch, kind, stream):
    from ai_provider.adapters import anthropic_messages, ollama, openai_compatible, openai_responses

    def forbidden(*args, **kwargs):
        pytest.fail("Credential-bearing input reached HTTP transport")

    for module in (anthropic_messages, ollama, openai_compatible, openai_responses):
        monkeypatch.setattr(module, "urlopen", forbidden)
    monkeypatch.setenv("SYNTHETIC_API_KEY", SECRET)
    classes = {
        "chat": (OpenAICompatibleChatClient, ProviderKind.OPENAI, "fixture"),
        "responses": (OpenAIResponsesChatClient, ProviderKind.OPENAI, "fixture"),
        "messages": (AnthropicMessagesChatClient, ProviderKind.OPENCODE_GO, "fixture"),
        "meta": (MetaResponsesChatClient, ProviderKind.META, "muse-spark-1.3"),
        "modal": (ModalRuntimeChatClient, ProviderKind.MODAL, "fixture"),
        "ollama": (OllamaChatClient, ProviderKind.OLLAMA, "fixture"),
    }
    client_type, provider, model = classes[kind]
    client = client_type(
        BackendConfig(
            provider, model, api_key="synthetic-auth-only", base_url="https://fixture.invalid/v1"
        )
    )
    request = AIRequest(
        messages=(AIMessage(MessageRole.USER, "Do not send " + SECRET),),
        privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
    )
    with pytest.raises(ProviderError, match="Credential-bearing"):
        list(client.stream(request)) if stream else client.complete(request)


def test_configured_auth_key_is_protected_without_environment(monkeypatch):
    from ai_provider.adapters import openai_compatible

    monkeypatch.setattr(
        openai_compatible, "urlopen", lambda *a, **k: pytest.fail("transport reached")
    )
    client = OpenAICompatibleChatClient(
        BackendConfig(ProviderKind.OPENAI, "fixture", api_key=SECRET)
    )
    request = AIRequest(
        messages=(AIMessage(MessageRole.USER, SECRET),),
        privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
    )
    with pytest.raises(ProviderError, match="Credential-bearing"):
        client.complete(request)
    assert not contains_credentials(replace(request, messages=()), extra=(SECRET,))
