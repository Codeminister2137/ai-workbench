from __future__ import annotations

import os
from dataclasses import replace

import pytest
from ai_provider import (
    AIMessage,
    AIRequest,
    AIStreamDelta,
    AIStreamFinal,
    BackendLocation,
    MessageRole,
    PrivacyClass,
)
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.factory import create_chat_client

pytestmark = pytest.mark.skipif(
    os.getenv("AI_PROVIDER_RUN_HOSTED_INTEGRATION") != "1",
    reason="Set AI_PROVIDER_RUN_HOSTED_INTEGRATION=1 to run live hosted integration tests.",
)


def _hosted_config_from_env() -> BackendConfig:
    config = BackendConfig.from_env()
    if config.provider is ProviderKind.OLLAMA:
        pytest.skip("Set AI_PROVIDER_KIND to openai or requesty for live hosted integration tests.")
    if config.provider is ProviderKind.REQUESTY:
        config = replace(config, require_free_model=True)
    return config


def test_live_hosted_chat_completion() -> None:
    client = create_chat_client(_hosted_config_from_env())
    response = client.complete(
        AIRequest(
            messages=(AIMessage(MessageRole.USER, "Reply with exactly: hosted-ok"),),
            temperature=0,
            max_output_tokens=8,
            privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        )
    )

    assert response.backend.provider in {"openai", "requesty"}
    assert response.backend.location is BackendLocation.EXTERNAL
    assert response.message.content.strip()


def test_live_hosted_chat_streaming() -> None:
    client = create_chat_client(_hosted_config_from_env())
    events = list(
        client.stream(
            AIRequest(
                messages=(AIMessage(MessageRole.USER, "Reply with exactly: hosted-stream-ok"),),
                temperature=0,
                max_output_tokens=8,
                privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
            )
        )
    )

    deltas = [event.content for event in events if isinstance(event, AIStreamDelta)]
    final_events = [event for event in events if isinstance(event, AIStreamFinal)]

    assert deltas
    assert len(final_events) == 1
    assert final_events[0].response.backend.provider in {"openai", "requesty"}
    assert final_events[0].response.message.content.strip()
