"""Local provider mapping, full-evidence sizing, and bounded review retries."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from ai_orchestrator.review import ReviewMode, ReviewSettings
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import (
    AIMessage,
    AIRequest,
    AIResponse,
    BackendInfo,
    BackendLocation,
    FinishReason,
    MessageRole,
    PrivacyClass,
)
from ai_provider.errors import ProviderError
from ai_provider.research_execution import add_research_arguments, validate_research_arguments
from ai_provider.research_review import (
    ResearchReviewClient,
    review_input_token_upper_bound,
    review_runtime_options,
)


def model_info(architecture="qwen3", thinking=True):
    return {
        "capabilities": ["thinking"] if thinking else [],
        "model_info": {
            "general.architecture": architecture,
            f"{architecture}.context_length": 40960,
        },
    }


def response(text="visible review", finish=FinishReason.STOP):
    return AIResponse(
        AIMessage(MessageRole.ASSISTANT, text),
        BackendInfo("ollama", "qwen3:14b", BackendLocation.LOCAL),
        finish_reason=finish,
    )


@pytest.mark.parametrize(
    "mode,architecture,expected",
    [
        (ReviewMode.DIRECT, "qwen3", False),
        (ReviewMode.DELIBERATIVE, "qwen3", True),
        (ReviewMode.DELIBERATIVE, "gptoss", "high"),
    ],
)
def test_native_controls_are_distinct(mode, architecture, expected):
    assert review_runtime_options(mode, model_info(architecture)) == {"ollama_thinking": expected}


def test_default_never_invents_controls_and_unsupported_explicit_modes_fail():
    assert review_runtime_options(ReviewMode.DEFAULT, {}) == {}
    with pytest.raises(ValueError, match="advertise"):
        review_runtime_options(ReviewMode.DELIBERATIVE, model_info(thinking=False))
    with pytest.raises(ValueError, match="Unsupported"):
        review_runtime_options(ReviewMode.DIRECT, model_info("gptoss"))
    with pytest.raises(ValueError, match="Unsupported"):
        review_runtime_options(ReviewMode.DELIBERATIVE, model_info("unknown"))


def test_runtime_thinking_values_are_authoritative_when_advertised():
    details = {**model_info("gptoss"), "thinking": {"values": ["low", "medium", "high"]}}
    assert review_runtime_options(ReviewMode.DELIBERATIVE, details) == {"ollama_thinking": "high"}
    details["thinking"]["values"] = ["low", "medium"]
    with pytest.raises(ValueError, match="explicit thinking value"):
        review_runtime_options(ReviewMode.DELIBERATIVE, details)
    details = {**model_info(), "thinking": {"values": [False, True]}}
    assert review_runtime_options(ReviewMode.DIRECT, details) == {"ollama_thinking": False}
    details["thinking"]["values"] = [1]
    with pytest.raises(ValueError, match="explicit thinking value"):
        review_runtime_options(ReviewMode.DELIBERATIVE, details)


@pytest.mark.parametrize("thinking", [None, {}, {"values": "high"}, {"values": [False]}])
def test_malformed_or_restrictive_runtime_thinking_metadata_never_uses_a_default(thinking):
    with pytest.raises(ValueError, match="explicit thinking value"):
        review_runtime_options(ReviewMode.DELIBERATIVE, {**model_info(), "thinking": thinking})


def harness(responses, *, deadline=300, context=32768, output=4096):
    state = SimpleNamespace(now=0.0, requests=[], configs=[], inspections=[])
    values = iter(responses)

    class Client:
        backend = response().backend

        def complete(self, request) -> AIResponse:
            state.requests.append(request)
            result = next(values)
            if isinstance(result, Exception):
                raise result
            if callable(result):
                result = result(state)
            assert isinstance(result, AIResponse)
            return result

        def stream(self, request):
            yield from ()

    def factory(config):
        state.configs.append(config)
        return Client()

    def inspector(*args, **kwargs):
        state.inspections.append(kwargs)
        return model_info()

    client = ResearchReviewClient(
        BackendConfig(ProviderKind.OLLAMA, "qwen3:14b", timeout_seconds=300),
        ReviewMode.DELIBERATIVE,
        context,
        ReviewSettings(output),
        deadline,
        client_factory=factory,
        model_inspector=inspector,
        clock=lambda: state.now,
    )
    request = AIRequest(
        (AIMessage(MessageRole.USER, "Complete source and report evidence."),), model="qwen3:14b"
    )
    return client, request, state


def test_full_evidence_and_settings_are_preserved():
    client, request, state = harness([response()], deadline=23)
    result = client.complete(request)
    assert result.message.content == "visible review"
    prepared = state.requests[0]
    assert prepared.messages == request.messages
    assert prepared.max_output_tokens == 4096 and prepared.temperature == 0.2
    assert prepared.metadata["ollama_thinking"] is True
    assert state.configs[0].timeout_seconds == 23
    assert client.details["input_token_upper_bound"] == review_input_token_upper_bound(request)


def test_one_same_mode_stronger_retry_rechecks_time_and_keeps_evidence():
    def truncated(state):
        state.now = 18
        return response("", FinishReason.LENGTH)

    client, request, state = harness([truncated, response()], deadline=25)
    client.complete(request)
    assert [item.max_output_tokens for item in state.requests] == [4096, 8192]
    assert [item.timeout_seconds for item in state.configs] == [25, 7]
    assert all(item.messages == request.messages for item in state.requests)
    assert all(item.metadata["ollama_thinking"] is True for item in state.requests)
    assert len(state.inspections) == 1


def test_second_truncation_is_failure_even_if_text_has_a_pass_verdict():
    client, request, state = harness([response("VERDICT: pass", FinishReason.LENGTH)] * 2)
    with pytest.raises(ValueError, match="after one bounded retry"):
        client.complete(request)
    assert len(state.requests) == 2


def test_no_retry_without_context_headroom():
    client, request, state = harness([response("", FinishReason.LENGTH)], output=8192)
    with pytest.raises(ValueError, match="stronger truncation retry"):
        client.complete(request)
    assert len(state.requests) == 1


def test_empty_visible_output_and_provider_error_do_not_become_passes_or_retry():
    for result in (response(""), response("pass", FinishReason.ERROR), ProviderError("timeout")):
        client, request, state = harness([result])
        with pytest.raises((ValueError, ProviderError)):
            client.complete(request)
        assert len(state.requests) == 1


def test_deadline_exhaustion_and_late_response_prevent_success():
    client, request, state = harness([response()], deadline=0)
    with pytest.raises(ValueError, match="deadline"):
        client.complete(request)
    assert not state.requests and not state.inspections

    def late(state):
        state.now = 5
        return response("pass")

    client, request, state = harness([late], deadline=5)
    with pytest.raises(ValueError, match="after its deadline"):
        client.complete(request)


@pytest.mark.parametrize("deadline", [float("nan"), float("inf")])
def test_non_finite_deadline_is_rejected_before_any_probe(deadline):
    client, request, state = harness([response()], deadline=deadline)
    with pytest.raises(ValueError, match="finite"):
        client.complete(request)
    assert not state.requests and not state.inspections


def test_context_sizing_rejects_without_mutating_or_transmitting_evidence():
    client, request, state = harness([response()], context=4096)
    request = replace(request, messages=(AIMessage(MessageRole.USER, "é" * 2000),))
    assert review_input_token_upper_bound(request) == 4256
    with pytest.raises(ValueError, match="evidence was preserved"):
        client.complete(request)
    assert not state.requests and request.messages[0].content == "é" * 2000


def test_context_above_installed_model_capacity_is_rejected():
    client, request, state = harness([response()], context=65536)
    with pytest.raises(ValueError, match="installed model capacity"):
        client.complete(request)
    assert not state.requests


@pytest.mark.parametrize(
    "config",
    [
        BackendConfig(ProviderKind.OPENAI, "remote", api_key="present"),
        BackendConfig(ProviderKind.OLLAMA, "qwen3:14b", base_url="https://remote.example"),
        BackendConfig(
            ProviderKind.OLLAMA, "qwen3:14b", base_url="http://user:password@localhost:11434"
        ),
    ],
)
def test_paid_or_remote_routes_fail_before_any_probe_even_with_credentials(config):
    client, request, state = harness([response()])
    client.config = config
    with pytest.raises(ProviderError, match="local loopback"):
        client.complete(request)
    assert not state.inspections and not state.requests and not state.configs


def test_request_privacy_and_model_must_match_local_plan():
    client, request, state = harness([response()])
    with pytest.raises(ValueError, match="local-only privacy"):
        client.complete(replace(request, privacy_class=PrivacyClass.EXTERNAL_ALLOWED))
    with pytest.raises(ValueError, match="differs"):
        client.complete(replace(request, model="different"))
    assert not state.inspections and not state.requests


def test_review_argument_defaults_and_bypass_remain_compatible():
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser()
    add_research_arguments(parser)
    args = parser.parse_args([])
    assert args.research_review_policy == "legacy"
    assert args.research_review_tokenizer_file is None
    validate_research_arguments(args, Path.cwd(), parser)
    for flags in (
        ["--research-review-policy", "quality_first"],
        ["--research-review-model", "qwen3:14b"],
        ["--research-review-mode", "direct"],
        ["--research-review-tokenizer-file", "local.json"],
    ):
        with pytest.raises(SystemExit):
            validate_research_arguments(parser.parse_args(flags), Path.cwd(), parser)
    with pytest.raises(SystemExit):
        validate_research_arguments(
            parser.parse_args(["--tool-profile", "research", "--research-review-mode", "direct"]),
            Path.cwd(),
            parser,
        )


@pytest.mark.parametrize("fallback", [False, True])
def test_optional_counter_receives_effective_mode_and_records_fallback(
    tmp_path, monkeypatch, fallback
):
    client, request, state = harness([response()])
    client.tokenizer_file = tmp_path / "explicit.json"
    client.version_inspector = lambda *args, **kwargs: "0.32.5"

    def counter(prepared, info, asset, *, runtime_version):
        assert prepared.messages == request.messages
        assert prepared.metadata["ollama_thinking"] is True
        assert prepared.model == "qwen3:14b"
        assert asset == client.tokenizer_file and runtime_version == "0.32.5"
        if fallback:
            raise ValueError("Profile mismatch")
        return 17

    monkeypatch.setattr("ai_provider.research_token_count.count_review_input_tokens", counter)
    client.complete(request)
    assert state.requests[0].messages == request.messages
    assert client.details["input_bound_method"] == (
        "utf8_bytes_plus_framing" if fallback else "verified_local_tokenizer"
    )
    assert client.details["input_token_upper_bound"] == (
        review_input_token_upper_bound(request) if fallback else 17
    )
    if fallback:
        assert client.details["tokenizer_fallback_reason"] == "Profile mismatch"


def test_tokenizer_preparation_time_cannot_start_generation_after_deadline(tmp_path, monkeypatch):
    client, request, state = harness([response()], deadline=23)
    client.tokenizer_file = tmp_path / "explicit.json"
    client.version_inspector = lambda *args, **kwargs: "0.32.5"

    def counter(*args, **kwargs):
        state.now = 23
        return 17

    monkeypatch.setattr("ai_provider.research_token_count.count_review_input_tokens", counter)
    with pytest.raises(ValueError):
        client.complete(request)
    assert not state.requests and not state.configs


def test_absent_tokenizer_option_does_not_inspect_runtime_version():
    client, request, state = harness([response()])

    def unexpected(*args, **kwargs):
        pytest.fail("Legacy conservative sizing must not probe optional tokenizer compatibility")

    client.version_inspector = unexpected
    client.complete(request)
    assert len(state.requests) == 1


def test_explicit_tokenizer_option_requires_and_accepts_quality_first_research():
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser()
    add_research_arguments(parser)
    parser.set_defaults(
        mode="plan",
        orchestrated=True,
        privacy="local_only",
        cost_policy="local_only",
        no_native_tools=False,
        apply_actions=False,
        allow_outside_files=False,
        delegate_context=False,
        skip_validation=False,
    )
    flags = ["--tool-profile", "research", "--research-review-tokenizer-file", "local.json"]
    with pytest.raises(SystemExit):
        validate_research_arguments(parser.parse_args(flags), Path.cwd(), parser)
    args = parser.parse_args(
        flags
        + ["--research-review-policy", "quality_first", "--research-report", "artifacts/report.md"]
    )
    validate_research_arguments(args, Path.cwd(), parser)
    assert args.research_review_tokenizer_file == Path("local.json")


def test_large_evidence_is_admitted_only_by_verified_counter(tmp_path, monkeypatch):
    client, request, state = harness([response()])
    request = replace(
        request,
        messages=(
            AIMessage(MessageRole.SYSTEM, "Grounding rules"),
            AIMessage(MessageRole.USER, "Complete evidence " * 4000),
        ),
    )
    with pytest.raises(ValueError, match="headroom"):
        client.complete(request)
    assert not state.requests
    client.tokenizer_file = tmp_path / "explicit.json"
    client.version_inspector = lambda *args, **kwargs: "0.32.5"
    monkeypatch.setattr(
        "ai_provider.research_token_count.count_review_input_tokens", lambda *a, **k: 12000
    )
    client.complete(request)
    assert state.requests[0].messages == request.messages
    assert state.requests[0].max_output_tokens == 4096


def test_fallback_never_forces_large_evidence_into_context(tmp_path, monkeypatch):
    client, request, state = harness([response()])
    request = replace(
        request,
        messages=(
            AIMessage(MessageRole.SYSTEM, "Grounding rules"),
            AIMessage(MessageRole.USER, "Full evidence " * 4000),
        ),
    )
    client.tokenizer_file = tmp_path / "explicit.json"
    client.version_inspector = lambda *args, **kwargs: None

    def unsupported(*args, **kwargs):
        raise ValueError("Unknown runtime version")

    monkeypatch.setattr("ai_provider.research_token_count.count_review_input_tokens", unsupported)
    with pytest.raises(ValueError, match="headroom"):
        client.complete(request)
    assert not state.requests
    assert client.details["input_bound_method"] == "utf8_bytes_plus_framing"
