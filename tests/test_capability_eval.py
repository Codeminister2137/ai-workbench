import json
import sys
from collections.abc import Callable, Iterator
from typing import cast

import pytest
from ai_provider import capability_eval
from ai_provider.adapters.openai_compatible import OpenAICompatibleChatClient
from ai_provider.adapters.openrouter import OpenRouterFreeChatClient
from ai_provider.capability_eval import SCHEMA, SchemaProbeOllamaClient, create_probe_client, probe
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import (
    AIMessage,
    AIRequest,
    AIResponse,
    AIStreamDelta,
    AIStreamEvent,
    AIStreamFinal,
    AIToolCall,
    BackendInfo,
    BackendLocation,
    MessageRole,
)
from ai_provider.errors import ProviderError, ProviderErrorCategory


class FakeClient:
    """Typed stand-in satisfying the ChatClient protocol."""

    backend = BackendInfo(provider="fake", model="test", location=BackendLocation.LOCAL)

    def __init__(
        self,
        complete: Callable[[AIRequest], AIResponse] | None = None,
        stream: Callable[[AIRequest], Iterator[AIStreamEvent]] | None = None,
    ) -> None:
        self._complete = complete
        self._stream = stream

    def complete(self, request: AIRequest) -> AIResponse:
        assert self._complete is not None
        return self._complete(request)

    def stream(self, request: AIRequest) -> Iterator[AIStreamEvent]:
        assert self._stream is not None
        return self._stream(request)


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
        client = FakeClient(complete=lambda request, calls=calls: response(calls=calls))
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
    client = FakeClient(stream=lambda request: iter(events))
    assert probe(client, "fixture", "streaming").status == expected


def test_errors_and_unavailable_schema_are_unknown():
    def fail(request):
        raise ProviderError("secret body", category=ProviderErrorCategory.TIMEOUT)

    result = probe(FakeClient(complete=fail), "fixture", "tools")
    assert result.status == "unknown"
    assert "secret" not in result.detail
    assert probe(FakeClient(), "fixture", "structured_output").status == "unknown"


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


def test_probe_attests_synthetic_prompts_for_retention_gates() -> None:
    seen: list[dict] = []

    def capture(request):
        seen.append(dict(request.metadata))
        return response()

    client = FakeClient(complete=capture, stream=lambda request: iter([]))
    assert probe(client, "fixture", "tools").status == "fail"
    assert seen and all(meta.get("public_or_synthetic") is True for meta in seen)


HOSTED_ROUTES = [
    (ProviderKind.REQUESTY, "fixture"),
    (ProviderKind.OPENCODE_GO, "kimi-k2.7-code"),
    (ProviderKind.OPENROUTER, "fixture/model:free"),
]


@pytest.mark.parametrize("provider,model", HOSTED_ROUTES)
@pytest.mark.parametrize(
    "text,expected",
    [
        ('{"answer":7}', "pass"),
        ('{"answer":7.0}', "fail"),
        ('{"answer":true}', "fail"),
        ('{"answer":7,"extra":1}', "fail"),
        ("{}", "fail"),
        ("[7]", "fail"),
        ('```json\n{"answer":7}\n```', "fail"),
        ("private raw response", "fail"),
    ],
)
def test_hosted_schema_payload_and_grading(monkeypatch, provider, model, text, expected):
    client = cast(OpenAICompatibleChatClient, create_probe_client(BackendConfig(provider, model)))
    seen = []
    admissions = []

    def admit(request):
        admissions.append(request)

    def post(payload):
        seen.append(payload)
        return {"choices": [{"message": {"role": "assistant", "content": text}}]}

    monkeypatch.setattr(client, "_verify_request_model", admit)
    monkeypatch.setattr(client, "_post_chat", post)
    result = probe(client, "fixture", "structured_output")
    assert result.status == expected
    assert "private raw response" not in result.detail
    assert len(seen) == len(admissions) == 1
    assert admissions[0].metadata["public_or_synthetic"] is True
    assert seen[0]["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "capability_probe", "strict": True, "schema": SCHEMA},
    }
    if provider is ProviderKind.OPENROUTER:
        assert seen[0]["provider"]["require_parameters"] is True
        assert seen[0]["provider"]["data_collection"] == "deny"
        assert set(seen[0]["provider"]["max_price"].values()) == {0}
    ordinary = client._chat_payload(AIRequest(()), stream=False)
    assert "response_format" not in ordinary


@pytest.mark.parametrize("provider,model", HOSTED_ROUTES)
def test_hosted_schema_preserves_admission_refusal(monkeypatch, provider, model):
    client = create_probe_client(
        BackendConfig(provider, model, require_free_model=provider is ProviderKind.REQUESTY)
    )

    def refuse(*args, **kwargs):
        raise ProviderError(
            "private credential and raw body", category=ProviderErrorCategory.CONFIGURATION
        )

    def unexpected_post(payload):
        pytest.fail("inference must not follow an admission refusal")

    guard = (
        "_verify_request_model" if provider is ProviderKind.OPENCODE_GO else "_verify_free_model"
    )
    monkeypatch.setattr(client, guard, refuse)
    monkeypatch.setattr(client, "_post_chat", unexpected_post)
    result = probe(client, "fixture", "structured_output")
    assert result.status == "unknown"
    assert result.detail == "provider error category=configuration; support undetermined"


@pytest.mark.parametrize("provider,model", HOSTED_ROUTES)
def test_hosted_schema_transport_error_is_unknown_and_redacted(monkeypatch, provider, model):
    client = create_probe_client(BackendConfig(provider, model))
    monkeypatch.setattr(client, "_verify_request_model", lambda request: None)

    def fail(payload):
        raise ProviderError("private raw error body", category=ProviderErrorCategory.NON_RETRYABLE)

    monkeypatch.setattr(client, "_post_chat", fail)
    result = probe(client, "fixture", "structured_output")
    assert result.status == "unknown"
    assert "private" not in result.detail


@pytest.mark.parametrize("model", ["gpt-6-luna", "claude-haiku-5-5"])
def test_non_chat_opencode_protocols_remain_unknown(monkeypatch, model):
    client = create_probe_client(BackendConfig(ProviderKind.OPENCODE_GO, model))

    def unexpected_complete(self, request):
        pytest.fail("unsupported schema protocol must not send prompted JSON")

    monkeypatch.setattr(type(client), "complete", unexpected_complete)
    assert probe(client, "fixture", "structured_output").status == "unknown"


@pytest.mark.parametrize("provider,model", HOSTED_ROUTES)
def test_cli_writes_schema_verdict_without_raw_bodies(monkeypatch, tmp_path, provider, model):
    catalog = tmp_path / "catalog.toml"
    catalog.write_text(
        f'[[models]]\nroute_id="fixture"\nprovider="{provider.value}"\n'
        f'model="{model}"\naccess_method="provider_api"\n',
        encoding="utf-8",
    )
    output = tmp_path / "evidence.jsonl"
    payloads = []

    def post(self, payload):
        payloads.append(payload)
        return {
            "choices": [{"message": {"role": "assistant", "content": '{"answer":7}'}}],
            "private_raw_field": "must never reach evidence",
        }

    def stream(self, request):
        return iter([AIStreamDelta('{"answer":7}'), AIStreamFinal(response())])

    monkeypatch.setattr(OpenAICompatibleChatClient, "_post_chat", post)
    monkeypatch.setattr(OpenAICompatibleChatClient, "stream", stream)
    monkeypatch.setattr(OpenAICompatibleChatClient, "_verify_request_model", lambda *args: None)
    monkeypatch.setattr(OpenRouterFreeChatClient, "_verify_request_model", lambda *args: None)
    monkeypatch.setattr(capability_eval, "load_dotenv", lambda root: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capability_eval",
            "--catalog",
            str(catalog),
            "--route",
            "fixture",
            "--output",
            str(output),
            "--allow-hosted",
        ],
    )
    capability_eval.main()
    evidence = output.read_text(encoding="utf-8")
    rows = [json.loads(line) for line in evidence.splitlines()]
    assert [row["capability"] for row in rows] == ["tools", "streaming", "structured_output"]
    assert rows[-1]["status"] == "pass"
    assert "response_format" not in payloads[0]
    assert payloads[-1]["response_format"]["json_schema"]["schema"] == SCHEMA
    assert "must never reach evidence" not in evidence
    assert "private_raw_field" not in evidence
    assert all(set(row) == set(capability_eval.Verdict.__dataclass_fields__) for row in rows)
