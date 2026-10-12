"""Repo-assistant native tools regression contracts."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from .support import (
    _EXAMPLE,
    _NativeFakeClient,
    _run_native_agent,
    main,
)


def test_review_mode_rejects_native_tools_before_provider_contact(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("invalid review mode must stop before provider contact")

    monkeypatch.setattr(_EXAMPLE, "create_chat_client", fail_if_called)

    with pytest.raises(SystemExit):
        main(["--mode", "review", "Review code.", "--native-tools"])


def test_native_agent_provider_failure_reports_failed_status(capsys, monkeypatch) -> None:
    from dataclasses import replace

    from ai_provider import ProviderError

    catalog = _EXAMPLE.load_model_catalog(
        Path("packages/ai_orchestrator/examples/model_catalog.toml")
    )
    prepared = _EXAMPLE.run_coding_prompt(
        "Create a helper.",
        _EXAMPLE.coding_task_profile(model_override="qwen2.5-coder:14b"),
        catalog,
    )
    prepared = replace(
        prepared,
        response=None,
        config=_EXAMPLE.BackendConfig(provider=_EXAMPLE.ProviderKind.OLLAMA, model="test"),
    )

    clock = [10.0]
    monkeypatch.setattr(_EXAMPLE.time, "perf_counter", lambda: clock[0])

    def fail_native_agent(*args, **kwargs):
        clock[0] = 13.0
        raise ProviderError("native provider unavailable")

    monkeypatch.setattr(_EXAMPLE, "run_coding_prompt", lambda *args, **kwargs: prepared)
    monkeypatch.setattr(_EXAMPLE, "_run_native_agent", fail_native_agent)

    assert (
        main(
            [
                "--mode",
                "implement",
                "Create a helper.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--execute",
            ]
        )
        == 1
    )

    output = capsys.readouterr().out
    assert "failure_reason: native provider unavailable" in output
    assert "primary_elapsed_seconds: 3.000" in output
    assert "primary_usage_source: unavailable" in output
    assert "status: failed" in output
    assert "delegation: disabled" in output
    assert "execution_status: failed" in output


def test_native_agent_mode_executes_provider_tool_calls(tmp_path: Path, monkeypatch) -> None:
    from ai_orchestrator import PrivacyClass as OrchestratorPrivacyClass

    coding_task_profile = _EXAMPLE.coding_task_profile
    from ai_provider import BackendConfig, ProviderKind

    client = _NativeFakeClient()
    requests = []
    complete = client.complete

    def capture_request(request):
        requests.append(request)
        return complete(request)

    monkeypatch.setattr(client, "complete", capture_request)
    monkeypatch.setattr(_EXAMPLE, "create_chat_client", lambda config: client)
    monkeypatch.setattr("builtins.input", lambda prompt: "yes")
    args = Namespace(
        **{
            "start_ollama": False,
            "ollama_command": "ollama",
            "ollama_startup_timeout_seconds": 1.0,
            "system": None,
            "max_action_rounds": 3,
            "approval_policy": "trusted_local",
            "ollama_log_file": None,
            "ollama_profile": None,
        }
    )
    profile = coding_task_profile(privacy_class=OrchestratorPrivacyClass.LOCAL_ONLY)
    events: list[str] = []
    result = _run_native_agent(
        "Create native.txt",
        BackendConfig(provider=ProviderKind.OLLAMA, model="test"),
        profile,
        args,
        tmp_path,
        progress_callback=events.append,
    )

    assert result.response.message.content == "native complete"
    from ai_provider.repo_context import NATIVE_TOOL_SYSTEM_PROMPT

    assert requests[0].messages[0].content == NATIVE_TOOL_SYSTEM_PROMPT
    assert requests[0].tools
    assert (tmp_path / "native.txt").read_text(encoding="utf-8") == "native"
    assert result.tool_results[0].is_error is False
    assert events[0] == "local_agent_activity: model_request - provider=ollama model=test"
    assert "local_agent_activity: completed - iterations=2 tool_results=1" in events
    assert any(event.startswith("local_tool_activity: ok - create_file:") for event in events)


@pytest.mark.parametrize(
    "content",
    [
        '```json\n{"name":"run_command","arguments":{"command":"echo done"}}\n```',
        '{"name":"create_file","arguments":{"path":"report.md","content":"done"}}',
    ],
)
def test_native_agent_rejects_textual_actions_without_execution(
    content: str, tmp_path: Path, monkeypatch
) -> None:
    from argparse import Namespace

    from ai_orchestrator import PrivacyClass as OrchestratorPrivacyClass
    from ai_provider import AIMessage, AIResponse, BackendConfig, MessageRole, ProviderError

    client = _NativeFakeClient()
    monkeypatch.setattr(
        client,
        "complete",
        lambda request: AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, content), backend=client.backend
        ),
    )
    monkeypatch.setattr(_EXAMPLE, "create_chat_client", lambda config: client)
    args = Namespace(
        start_ollama=False, system=None, max_action_rounds=3, approval_policy="trusted_local"
    )
    with pytest.raises(ProviderError, match="without executing any tools"):
        _run_native_agent(
            "Write a report",
            BackendConfig(provider=_EXAMPLE.ProviderKind.OLLAMA, model="test"),
            _EXAMPLE.coding_task_profile(privacy_class=OrchestratorPrivacyClass.LOCAL_ONLY),
            args,
            tmp_path,
        )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "content",
    ["No change needed.", '{"name":[],"arguments":{}}', '{"name":"example","arguments":{}}'],
)
def test_native_textual_action_guard_allows_ordinary_responses(content: str) -> None:
    assert not _EXAMPLE._contains_textual_tool_request(content, {"run_command"})


def test_native_agent_preserves_earlier_effect_when_final_request_is_textual(tmp_path, monkeypatch):
    from argparse import Namespace

    from ai_provider import AIMessage, AIResponse, BackendConfig, MessageRole, ProviderError

    client = _NativeFakeClient()
    complete = client.complete

    def incomplete(request):
        if client.calls == 0:
            return complete(request)
        return AIResponse(
            message=AIMessage(
                MessageRole.ASSISTANT,
                '{"name":"create_file","arguments":{"path":"missing.txt","content":"x"}}',
            ),
            backend=client.backend,
        )

    monkeypatch.setattr(client, "complete", incomplete)
    monkeypatch.setattr(_EXAMPLE, "create_chat_client", lambda config: client)
    events = []
    with pytest.raises(ProviderError, match="Earlier tool effects remain"):
        _run_native_agent(
            "Create two files",
            BackendConfig(provider=_EXAMPLE.ProviderKind.OLLAMA, model="test"),
            _EXAMPLE.coding_task_profile(),
            Namespace(
                start_ollama=False,
                system=None,
                max_action_rounds=3,
                approval_policy="trusted_local",
            ),
            tmp_path,
            progress_callback=events.append,
        )
    assert (tmp_path / "native.txt").read_text() == "native"
    assert not (tmp_path / "missing.txt").exists()
    assert any("local_tool_activity: ok - create_file" in event for event in events)
    assert any("local_agent_activity: incomplete" in event for event in events)


@pytest.mark.parametrize("content", ["", " \n\t"])
@pytest.mark.parametrize("earlier_effect", [False, True])
def test_native_agent_rejects_empty_final_report_without_replaying_effects(
    content, earlier_effect, tmp_path, monkeypatch
):
    from ai_provider import AIMessage, AIResponse, BackendConfig, MessageRole, ProviderError

    client = _NativeFakeClient()
    complete = client.complete
    requests = []

    def empty_final(request):
        requests.append(request)
        if earlier_effect and len(requests) == 1:
            return complete(request)
        return AIResponse(message=AIMessage(MessageRole.ASSISTANT, content), backend=client.backend)

    monkeypatch.setattr(client, "complete", empty_final)
    monkeypatch.setattr(_EXAMPLE, "create_chat_client", lambda config: client)
    events = []
    with pytest.raises(ProviderError, match="no final report"):
        _run_native_agent(
            "Create native.txt and report the result",
            BackendConfig(provider=_EXAMPLE.ProviderKind.OLLAMA, model="test"),
            _EXAMPLE.coding_task_profile(),
            Namespace(
                start_ollama=False,
                system=None,
                max_action_rounds=3,
                approval_policy="trusted_local",
            ),
            tmp_path,
            progress_callback=events.append,
        )
    assert len(requests) == (2 if earlier_effect else 1)
    assert (tmp_path / "native.txt").exists() == earlier_effect
    if earlier_effect:
        assert (tmp_path / "native.txt").read_text() == "native"
        assert any("local_tool_activity: ok - create_file" in event for event in events)
    assert any("local_agent_activity: incomplete" in event for event in events)
    assert not any("local_agent_activity: completed" in event for event in events)


def test_native_iteration_limit_reports_observed_receipts(tmp_path, monkeypatch):
    from argparse import Namespace

    from ai_provider import BackendConfig, ProviderError

    client = _NativeFakeClient()
    monkeypatch.setattr(_EXAMPLE, "create_chat_client", lambda config: client)
    events = []
    with pytest.raises(ProviderError, match="exceeded max_iterations=1"):
        _run_native_agent(
            "Create a file",
            BackendConfig(provider=_EXAMPLE.ProviderKind.OLLAMA, model="test"),
            _EXAMPLE.coding_task_profile(),
            Namespace(
                start_ollama=False,
                system=None,
                max_action_rounds=1,
                approval_policy="trusted_local",
            ),
            tmp_path,
            progress_callback=events.append,
        )
    assert (tmp_path / "native.txt").read_text() == "native"
    assert "local_agent_activity: failed - earlier receipts follow" in events
    assert any("local_tool_activity: recorded - create_file" in event for event in events)


def test_native_failure_preserves_provider_error_when_console_quota_is_exhausted(
    tmp_path, monkeypatch
):
    from ai_provider import BackendConfig, ProviderError

    client = _NativeFakeClient()
    monkeypatch.setattr(_EXAMPLE, "create_chat_client", lambda config: client)

    def failed_console(message):
        if message.startswith("local_agent_activity: failed"):
            raise OSError(1453, "Insufficient quota to complete the requested service")

    with pytest.raises(ProviderError, match="exceeded max_iterations=1") as caught:
        _run_native_agent(
            "Create a file",
            BackendConfig(provider=_EXAMPLE.ProviderKind.OLLAMA, model="test"),
            _EXAMPLE.coding_task_profile(),
            Namespace(
                start_ollama=False,
                system=None,
                max_action_rounds=1,
                approval_policy="trusted_local",
            ),
            tmp_path,
            progress_callback=failed_console,
        )
    assert (tmp_path / "native.txt").read_text() == "native"
    assert any(message.role.value == "tool" for message in caught.value.partial_messages)


def test_implement_mode_defaults_to_native_tools(capsys, monkeypatch) -> None:
    from dataclasses import replace

    from ai_provider import AIMessage, AIResponse, BackendInfo, BackendLocation, MessageRole

    catalog = _EXAMPLE.load_model_catalog(
        Path("packages/ai_orchestrator/examples/model_catalog.toml")
    )
    prepared = _EXAMPLE.run_coding_prompt(
        "Create a helper.",
        _EXAMPLE.coding_task_profile(model_override="qwen2.5-coder:14b"),
        catalog,
    )
    prepared = replace(
        prepared,
        response=None,
        config=_EXAMPLE.BackendConfig(provider=_EXAMPLE.ProviderKind.OLLAMA, model="test"),
    )
    native_response = SimpleNamespace(
        response=AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, "native done"),
            backend=BackendInfo("ollama", "test", BackendLocation.LOCAL),
        ),
        tool_results=(SimpleNamespace(name="delegate_task", is_error=False),),
    )
    monkeypatch.setattr(_EXAMPLE, "run_coding_prompt", lambda *args, **kwargs: prepared)
    clock = [10.0]
    monkeypatch.setattr(_EXAMPLE.time, "perf_counter", lambda: clock[0])

    def complete_native_agent(*args, **kwargs):
        clock[0] = 17.0
        return native_response

    monkeypatch.setattr(_EXAMPLE, "_run_native_agent", complete_native_agent)

    assert (
        main(
            [
                "--mode",
                "implement",
                "Create a helper.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--execute",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "native done" in output
    assert "primary_elapsed_seconds: 7.000" in output
    assert "provider_native_tools: enabled" in output
    assert "provider_native_approval_policy: interactive" in output
    assert (
        'provider_native_tool_policy_json: {"custom": "ask_user", "read": "allow", '
        '"search": "allow", "shell": "ask_user", "write": "ask_user"}'
    ) in output
    assert "provider_native_requires_interactive_approval: True" in output
    assert ("provider_native_delegation: enabled: primary agent may call delegate_task") in output
    assert "delegation: completed: native delegate_task" in output
    assert "execution_status: completed" in output


@pytest.mark.parametrize("experimental", [False, True])
def test_cli_prints_native_usage_and_latency(capsys, monkeypatch, experimental) -> None:
    from dataclasses import replace
    from pathlib import Path
    from types import SimpleNamespace

    from ai_provider import (
        AIMessage,
        AIResponse,
        BackendInfo,
        BackendLocation,
        MessageRole,
        UsageMetadata,
        UsageSource,
    )

    catalog = _EXAMPLE.load_model_catalog(
        Path("packages/ai_orchestrator/examples/model_catalog.toml")
    )
    prepared = _EXAMPLE.run_coding_prompt(
        "Create a helper.",
        _EXAMPLE.coding_task_profile(model_override="qwen2.5-coder:14b"),
        catalog,
    )
    prepared = replace(
        prepared,
        response=None,
        config=_EXAMPLE.BackendConfig(provider=_EXAMPLE.ProviderKind.OLLAMA, model="test"),
    )
    native_response = SimpleNamespace(
        response=AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, "native done"),
            backend=BackendInfo("ollama", "test", BackendLocation.LOCAL),
            usage=UsageMetadata(
                source=UsageSource.PROVIDER_REPORTED,
                input_tokens=11,
                output_tokens=7,
                total_tokens=18,
            ),
            latency_ms=125.0,
        ),
        tool_results=(SimpleNamespace(name="delegate_task", is_error=False),),
    )
    monkeypatch.setattr(_EXAMPLE, "run_coding_prompt", lambda *args, **kwargs: prepared)
    clock = [10.0]
    monkeypatch.setattr(_EXAMPLE.time, "perf_counter", lambda: clock[0])

    def complete_native_agent(*args, **kwargs):
        assert args[3].experimental_measured_prefix is experimental
        clock[0] = 17.0
        return native_response

    monkeypatch.setattr(_EXAMPLE, "_run_native_agent", complete_native_agent)

    assert (
        main(
            [
                "--mode",
                "implement",
                "Create a helper.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--execute",
                *(["--experimental-measured-prefix"] if experimental else []),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "native done" in output
    assert "primary_elapsed_seconds: 7.000" in output
    # usage and latency assertions
    assert "primary_usage_source: provider_reported" in output
    assert "primary_input_tokens: 11" in output
    assert "primary_output_tokens: 7" in output
    assert "primary_total_tokens: 18" in output
    assert "primary_provider_latency_ms: 125.0" in output


@pytest.mark.parametrize(
    "options",
    [
        ["--mode", "ask"],
        ["--mode", "plan", "--native-tools"],
        ["--mode", "chat", "--execute"],
        ["--mode", "implement", "--execute", "--no-native-tools"],
        ["--mode", "implement", "--execute", "--provider", "openai"],
        ["--mode", "implement", "--execute", "--tool-profile", "research"],
    ],
)
def test_experimental_prefix_rejects_incompatible_cli_before_provider_contact(
    options, monkeypatch, capsys
) -> None:
    def refused(*args, **kwargs):
        raise AssertionError("Incompatible experimental flag must refuse before provider contact")

    monkeypatch.setattr(_EXAMPLE, "create_chat_client", refused)
    monkeypatch.setattr(_EXAMPLE, "run_coding_prompt", refused)
    with pytest.raises(SystemExit) as caught:
        main(["Check the explicit opt-in.", "--experimental-measured-prefix", *options])
    assert caught.value.code == 2
    assert "--experimental-measured-prefix requires" in capsys.readouterr().err


def test_experimental_prefix_refuses_selected_hosted_route_before_execution(
    monkeypatch, capsys
) -> None:
    def refused(*args, **kwargs):
        raise AssertionError("Selected hosted route must refuse before execution")

    selected = SimpleNamespace(
        is_ready=True,
        execution_plan=SimpleNamespace(target=SimpleNamespace(provider="openai")),
    )
    monkeypatch.setattr(_EXAMPLE, "prepare_execution", lambda *args, **kwargs: selected)
    monkeypatch.setattr(_EXAMPLE, "run_coding_prompt", refused)
    monkeypatch.setattr(_EXAMPLE, "create_chat_client", refused)
    with pytest.raises(SystemExit) as caught:
        main(
            [
                "Check selected route.",
                "--mode",
                "implement",
                "--execute",
                "--experimental-measured-prefix",
            ]
        )
    assert caught.value.code == 2
    assert "requires a native Ollama route" in capsys.readouterr().err
