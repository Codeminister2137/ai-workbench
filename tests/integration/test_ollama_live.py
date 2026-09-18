from __future__ import annotations

import os

import pytest
from ai_provider import AIMessage, AIRequest, MessageRole
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
