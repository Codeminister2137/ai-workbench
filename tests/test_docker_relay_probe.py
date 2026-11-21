import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

PROBE = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/docker-relay-probe.py"))


def test_hosted_fixed_free_single_attempt(monkeypatch):
    from ai_provider.contracts import AIMessage, MessageRole, UsageMetadata
    from proxy_model_callback import CallbackExhausted

    configs, requests = [], []

    def factory(config):
        configs.append(config)

        def complete(request):
            requests.append(request)
            return SimpleNamespace(
                message=AIMessage(MessageRole.ASSISTANT, "relay-ok"),
                usage=UsageMetadata(input_tokens=10, output_tokens=3),
                finish_reason="stop",
            )

        return SimpleNamespace(complete=complete)

    monkeypatch.setattr("ai_provider.factory.create_chat_client", factory)
    monkeypatch.setattr("ai_provider.secrets.load_dotenv", lambda root: ())
    observations = {}
    callback = PROBE["_hosted_callback"](observations)
    with pytest.raises(ValueError):
        callback("other", [])
    assert observations["attempts"] == 0
    assert (
        callback(PROBE["HOSTED_ROUTE"], [{"role": "user", "content": "hi"}])["text"] == "relay-ok"
    )
    with pytest.raises(CallbackExhausted):
        callback(PROBE["HOSTED_ROUTE"], [])
    assert len(requests) == 1
    assert configs[0].require_free_model is True
    assert configs[0].model == PROBE["HOSTED_MODEL"]
    assert configs[0].timeout_seconds == 120
    assert requests[0].max_output_tokens == 512
    assert requests[0].metadata == {"public_or_synthetic": True}
    assert observations["usage"]["input_tokens"] == 10


def test_failed_hosted_attempt_cannot_repeat(monkeypatch):
    def fail(request):
        raise TimeoutError("fixture")

    monkeypatch.setattr(
        "ai_provider.factory.create_chat_client", lambda config: SimpleNamespace(complete=fail)
    )
    monkeypatch.setattr("ai_provider.secrets.load_dotenv", lambda root: ())
    observations = {}
    callback = PROBE["_hosted_callback"](observations)
    with pytest.raises(TimeoutError):
        callback(PROBE["HOSTED_ROUTE"], [])
    with pytest.raises(RuntimeError, match="consumed"):
        callback(PROBE["HOSTED_ROUTE"], [])
    assert observations["attempts"] == 1
