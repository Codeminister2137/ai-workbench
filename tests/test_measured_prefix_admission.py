"""Offline behavioral checks for the opt-in count experiment; no services."""

from dataclasses import asdict, replace

import pytest
import test_native_admission
from ai_provider import AIMessage, AIRequest, AIResponse, MessageRole, ProviderError
from ai_provider.adapters.ollama import OllamaChatClient
from ai_provider.contracts import FinishReason, ProviderContinuation, UsageMetadata, UsageSource

native_admitted = test_native_admission.admitted


@pytest.fixture
def experiment(native_admitted):
    wrapper, client, diagnostics = native_admitted
    wrapper.measured_prefix_prototype = True
    wrapper.context_tokens = 4096
    response = AIResponse(
        AIMessage(MessageRole.ASSISTANT, "done"),
        client.backend,
        usage=UsageMetadata(UsageSource.PROVIDER_REPORTED, 100, 1),
        finish_reason=FinishReason.STOP,
    )
    original = client.complete

    def complete(request):
        original(request)
        return response

    client.complete = complete
    request = AIRequest(
        (AIMessage(MessageRole.USER, "private-prefix " * 200),), max_output_tokens=100
    )
    wrapper.complete(request)
    return wrapper, client, diagnostics, request, response


def appended(request):
    return replace(request, messages=request.messages + (AIMessage(MessageRole.USER, "next"),))


def test_prefix_reduces_false_refusal_and_preserves_full_input(experiment):
    wrapper, client, diagnostics, request, _ = experiment
    extended = replace(
        request, messages=request.messages + (AIMessage(MessageRole.USER, "x" * 4900),)
    )
    wrapper.measured_prefix_prototype = False
    with pytest.raises(ProviderError, match="does not fit"):
        wrapper.complete(extended)
    wrapper.measured_prefix_prototype = True
    wrapper.complete(request)
    wrapper.complete(extended)
    assert "measured_prefix_estimated_append" in diagnostics[-1]
    assert client.requests[-1].messages == extended.messages
    assert client.requests[-1].metadata["ollama_preserve_context"] is True
    assert "private-prefix" not in repr(wrapper._prefix)
    assert "private-prefix" not in str(asdict(wrapper._prefix))
    assert all("private-prefix" not in line for line in diagnostics)


@pytest.mark.parametrize(
    "change", ["prefix", "metadata", "thinking", "temperature", "top_p", "tools", "endpoint"]
)
def test_changed_scope_uses_absolute_gate(experiment, change):
    from ai_provider import AIToolDefinition

    wrapper, _, diagnostics, request, _ = experiment
    request = appended(request)
    if change == "prefix":
        request = replace(request, messages=(AIMessage(MessageRole.USER, "changed"),))
    elif change in ("metadata", "thinking"):
        request = replace(
            request, metadata={"ollama_thinking" if change == "thinking" else "option": True}
        )
    elif change == "temperature":
        request = replace(request, temperature=0.7)
    elif change == "top_p":
        request = replace(request, top_p=0.95)
    elif change == "tools":
        request = replace(request, tools=(AIToolDefinition("read", "new schema"),))
    else:
        wrapper.config = replace(wrapper.config, base_url="http://localhost:11434")
    wrapper.complete(request)
    assert "estimated_utf8" in diagnostics[-1]


@pytest.mark.parametrize("count", [None, 0, -1, True, 1.5, 4097])
def test_invalid_count_discards_anchor(experiment, count):
    wrapper, client, diagnostics, request, response = experiment
    client.complete = lambda request: replace(
        response, usage=UsageMetadata(UsageSource.PROVIDER_REPORTED, count)
    )
    wrapper.complete(appended(request))
    assert wrapper._prefix is None
    wrapper.complete(appended(request))
    assert "estimated_utf8" in diagnostics[-1]


@pytest.mark.parametrize("source", [UsageSource.ESTIMATED, UsageSource.UNAVAILABLE])
def test_unmeasured_usage_discards_anchor(experiment, source):
    wrapper, client, _, request, response = experiment
    client.complete = lambda request: replace(response, usage=UsageMetadata(source, 100))
    wrapper.complete(request)
    assert wrapper._prefix is None


def test_unverifiable_options_fall_back_without_logging_private_values(experiment):
    wrapper, _, diagnostics, request, _ = experiment
    wrapper.complete(replace(request, metadata={"private-option": object()}))
    assert "estimated_utf8" in diagnostics[-1]
    assert wrapper._prefix is None
    assert all("private-option" not in line for line in diagnostics)


def test_output_and_appended_thinking_overflow_refuse_without_effect(experiment):
    wrapper, client, _, request, _ = experiment
    before = len(client.requests)
    with pytest.raises(ProviderError, match="does not fit"):
        wrapper.complete(replace(appended(request), max_output_tokens=4096))
    state = ProviderContinuation(
        "ollama", wrapper.config.model, "local", {"thinking": "private" * 2000}
    )
    with pytest.raises(ProviderError, match="does not fit"):
        wrapper.complete(
            replace(
                request,
                messages=request.messages
                + (AIMessage(MessageRole.ASSISTANT, "", continuation=state),),
            )
        )
    assert len(client.requests) == before


@pytest.mark.parametrize("change", ["provider", "model", "endpoint", "error_finish"])
def test_wrong_response_identity_or_error_cannot_anchor(experiment, change):
    wrapper, client, _, request, response = experiment
    if change == "error_finish":
        response = replace(response, finish_reason=FinishReason.ERROR)
    else:
        field = "base_url" if change == "endpoint" else change
        response = replace(response, backend=replace(response.backend, **{field: "changed"}))
    client.complete = lambda request: response
    wrapper.complete(request)
    assert wrapper._prefix is None


def test_stale_runtime_and_model_refuse_before_inference(experiment, monkeypatch):
    wrapper, client, _, request, _ = experiment
    before = len(client.requests)
    monkeypatch.setattr(
        "ai_provider.native_admission.installed_native_identity",
        lambda config: ("changed", "changed"),
    )
    with pytest.raises(ProviderError):
        wrapper.complete(request)
    with pytest.raises(ProviderError):
        wrapper.complete(replace(request, model="unknown"))
    assert len(client.requests) == before


def test_stream_falls_back_and_failure_discards_state(experiment):
    wrapper, client, diagnostics, request, _ = experiment
    list(wrapper.stream(appended(request)))
    assert "estimated_utf8" in diagnostics[-1]
    assert wrapper._prefix is None
    wrapper.complete(request)

    def fail(request):
        raise RuntimeError("provider failed")

    client.complete = fail
    with pytest.raises(RuntimeError):
        wrapper.complete(request)
    assert wrapper._prefix is None and wrapper._pending is None


def test_prototype_wire_disables_truncation_and_shift(experiment):
    wrapper, client, _, request, _ = experiment
    wrapper.complete(request)
    adapter = OllamaChatClient(wrapper.config)
    payload = adapter._chat_payload(client.requests[-1], stream=False)
    assert payload["truncate"] is False and payload["shift"] is False
    default = adapter._chat_payload(request, stream=False)
    assert "truncate" not in default and "shift" not in default
