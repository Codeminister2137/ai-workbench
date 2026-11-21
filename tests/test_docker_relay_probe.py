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


@pytest.mark.parametrize(
    "code,listing,verified", [(0, "", True), (0, "abc worker Exited", False), (1, "", False)]
)
def test_teardown_observation_requires_successful_empty_listing(
    monkeypatch, code, listing, verified
):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=code, stdout=listing, stderr="")

    monkeypatch.setattr("subprocess.run", run)
    result = PROBE["_teardown_listing"]("unique-project")
    assert result["empty_verified"] is verified
    assert result["stdout"] == listing
    assert "--all" in calls[0]
    assert "label=com.docker.compose.project=unique-project" in calls[0]


@pytest.mark.parametrize("down_code,empty", [(0, True), (1, True), (0, False)])
def test_probe_closeout_includes_cleanup(monkeypatch, tmp_path, capsys, down_code, empty):
    import json

    namespace = PROBE["main"].__globals__

    def compose(file, project, *args, **kwargs):
        return SimpleNamespace(
            returncode=down_code if args[0] == "down" else 0,
            stdout=json.dumps({"relay_turn": True}),
            stderr="",
        )

    monkeypatch.setitem(namespace, "compose", compose)
    monkeypatch.setitem(namespace, "_teardown_listing", lambda project: {"empty_verified": empty})
    monkeypatch.setattr(namespace["HostMediator"], "serve_once", lambda self, **kwargs: True)
    monkeypatch.setattr("sys.argv", ["probe", "--evidence-dir", str(tmp_path / "proof")])
    expected = down_code == 0 and empty
    assert PROBE["main"]() == (0 if expected else 1)
    receipt = json.loads((tmp_path / "proof/receipt.json").read_text())
    assert receipt["passed"] is expected
    assert receipt["cleanup_verified"] is expected
    assert json.loads(capsys.readouterr().out)["passed"] is expected
