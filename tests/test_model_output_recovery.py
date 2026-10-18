"""Real adapter/loop recovery, bounded failures, effect receipts and privacy."""

from __future__ import annotations

import io
import json
from email.message import Message
from urllib.error import HTTPError

import pytest
from ai_agent import (
    AgentLoop,
    PermissionManager,
    PermissionPolicy,
    ToolContext,
    default_coding_tools,
)
from ai_provider import (
    BackendConfig,
    MessageRole,
    OllamaChatClient,
    ProviderError,
    ProviderErrorCategory,
    ProviderKind,
    ToolCallFormatError,
)
from ai_provider.turn_usage import ACTIVE_USAGE, TurnUsage


def parser_error(message=None, *, code=500):
    raw = json.dumps({"content": "PRIVATE_SENTINEL invalid escape offset=99"}) + "]"
    message = message or (
        f"error parsing tool call: raw='{raw}', err=invalid character ']' after top-level value"
    )
    return HTTPError(
        "http://localhost/api/chat",
        code,
        "failed",
        Message(),
        io.BytesIO(json.dumps({"error": message}).encode()),
    )


def tool(name, **args):
    return {
        "message": {
            "content": "",
            "tool_calls": [{"id": "call", "function": {"name": name, "arguments": args}}],
        },
        "done_reason": "stop",
        "prompt_eval_count": 10,
        "eval_count": 2,
    }


FINAL = {
    "message": {"content": "Verified observed work; complete."},
    "done_reason": "stop",
    "prompt_eval_count": 10,
    "eval_count": 2,
}


def client(monkeypatch, sequence):
    values = iter(sequence)
    requests = []

    def transport(request, **kwargs):
        requests.append(json.loads(request.data))
        value = next(values)
        if isinstance(value, Exception):
            raise value
        return io.BytesIO(json.dumps(value).encode())

    monkeypatch.setattr("ai_provider.adapters.ollama.urlopen", transport)
    return OllamaChatClient(BackendConfig(ProviderKind.OLLAMA, "synthetic")), requests


def loop(model, root, **kwargs):
    return AgentLoop(
        model,
        default_coding_tools(),
        ToolContext(root),
        permissions=PermissionManager(policy=PermissionPolicy.permissive()),
        **kwargs,
    )


def test_two_corrections_in_one_turn_preserve_effects_history_and_partial_usage(
    tmp_path, monkeypatch
):
    model, requests = client(
        monkeypatch,
        [
            parser_error(),
            tool("create_file", path="out.txt", content="done"),
            parser_error(),
            FINAL,
        ],
    )
    ledger = TurnUsage()
    token = ACTIVE_USAGE.set(ledger)
    events = []
    try:
        result = loop(model, tmp_path, max_iterations=5, diagnostic=events.append).run(
            "Create one file", system_prompt="Preserve instructions"
        )
    finally:
        ACTIVE_USAGE.reset(token)
    assert (tmp_path / "out.txt").read_text() == "done"
    assert len(result.tool_results) == 1 and result.model_output_errors == 2
    assert result.iterations == len(requests) == 4
    assert all(request["messages"][0]["content"] == "Preserve instructions" for request in requests)
    assert requests[-1]["messages"][: len(requests[-2]["messages"])] == requests[-2]["messages"]
    assert all(request["tools"] == requests[0]["tools"] for request in requests)
    assert "PRIVATE_SENTINEL" not in json.dumps(requests) + repr(result) + str(events)
    assert len([m for m in result.messages if m.role is MessageRole.TOOL]) == 1
    summary = ledger.summary()
    assert summary["attempts"] == 4 and summary["responses"] == 2
    assert summary["input_tokens"]["coverage"] == "partial"
    assert summary["reported_cost_usd"]["coverage"] == "unknown"


def test_repeated_parse_failures_stop_without_new_calls_or_fake_tool_results(tmp_path, monkeypatch):
    model, requests = client(monkeypatch, [parser_error(), parser_error(), FINAL])
    with pytest.raises(ProviderError, match="without observed file progress") as caught:
        loop(model, tmp_path).run("Task")
    assert len(requests) == 2 and not list(tmp_path.iterdir())
    assert isinstance(caught.value.__cause__, ToolCallFormatError)
    assert all(m.role is MessageRole.USER for m in caught.value.partial_messages)
    assert "PRIVATE_SENTINEL" not in str(caught.value)


def test_cycle_to_previously_failed_file_state_does_not_renew_feedback(tmp_path, monkeypatch):
    model, requests = client(
        monkeypatch,
        [
            tool("create_file", path="out.txt", content="A"),
            parser_error(),
            tool("edit_file", path="out.txt", old_text="A", new_text="B"),
            parser_error(),
            tool("edit_file", path="out.txt", old_text="B", new_text="A"),
            parser_error(),
            FINAL,
        ],
    )
    with pytest.raises(ProviderError, match="without observed file progress"):
        loop(model, tmp_path, max_iterations=8).run("Task")
    assert len(requests) == 6 and (tmp_path / "out.txt").read_text() == "A"


@pytest.mark.parametrize(
    "message,code",
    [
        ("an unknown server failure", 500),
        ("error parsing tool call: raw='invalid character x', err=unknown failure", 500),
        ("error parsing tool call: raw='invalid escape offset=12", 500),
        ("error parsing tool call: raw='{}', err=unexpected end of JSON input", 429),
        (
            "error parsing tool call: raw='" + "x" * 66000 + "', err=unexpected end of JSON input",
            500,
        ),
    ],
    ids=["unknown", "payload-spoof", "malformed-wrapper", "other-status", "oversize"],
)
def test_unknown_spoofed_truncated_or_other_status_does_not_enable_correction(
    tmp_path, monkeypatch, message, code
):
    failure = parser_error(message, code=code)
    model, requests = client(monkeypatch, [failure, FINAL])
    with pytest.raises(ProviderError) as caught:
        loop(model, tmp_path).run("Task")
    assert type(caught.value) is ProviderError and len(requests) == 1
    assert failure.fp is None or failure.fp.closed


def test_local_argument_decoder_uses_neutral_signal_and_preserves_known_usage(
    tmp_path, monkeypatch
):
    invalid = tool("create_file", path="out.txt", content="done")
    invalid["message"]["tool_calls"][0]["function"]["arguments"] = '{"bad":"PRIVATE_SENTINEL"'
    model, requests = client(monkeypatch, [invalid, FINAL])
    result = loop(model, tmp_path).run("Task")
    assert result.model_output_errors == 1 and not result.tool_results
    assert not list(tmp_path.iterdir())
    assert "PRIVATE_SENTINEL" not in json.dumps(requests)


def test_iteration_budget_is_not_extended_for_correction(tmp_path, monkeypatch):
    model, requests = client(monkeypatch, [parser_error(), FINAL])
    with pytest.raises(ProviderError, match="allowance ended"):
        loop(model, tmp_path, max_iterations=1).run("Task")
    assert len(requests) == 1


def test_expired_deadline_after_error_admits_no_correction(tmp_path, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("ai_agent.loop.time.perf_counter", lambda: clock[0])
    model, requests = client(monkeypatch, [parser_error(), FINAL])
    complete = model.complete

    def fail_then_expire(request):
        try:
            return complete(request)
        finally:
            clock[0] = 2.0

    monkeypatch.setattr(
        OllamaChatClient, "complete", lambda self, request: fail_then_expire(request)
    )
    with pytest.raises(ProviderError) as caught:
        loop(model, tmp_path, deadline=1.0).run("Task")
    assert caught.value.category is ProviderErrorCategory.TIMEOUT and len(requests) == 1


def test_correction_does_not_override_tool_permission(tmp_path, monkeypatch):
    model, requests = client(
        monkeypatch, [parser_error(), tool("create_file", path="out.txt", content="no"), FINAL]
    )
    result = AgentLoop(
        model,
        default_coding_tools(),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.read_only()),
    ).run("Task")
    assert result.tool_results[0].is_error and not (tmp_path / "out.txt").exists()
    assert result.model_output_errors == 1 and len(requests) == 3


def test_signal_is_not_transport_retryable():
    error = ToolCallFormatError(provider="test")
    assert error.category is ProviderErrorCategory.NON_RETRYABLE and not error.retryable
    assert error.provider == "test" and error.raw_error is None
