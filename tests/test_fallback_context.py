"""Destination headroom controls observable history without relaxing hard admission."""

import json
from dataclasses import replace

import pytest
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import (
    AIMessage,
    AIRequest,
    AIResponse,
    AIToolCall,
    AIToolDefinition,
    BackendInfo,
    BackendLocation,
    MessageRole,
    ProviderContinuation,
)
from ai_provider.errors import ProviderError
from ai_provider.fallback_context import FallbackHistoryClient
from ai_provider.native_admission import NativeCodingClient, estimate_coding_input_tokens


class Client:
    backend = BackendInfo("test", "test", BackendLocation.EXTERNAL)

    def __init__(self):
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        return AIResponse(AIMessage(MessageRole.ASSISTANT, "done"), self.backend)

    def stream(self, request):
        self.requests.append(request)
        return iter(())


def checkpoint():
    return (
        AIMessage(MessageRole.SYSTEM, "Preserve owner instructions"),
        AIMessage(MessageRole.USER, "Original objective"),
        AIMessage(
            MessageRole.ASSISTANT,
            "Observed edit",
            tool_calls=(
                AIToolCall("edit-1", "edit_file", {"path": "source.py", "new_text": "partial"}),
            ),
            continuation=ProviderContinuation(
                "source", "model", "endpoint", {"reasoning": "PRIVATE_REASONING_SENTINEL"}
            ),
        ),
        AIMessage(
            MessageRole.TOOL,
            "Edit succeeded; partial effect remains",
            name="edit_file",
            tool_call_id="edit-1",
        ),
    )


def request():
    return AIRequest(
        (
            AIMessage(MessageRole.SYSTEM, "Required safety and approval rules"),
            AIMessage(MessageRole.USER, "Original objective and bounded handoff; inspect effects"),
        ),
        max_output_tokens=200,
        tools=(AIToolDefinition("read_file", "Read current file"),),
    )


def test_full_history_preserves_messages_calls_results_but_no_private_reasoning():
    inner = Client()
    diagnostics = []
    wrapper = FallbackHistoryClient(inner, checkpoint(), 100000, diagnostics.append)
    wrapper.complete(request())
    admitted = inner.requests[0]
    assert admitted.messages[:-1] == request().messages
    assert admitted.tools == request().tools
    history = json.loads(admitted.messages[-1].content.split("\n", 1)[1])
    assert [item["content"] for item in history] == [item.content for item in checkpoint()]
    assert history[2]["tool_calls"][0]["arguments"]["new_text"] == "partial"
    assert history[3]["tool_call_id"] == "edit-1"
    assert all(item["continuation"] is None for item in history)
    assert "PRIVATE_REASONING_SENTINEL" not in str(admitted)
    assert all("partial effect" not in line for line in diagnostics)
    assert "full_observable_history" in diagnostics[0]
    assert checkpoint()[2].continuation is not None


@pytest.mark.parametrize("delta,full", [(0, True), (-1, False), (1, True)])
def test_exact_twenty_percent_boundary_includes_input_output_framing(delta, full):
    inner = Client()
    wide = FallbackHistoryClient(inner, checkpoint(), 100000)._request(request())
    required = estimate_coding_input_tokens(wide) + 200 + 256
    capacity = (required * 5 + 3) // 4
    wrapper = FallbackHistoryClient(inner, checkpoint(), capacity + delta)
    wrapper.complete(request())
    assert (inner.requests[0] != request()) is full


@pytest.mark.parametrize("capacity", [None, 0, -1, True, 10])
def test_unknown_invalid_or_overflow_uses_original_bounded_request(capacity):
    inner = Client()
    FallbackHistoryClient(inner, checkpoint(), capacity).complete(request())
    assert inner.requests == [request()]


def test_tools_and_explicit_output_reservation_can_force_bounded_mode():
    inner = Client()
    wrapper = FallbackHistoryClient(inner, checkpoint(), 4000)
    wrapper.complete(request())
    wrapper.complete(replace(request(), tools=(AIToolDefinition("large", "x" * 10000),)))
    wrapper.complete(replace(request(), max_output_tokens=3500))
    assert len(inner.requests[0].messages) == 3
    assert len(inner.requests[1].messages) == len(inner.requests[2].messages) == 2


def test_rechecks_growth_after_tool_work_and_preserves_all_new_messages():
    inner = Client()
    wrapper = FallbackHistoryClient(inner, checkpoint(), 4000)
    initial = request()
    wrapper.complete(initial)
    growing = replace(
        initial, messages=(*initial.messages, AIMessage(MessageRole.TOOL, "large-result" * 1000))
    )
    wrapper.complete(growing)
    assert len(inner.requests[0].messages) == 3
    assert inner.requests[1] is growing


def test_bounded_request_still_refuses_when_required_content_cannot_fit():
    inner = Client()
    admission = NativeCodingClient(inner, BackendConfig(ProviderKind.OPENAI, "test"), 100)
    wrapper = FallbackHistoryClient(admission, checkpoint(), 100)
    with pytest.raises(ProviderError, match="no model request sent"):
        wrapper.complete(request())
    assert not inner.requests


def test_default_output_reserve_and_stream_share_policy():
    inner = Client()
    wrapper = FallbackHistoryClient(inner, checkpoint(), 100000)
    assert list(wrapper.stream(replace(request(), max_output_tokens=None))) == []
    assert len(inner.requests[0].messages) == 3


def test_console_failure_cannot_discard_context_policy():
    inner = Client()

    def broken_console(message):
        raise OSError("closed")

    wrapper = FallbackHistoryClient(inner, checkpoint(), 100000, broken_console)
    wrapper.complete(request())
    assert len(inner.requests[0].messages) == 3
