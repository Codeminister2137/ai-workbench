"""Opt-in synthetic Requesty checks; paid models are never used."""

import os
from decimal import Decimal

import pytest
from ai_provider import (
    AIMessage,
    AIRequest,
    AIToolDefinition,
    AIToolParameter,
    MessageRole,
    PrivacyClass,
)
from ai_provider.adapters.openai_compatible import OpenAICompatibleChatClient
from ai_provider.config import BackendConfig, ProviderKind

pytestmark = pytest.mark.skipif(
    os.getenv("AI_PROVIDER_RUN_REQUESTY_FREE_INTEGRATION") != "1",
    reason="Set AI_PROVIDER_RUN_REQUESTY_FREE_INTEGRATION=1 for synthetic free-only live checks.",
)


def _client() -> OpenAICompatibleChatClient:
    return OpenAICompatibleChatClient(
        BackendConfig(
            provider=ProviderKind.REQUESTY,
            model="google/gemma-4-31b-it",
            require_free_model=True,
            timeout_seconds=90,
        )
    )


def _assert_zero_cost(response) -> None:
    usage = response.raw_metadata.get("usage", {})
    assert "cost" in usage, "Provider must report cost for the live acceptance check"
    assert Decimal(str(usage["cost"])) == 0


def test_free_requesty_completion_and_reported_zero_cost() -> None:
    response = _client().complete(
        AIRequest(
            messages=(AIMessage(MessageRole.USER, "Reply with exactly: CONNECTED"),),
            privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
            max_output_tokens=256,
        )
    )
    assert "CONNECTED" in response.message.content
    _assert_zero_cost(response)


def test_free_requesty_native_tool_round_trip() -> None:
    chat = _client()
    messages = (
        AIMessage(
            MessageRole.USER, "Call add_numbers with a=2 and b=3. Do not calculate it yourself."
        ),
    )
    tool = AIToolDefinition(
        "add_numbers",
        "Add two integers",
        (
            AIToolParameter("a", "integer", "First integer"),
            AIToolParameter("b", "integer", "Second integer"),
        ),
    )
    first = chat.complete(
        AIRequest(
            messages=messages,
            tools=(tool,),
            privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
            max_output_tokens=512,
        )
    )
    _assert_zero_cost(first)
    assert len(first.message.tool_calls) == 1
    call = first.message.tool_calls[0]
    assert call.name == "add_numbers"
    assert call.arguments == {"a": 2, "b": 3}
    result = chat.complete(
        AIRequest(
            messages=(
                *messages,
                first.message,
                AIMessage(
                    MessageRole.TOOL,
                    "5",
                    name=call.name,
                    tool_call_id=call.id,
                ),
            ),
            privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
            max_output_tokens=256,
        )
    )
    assert "5" in result.message.content
    _assert_zero_cost(result)
