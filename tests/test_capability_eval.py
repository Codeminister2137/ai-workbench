from types import SimpleNamespace

import pytest
from ai_provider.capability_eval import SchemaProbeOllamaClient, probe
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import (
    AIMessage,
    AIRequest,
    AIResponse,
    AIStreamDelta,
    AIStreamFinal,
    AIToolCall,
    BackendInfo,
    BackendLocation,
    MessageRole,
)
from ai_provider.errors import ProviderError, ProviderErrorCategory


def response(text='{"answer":7}', calls=()):
    return AIResponse(
        AIMessage(MessageRole.ASSISTANT, text),
        BackendInfo("ollama", "fixture", BackendLocation.LOCAL),
        tool_calls=calls,
    )


def test_tools_require_exact_name_and_integer():
    for calls, expected in [
        ((AIToolCall("1", "record_answer", {"answer": 7}),), "pass"),
        ((AIToolCall("1", "record_answer", {"answer": 7.0}),), "fail"),
        ((AIToolCall("1", "wrong", {"answer": 7}),), "fail"),
        ((), "fail"),
    ]:
        client = SimpleNamespace(complete=lambda request, calls=calls: response(calls=calls))
        assert probe(client, "fixture", "tools").status == expected


@pytest.mark.parametrize(
    "events,expected",
    [
        ([AIStreamDelta('{"answer":7}'), AIStreamFinal(response())], "pass"),
        ([AIStreamFinal(response())], "fail"),
        ([AIStreamDelta("wrong"), AIStreamFinal(response())], "fail"),
        ([AIStreamDelta("partial")], "fail"),
    ],
)
def test_stream_requires_matching_deltas_and_final(events, expected):
    client = SimpleNamespace(stream=lambda request: iter(events))
    assert probe(client, "fixture", "streaming").status == expected


def test_errors_and_unavailable_schema_are_unknown():
    def fail(request):
        raise ProviderError("secret body", category=ProviderErrorCategory.TIMEOUT)

    result = probe(SimpleNamespace(complete=fail), "fixture", "tools")
    assert result.status == "unknown"
    assert "secret" not in result.detail
    assert probe(SimpleNamespace(), "fixture", "structured_output").status == "unknown"


def test_schema_is_actually_sent_and_prompt_alone_is_not_enough(monkeypatch):
    client = SchemaProbeOllamaClient(BackendConfig(ProviderKind.OLLAMA, "fixture"))
    payload = client._chat_payload(
        AIRequest((), metadata={"capability_schema_probe": True}), stream=False
    )
    assert payload["format"]["additionalProperties"] is False
    for text, expected in [
        ('{"answer":7}', "pass"),
        ('{"answer":7.0}', "fail"),
        ('{"answer":7,"extra":1}', "fail"),
        ("not JSON", "fail"),
    ]:
        monkeypatch.setattr(client, "complete", lambda request, text=text: response(text))
        assert probe(client, "fixture", "structured_output").status == expected
