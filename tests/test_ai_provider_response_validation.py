"""Malformed transport data never becomes executable invented tool arguments."""

import json

import pytest
from ai_provider import (
    AIMessage,
    AIRequest,
    MessageRole,
    PrivacyClass,
    ProviderError,
    ProviderErrorCategory,
)
from ai_provider.adapters import ollama, openai_compatible
from ai_provider.config import BackendConfig, ProviderKind


@pytest.fixture(params=[ProviderKind.OLLAMA, ProviderKind.OPENAI])
def adapter(request, monkeypatch):
    provider = request.param
    module, client_type = (
        (ollama, ollama.OllamaChatClient)
        if provider is ProviderKind.OLLAMA
        else (openai_compatible, openai_compatible.OpenAICompatibleChatClient)
    )
    client = client_type(BackendConfig(provider=provider, model="fixture", api_key="fixture"))

    def respond(body, *, stream=False):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return body

            def __iter__(self):
                yield (b"data: " if provider is ProviderKind.OPENAI else b"") + body + b"\n"

        monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: Response())
        task = AIRequest(
            messages=(AIMessage(MessageRole.USER, "fixture"),),
            privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
        )
        return list(client.stream(task)) if stream else client.complete(task)

    return provider, respond


class TestOptionalResponseMetadata:
    @pytest.mark.parametrize("invalid", [True, -1, "10", 1.5])
    def test_invalid_counters_remain_unknown_without_losing_the_answer(self, adapter, invalid):
        provider, respond = adapter
        message = {"content": "Valid answer"}
        payload = (
            {"message": message, "done": True, "prompt_eval_count": invalid, "eval_count": 3}
            if provider is ProviderKind.OLLAMA
            else {
                "choices": [{"message": message, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": invalid,
                    "completion_tokens": 3,
                    "total_tokens": invalid,
                },
            }
        )
        response = respond(json.dumps(payload).encode())
        assert response.message.content == "Valid answer"
        assert response.usage.input_tokens is None
        assert response.usage.output_tokens == 3
        assert response.usage.total_tokens is None

    @pytest.mark.parametrize("reason", [[], {}])
    def test_unknown_finish_metadata_does_not_escape_as_a_type_error(self, adapter, reason):
        provider, respond = adapter
        message = {"content": "Valid answer"}
        payload = (
            {"message": message, "done": True, "done_reason": reason}
            if provider is ProviderKind.OLLAMA
            else {"choices": [{"message": message, "finish_reason": reason}]}
        )
        response = respond(json.dumps(payload).encode())
        assert response.message.content == "Valid answer"
        assert response.finish_reason.value == "unknown"


class TestMalformedResponses:
    @pytest.mark.parametrize(
        "calls",
        [
            {},
            [None],
            [{"function": []}],
            [{"function": {"name": ""}}],
            [{"function": {"name": 42}}],
        ],
    )
    @pytest.mark.parametrize("stream", [False, True])
    def test_invalid_call_shapes_are_not_silently_dropped(self, adapter, calls, stream):
        provider, respond = adapter
        message = {"content": "", "tool_calls": calls}
        payload = (
            {"message": message, "done": True}
            if provider is ProviderKind.OLLAMA
            else {
                "choices": [
                    {"delta" if stream else "message": message, "finish_reason": "tool_calls"}
                ]
            }
        )
        with pytest.raises(ProviderError) as failure:
            respond(json.dumps(payload).encode(), stream=stream)
        assert failure.value.category is ProviderErrorCategory.NON_RETRYABLE
        assert failure.value.provider == provider.value

    @pytest.mark.parametrize("body", [b"not-json", b"\xff", b"[]", b"null"])
    @pytest.mark.parametrize("stream", [False, True])
    def test_invalid_wire_data_is_a_normalized_nonretryable_error(self, adapter, body, stream):
        provider, respond = adapter
        with pytest.raises(ProviderError) as failure:
            respond(body, stream=stream)
        assert failure.value.category is ProviderErrorCategory.NON_RETRYABLE
        assert failure.value.provider == provider.value

    @pytest.mark.parametrize("arguments", ["{broken", "[]", [], None])
    def test_invalid_arguments_do_not_silently_become_an_empty_object(self, adapter, arguments):
        provider, respond = adapter
        message = {
            "content": "",
            "tool_calls": [{"id": "call", "function": {"name": "probe", "arguments": arguments}}],
        }
        payload = (
            {"message": message, "done": True}
            if provider is ProviderKind.OLLAMA
            else {"choices": [{"message": message, "finish_reason": "tool_calls"}]}
        )
        with pytest.raises(ProviderError, match="Tool arguments|tool arguments") as failure:
            respond(json.dumps(payload).encode())
        assert failure.value.category is ProviderErrorCategory.NON_RETRYABLE
        assert failure.value.provider == provider.value
