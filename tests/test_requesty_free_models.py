"""Free-only requests must verify live pricing before sending inference."""

import io
import json
from typing import Any

import pytest
from ai_provider import AIMessage, AIRequest, MessageRole, PrivacyClass, ProviderError
from ai_provider.adapters.openai_compatible import OpenAICompatibleChatClient
from ai_provider.config import BackendConfig, ProviderKind


def test_cli_handles_unicode_with_windows_output_encoding(monkeypatch) -> None:
    from ai_provider.repo_coding_assistant import main

    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1252")
    monkeypatch.setattr("sys.stdout", stream)
    with pytest.raises(SystemExit) as result:
        main(["--help"])
    assert result.value.code == 0
    print("Tool result: 📄")
    stream.flush()
    assert "Tool result: 📄" in buffer.getvalue().decode("utf-8")


class Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def free_model(**changes) -> dict[str, Any]:
    return {
        "id": "google/gemma-4-31b-it",
        "api": "chat",
        "input_price": 0,
        "output_price": 0,
        **changes,
    }


def client() -> OpenAICompatibleChatClient:
    return OpenAICompatibleChatClient(
        BackendConfig(
            provider=ProviderKind.REQUESTY,
            model="google/gemma-4-31b-it",
            api_key="test-only",
            require_free_model=True,
        )
    )


def request(**changes) -> AIRequest:
    return AIRequest(
        messages=(AIMessage(MessageRole.USER, "Synthetic test"),),
        privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
        **changes,
    )


@pytest.mark.parametrize(
    "row",
    [
        free_model(input_price=0.01),
        free_model(output_price=None),
        free_model(input_price=False),
        free_model(output_price="NaN"),
        free_model(pricing=[{"input_price": 0, "output_price": 0.01}]),
        free_model(cached_price=0.1),
        free_model(id="other"),
    ],
)
@pytest.mark.parametrize("stream", [False, True])
def test_rejects_paid_missing_or_unknown_prices_before_inference(monkeypatch, row, stream) -> None:
    calls = []

    def fake_urlopen(http_request, **kwargs):
        calls.append(http_request.get_method())
        return Response({"data": [row]})

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", fake_urlopen)
    with pytest.raises(ProviderError, match="not verified free"):
        if stream:
            list(client().stream(request()))
        else:
            client().complete(request())
    assert calls == ["GET"]


def test_rechecks_effective_model_every_turn_and_stops_after_price_change(monkeypatch) -> None:
    calls = []
    rows = [free_model(), free_model(output_price=1)]

    def fake_urlopen(http_request, **kwargs):
        calls.append(http_request.get_method())
        if http_request.get_method() == "GET":
            return Response({"data": [rows.pop(0)]})
        assert json.loads(http_request.data)["model"] == "google/gemma-4-31b-it"
        return Response(
            {
                "choices": [
                    {"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
                ]
            }
        )

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", fake_urlopen)
    chat = client()
    assert chat.complete(request()).message.content == "ok"
    with pytest.raises(ProviderError, match="not verified free"):
        chat.complete(request())
    assert calls == ["GET", "POST", "GET"]


def test_model_override_cannot_bypass_free_guard(monkeypatch) -> None:
    monkeypatch.setattr(
        "ai_provider.adapters.openai_compatible.urlopen",
        lambda *args, **kwargs: Response({"data": [free_model()]}),
    )
    with pytest.raises(ProviderError, match="not verified free"):
        client().complete(request(model="openai/gpt-5-mini"))


def test_catalog_failure_blocks_inference(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise TimeoutError()

    monkeypatch.setattr("ai_provider.adapters.openai_compatible.urlopen", fail)
    with pytest.raises(ProviderError, match="inference was not sent"):
        client().complete(request())
