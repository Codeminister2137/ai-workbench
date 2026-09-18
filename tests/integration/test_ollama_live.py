from __future__ import annotations

import os

import pytest
from ai_provider import AIMessage, AIRequest, AIStreamDelta, AIStreamFinal, MessageRole
from ai_provider.config import BackendConfig
from ai_provider.factory import create_chat_client

pytestmark = pytest.mark.skipif(
    os.getenv("AI_PROVIDER_RUN_OLLAMA_INTEGRATION") != "1",
    reason="Set AI_PROVIDER_RUN_OLLAMA_INTEGRATION=1 to run live Ollama integration tests.",
)


def test_live_ollama_chat_completion() -> None:
    client = create_chat_client(BackendConfig.from_env())
    response = client.complete(
        AIRequest(
            messages=(AIMessage(MessageRole.USER, "Reply with exactly: provider-ok"),),
            temperature=0,
            max_output_tokens=8,
        )
    )

    assert response.backend.provider == "ollama"
    assert response.message.content.strip()


def test_live_ollama_chat_streaming() -> None:
    client = create_chat_client(BackendConfig.from_env())
    events = list(
        client.stream(
            AIRequest(
                messages=(AIMessage(MessageRole.USER, "Reply with exactly: stream-ok"),),
                temperature=0,
                max_output_tokens=8,
            )
        )
    )

    deltas = [event.content for event in events if isinstance(event, AIStreamDelta)]
    final_events = [event for event in events if isinstance(event, AIStreamFinal)]

    assert deltas
    assert len(final_events) == 1
    assert final_events[0].response.backend.provider == "ollama"
    assert final_events[0].response.message.content.strip()
