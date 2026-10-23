"""Opt-in sampling is validated locally and preserved without live inference."""

from argparse import Namespace
from types import SimpleNamespace

import pytest
from ai_agent import repo_coding_assistant as cli
from ai_agent.repo_assistant_args import build_argument_parser, sampling_kwargs
from ai_orchestrator import AccessMethod
from ai_provider import AIMessage, AIRequest, BackendConfig, MessageRole, ProviderKind
from ai_provider.adapters.ollama import OllamaChatClient
from ai_provider.adapters.openai_compatible import OpenAICompatibleChatClient
from ai_provider.coding_assist import coding_request_from_prompt, coding_task_profile


@pytest.mark.parametrize("option", ["--temperature", "--top-p"])
@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "-0.1", "3", "invalid"])
def test_invalid_sampling_stops_before_execution(option, value):
    with pytest.raises(SystemExit) as error:
        build_argument_parser().parse_args(["task", f"{option}={value}"])
    assert error.value.code == 2


def test_parser_preserves_omission_zero_and_independent_controls():
    parser = build_argument_parser()
    assert sampling_kwargs(parser.parse_args(["task"])) == {}
    assert sampling_kwargs(parser.parse_args(["task", "--temperature=0"])) == {"temperature": 0}
    assert sampling_kwargs(parser.parse_args(["task", "--top-p=1"])) == {"top_p": 1}
    assert sampling_kwargs(parser.parse_args(["task", "--top-p=0"])) == {"top_p": 0}
    with pytest.raises(SystemExit):
        parser.parse_args(["task", "--top-p=1.01"])


@pytest.mark.parametrize("native", [True, False])
@pytest.mark.parametrize(
    "sampling", [{}, {"temperature": 0.0}, {"temperature": 1.0, "top_p": 0.95}]
)
def test_adapter_payloads_preserve_explicit_values_and_omit_defaults(native, sampling):
    provider = ProviderKind.OLLAMA if native else ProviderKind.REQUESTY
    config = BackendConfig(provider, "synthetic")
    client = OllamaChatClient(config) if native else OpenAICompatibleChatClient(config)
    request = AIRequest((AIMessage(MessageRole.USER, "public"),), **sampling)
    for stream in (False, True):
        payload = client._chat_payload(request, stream=stream)
        options = payload.get("options", {}) if native else payload
        for key in ("temperature", "top_p"):
            if key in sampling:
                assert options[key] == sampling[key]
            else:
                assert key not in options


def test_coding_request_carries_opt_in_sampling():
    request = coding_request_from_prompt(
        "task",
        coding_task_profile(),
        BackendConfig(ProviderKind.OLLAMA, "synthetic"),
        temperature=1.0,
        top_p=0.95,
    )
    assert (request.temperature, request.top_p) == (1.0, 0.95)


@pytest.mark.parametrize("method", [AccessMethod.CODEX_CLI, AccessMethod.COPILOT_CLI])
def test_external_fallback_cannot_silently_drop_sampling(tmp_path, method):
    target = SimpleNamespace(access_method=method)
    args = Namespace(temperature=0, top_p=0.95)
    reason = cli._fallback_target_incompatibility(target, args, tmp_path)
    preservation = cli._preservation_target_incompatibility(target, args, tmp_path)
    assert reason is not None and "sampling" in reason
    assert preservation is not None and "sampling" in preservation


def test_external_primary_refuses_before_client_or_fallback_start(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("external execution/readiness started with unsupported sampling")

    monkeypatch.setattr(cli, "FallbackSession", forbidden)
    monkeypatch.setattr(cli, "_run_external_agent", forbidden)
    with pytest.raises(SystemExit) as error:
        cli.main(
            [
                "task",
                "--execute",
                "--repo-root",
                str(tmp_path),
                "--route-id",
                "openai/codex-gpt-5.5",
                "--privacy",
                "public_or_low_risk",
                "--cost-policy",
                "allowances_allowed",
                "--temperature",
                "1",
                "--top-p",
                "0.95",
            ]
        )
    assert error.value.code == 2


def test_request_wrapper_keeps_sampling_for_repair_calls(tmp_path, monkeypatch):
    observed = []
    monkeypatch.setattr(cli, "run_coding_prompt", lambda *args, **kwargs: observed.append(kwargs))
    args = Namespace(temperature=1.0, top_p=0.95)
    cli._run_coding_prompt_with_fallback(
        "repair task", None, (), args=args, repo_root=tmp_path, execute=True
    )
    assert observed[0]["temperature"] == 1 and observed[0]["top_p"] == 0.95
