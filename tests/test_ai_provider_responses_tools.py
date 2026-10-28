"""Responses tools and stateless continuation through real adapter/agent boundaries."""

from __future__ import annotations

import json
from dataclasses import replace
from io import BytesIO

import pytest
from ai_provider import (
    AIMessage,
    AIRequest,
    AIStreamFinal,
    AIToolDefinition,
    AIToolParameter,
    BackendConfig,
    FinishReason,
    MessageRole,
    PrivacyClass,
    ProviderError,
    ProviderKind,
)
from ai_provider.adapters.meta import MetaResponsesChatClient
from ai_provider.adapters.openai_responses import OpenAIResponsesChatClient
from ai_provider.adapters.opencode_go_responses import OpenCodeGoResponsesClient
from ai_provider.errors import ToolCallFormatError


class Response(BytesIO):
    def __init__(self, payload):
        if isinstance(payload, list):
            body = b"".join(f"data: {json.dumps(event)}\n\n".encode() for event in payload)
        else:
            body = json.dumps(payload).encode()
        super().__init__(body)


@pytest.fixture(params=["openai", "meta", "opencode_go"])
def client(request):
    provider = ProviderKind(request.param)
    config = BackendConfig(
        provider,
        "muse-spark-1.3" if provider is ProviderKind.META else "test-model",
        api_key="test-key",
    )
    return {
        ProviderKind.OPENAI: OpenAIResponsesChatClient,
        ProviderKind.META: MetaResponsesChatClient,
        ProviderKind.OPENCODE_GO: OpenCodeGoResponsesClient,
    }[provider](config)


def call(call_id: str | None = "call_1", arguments: str | None = '{"path": "hello.txt"}'):
    return {
        "type": "function_call",
        "call_id": call_id,
        "name": "read_file",
        "arguments": arguments,
    }


def completed(output):
    return {
        "status": "completed",
        "output": output,
        "usage": {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
    }


def text(value="read verified"):
    return {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": value}],
    }


@pytest.mark.parametrize("stream", [False, True])
def test_actual_agent_read_roundtrip_uses_responses_items(client, stream, tmp_path, monkeypatch):
    from ai_agent import AgentLoop, PermissionManager, PermissionPolicy
    from ai_agent.tools import ReadFileTool, ToolContext, ToolRegistry

    (tmp_path / "hello.txt").write_text("fixture content from disk", encoding="utf-8")
    requests = []

    def send(request, *, timeout):
        payload = json.loads(request.data)
        requests.append(payload)
        if len(requests) == 1:
            tool = payload["tools"][0]
            assert tool["type"] == "function" and tool["name"] == "read_file"
            assert "function" not in tool
            result = completed([call()])
        else:
            assert len(requests) == 2
            calls = [item for item in payload["input"] if item.get("type") == "function_call"]
            outputs = [
                item for item in payload["input"] if item.get("type") == "function_call_output"
            ]
            assert len(calls) == len(outputs) == 1
            assert calls[0]["call_id"] == outputs[0]["call_id"] == "call_1"
            assert "fixture content from disk" in outputs[0]["output"]
            assert all(item.get("role") != "tool" for item in payload["input"])
            result = completed([text()])
        if client.config.provider is ProviderKind.META:
            assert payload["store"] is False
            assert payload["include"] == ["reasoning.encrypted_content"]
        if client.config.provider is ProviderKind.OPENCODE_GO:
            headers = {key.lower(): value for key, value in request.headers.items()}
            assert headers["user-agent"] and headers["x-opencode-session"]
        return Response([{"type": "response.completed", "response": result}] if stream else result)

    monkeypatch.setattr("ai_provider.adapters.openai_responses.urlopen", send)

    class Transport:
        backend = client.backend

        def stream(self, request):
            yield from client.stream(request)

        def complete(self, request):
            if stream:
                events = list(client.stream(request))
                assert isinstance(events[-1], AIStreamFinal)
                return events[-1].response
            return client.complete(request)

    registry = ToolRegistry()
    registry.register(ReadFileTool())
    result = AgentLoop(
        Transport(),
        registry,
        ToolContext(tmp_path),
        permissions=PermissionManager(PermissionPolicy.read_only()),
        max_iterations=2,
    ).run("Read hello.txt then report.", privacy_class=PrivacyClass.EXTERNAL_ALLOWED)
    assert result.response.message.content == "read verified"
    assert len(result.tool_results) == 1 and not result.tool_results[0].is_error
    assert result.response.backend.capabilities.tools is True


def test_native_output_order_phase_and_encrypted_continuation_are_preserved(client):
    commentary = {**text("Inspecting"), "phase": "commentary"}
    reasoning = {
        "type": "reasoning",
        "id": "rs_1",
        "encrypted_content": "opaque-state",
        "summary": [{"text": "private-summary"}],
    }
    response = client._response_from_raw(
        completed([commentary, reasoning, call()]), model=client.config.model, latency_ms=1
    )
    request = AIRequest(
        messages=(
            response.message,
            AIMessage(MessageRole.TOOL, "actual result", tool_call_id="call_1"),
        )
    )
    payload = client._responses_payload(request, stream=False)
    assert [item["type"] for item in payload["input"]] == [
        "message",
        "reasoning",
        "function_call",
        "function_call_output",
    ]
    assert payload["input"][0]["phase"] == "commentary"
    assert payload["input"][1] == {
        "type": "reasoning",
        "id": "rs_1",
        "encrypted_content": "opaque-state",
        "summary": [],
    }
    assert "opaque-state" not in json.dumps(response.raw_metadata)
    assert "private-summary" not in json.dumps(response.raw_metadata)
    assert "opaque-state" not in repr(response.message)


@pytest.mark.parametrize("mismatch", ["provider", "model", "base_url", "role"])
def test_continuation_cannot_cross_origin_or_role(mismatch):
    client = OpenAIResponsesChatClient(
        BackendConfig(
            ProviderKind.OPENAI, "test-model", api_key="synthetic-transport-credential-only"
        )
    )
    response = client._response_from_raw(
        completed(
            [
                {"type": "reasoning", "encrypted_content": "private-opaque", "id": "rs_1"},
                text(),
            ]
        ),
        model="test-model",
        latency_ms=1,
    )
    state = response.message.continuation
    assert state is not None
    message = response.message
    if mismatch == "role":
        message = replace(message, role=MessageRole.USER)
    else:
        message = replace(message, continuation=replace(state, **{mismatch: "different-origin"}))
    payload = client._responses_payload(AIRequest(messages=(message,)), stream=False)
    assert "private-opaque" not in json.dumps(payload)
    assert all(item.get("type") != "reasoning" for item in payload["input"])


@pytest.mark.parametrize("arguments", ["{", "[]", "null", None])
def test_malformed_arguments_refuse_entire_response_before_tools(client, arguments):
    with pytest.raises(ToolCallFormatError):
        client._response_from_raw(
            completed([call(), call("call_2", arguments)]), model=client.config.model, latency_ms=1
        )


@pytest.mark.parametrize("output", [[call(None)], [call("")], [call(), call()]])
def test_missing_or_duplicate_call_id_is_not_fabricated(client, output):
    with pytest.raises(ProviderError, match="unique call id"):
        client._response_from_raw(completed(output), model=client.config.model, latency_ms=1)


def test_bare_reasoning_id_is_never_replayed(client):
    response = client._response_from_raw(
        completed([{"type": "reasoning", "id": "rs_expired"}, text()]),
        model=client.config.model,
        latency_ms=1,
    )
    payload = client._responses_payload(AIRequest(messages=(response.message,)), stream=False)
    assert "rs_expired" not in json.dumps(payload)


def test_orphan_tool_result_fails_before_network(client, monkeypatch):
    monkeypatch.setattr(
        "ai_provider.adapters.openai_responses.urlopen", lambda *a, **k: pytest.fail("no network")
    )
    with pytest.raises(ProviderError, match="originating call id"):
        client.complete(
            AIRequest(
                messages=(AIMessage(MessageRole.TOOL, "result"),),
                privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
            )
        )


def test_incomplete_stream_retains_finish_reason_and_usage(client, monkeypatch):
    raw = {
        **completed([text("partial")]),
        "status": "incomplete",
        "incomplete_details": {"reason": "max_output_tokens"},
    }
    monkeypatch.setattr(
        "ai_provider.adapters.openai_responses.urlopen",
        lambda *a, **k: Response([{"type": "response.incomplete", "response": raw}]),
    )
    final = list(
        client.stream(
            AIRequest(
                messages=(AIMessage(MessageRole.USER, "hello"),),
                privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
            )
        )
    )[-1]
    assert isinstance(final, AIStreamFinal)
    assert final.response.finish_reason is FinishReason.LENGTH
    assert final.response.usage.total_tokens == 30


def test_flat_schema_preserves_required_and_array_items(client):
    tool = AIToolDefinition(
        "inspect",
        "Inspect paths",
        (AIToolParameter("paths", "array", "Paths", item_type_name="string"),),
    )
    payload = client._responses_payload(AIRequest(messages=(), tools=(tool,)), stream=False)
    assert payload["tools"][0]["parameters"]["properties"]["paths"]["items"] == {"type": "string"}
    assert payload["tools"][0]["parameters"]["required"] == ["paths"]


def test_rewritten_message_does_not_replay_stale_native_text(client):
    response = client._response_from_raw(
        completed(
            [
                {"type": "reasoning", "encrypted_content": "old-state"},
                text("old text"),
            ]
        ),
        model=client.config.model,
        latency_ms=1,
    )
    message = replace(response.message, content="current text")
    payload = client._responses_payload(AIRequest(messages=(message,)), stream=False)
    assert "old-state" not in json.dumps(payload) and "old text" not in json.dumps(payload)
    assert "current text" in json.dumps(payload)


def test_streamed_done_items_supply_tools_when_terminal_event_has_usage_only(client, monkeypatch):
    events = [
        {"type": "response.output_item.done", "output_index": 0, "item": call()},
        {"type": "response.completed", "response": {"usage": {"input_tokens": 3}}},
    ]
    monkeypatch.setattr(
        "ai_provider.adapters.openai_responses.urlopen", lambda *a, **k: Response(events)
    )
    final = list(
        client.stream(
            AIRequest(
                messages=(AIMessage(MessageRole.USER, "read"),),
                privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
            )
        )
    )[-1]
    assert isinstance(final, AIStreamFinal)
    assert final.response.tool_calls[0].id == "call_1"


def test_refusal_is_visible_and_can_be_replayed(client):
    output = [
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "refusal", "refusal": "Cannot do that."}],
        }
    ]
    response = client._response_from_raw(completed(output), model=client.config.model, latency_ms=1)
    assert response.message.content == "Cannot do that."
    assert "Cannot do that." in json.dumps(
        client._responses_payload(AIRequest(messages=(response.message,)), stream=False)
    )


def test_unmatched_result_and_unanswered_call_fail_before_provider(client):
    response = client._response_from_raw(
        completed([call()]), model=client.config.model, latency_ms=1
    )
    for messages in [
        (response.message,),
        (response.message, AIMessage(MessageRole.TOOL, "result", tool_call_id="wrong")),
    ]:
        with pytest.raises(ProviderError):
            client._responses_payload(AIRequest(messages=messages), stream=False)


@pytest.mark.parametrize("stream", [False, True])
def test_failed_response_preserves_service_error_and_cannot_deliver_tools(
    client, stream, monkeypatch
):
    raw = {
        "status": "failed",
        "error": {"code": "insufficient_quota", "message": "budget exhausted"},
        "output": [call()],
    }
    monkeypatch.setattr(
        "ai_provider.adapters.openai_responses.urlopen",
        lambda *a, **k: Response([{"type": "response.failed", "response": raw}] if stream else raw),
    )
    request = AIRequest(
        messages=(AIMessage(MessageRole.USER, "read"),), privacy_class=PrivacyClass.EXTERNAL_ALLOWED
    )
    with pytest.raises(ProviderError, match="insufficient_quota") as error:
        list(client.stream(request)) if stream else client.complete(request)
    assert error.value.category.value == "usage_limit"
    detail = error.value.raw_error
    assert isinstance(detail, dict)
    assert detail["error"]["message"] == "budget exhausted"
