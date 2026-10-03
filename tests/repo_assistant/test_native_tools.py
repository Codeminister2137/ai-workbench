"""Repo-assistant native tools regression contracts."""

from __future__ import annotations

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

    def fail_native_agent(*args, **kwargs):
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
    assert "status: failed" in output
    assert "delegation: disabled" in output
    assert "execution_status: failed" in output


def test_native_agent_mode_executes_provider_tool_calls(tmp_path: Path, monkeypatch) -> None:
    from ai_orchestrator import PrivacyClass as OrchestratorPrivacyClass

    coding_task_profile = _EXAMPLE.coding_task_profile
    from ai_provider import BackendConfig, ProviderKind

    client = _NativeFakeClient()
    monkeypatch.setattr(_EXAMPLE, "create_chat_client", lambda config: client)
    monkeypatch.setattr("builtins.input", lambda prompt: "yes")
    args = type(
        "Args",
        (),
        {
            "start_ollama": False,
            "ollama_command": "ollama",
            "ollama_startup_timeout_seconds": 1.0,
            "system": None,
            "max_action_rounds": 3,
            "approval_policy": "trusted_local",
            "ollama_log_file": None,
            "ollama_profile": None,
        },
    )()
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
    monkeypatch.setattr(_EXAMPLE, "_run_native_agent", lambda *args, **kwargs: native_response)

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
