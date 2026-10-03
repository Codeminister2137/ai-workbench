"""Repo-assistant delegation regression contracts."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from .support import (
    _EXAMPLE,
    _run_native_agent,
    build_delegation_context,
    main,
    parse_external_agent_jsonl,
    run_local_context_delegation,
)


def test_build_delegation_context_adds_source_line_numbers() -> None:
    context_file = _EXAMPLE.RepoContextFile(
        path=Path("src.py"),
        display_path="src.py",
        content="first\nsecond",
        inside_repo=True,
    )

    context, sources = build_delegation_context((context_file,))

    assert sources == ("src.py",)
    assert "=== SOURCE: src.py ===" in context
    assert "1: first" in context
    assert "2: second" in context


def test_external_agent_delegation_status_detects_codex_collab_events() -> None:
    events = parse_external_agent_jsonl(
        "\n".join(
            [
                (
                    '{"type":"item.completed","item":{"type":"collab_tool_call",'
                    '"tool":"spawn_agent","status":"completed"}}'
                ),
                (
                    '{"type":"item.completed","item":{"type":"collab_tool_call",'
                    '"tool":"wait","status":"completed"}}'
                ),
            ]
        )
    )

    assert (
        _EXAMPLE._delegation_status_after_external_agent_events("disabled", events)
        == "completed: external Codex collab delegation"
    )


def test_delegate_context_requires_execution_before_provider_contact(capsys, monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("dry-run delegation must not contact a provider")

    monkeypatch.setattr(_EXAMPLE, "create_chat_client", fail_if_called)

    assert (
        main(
            [
                "--mode",
                "ask",
                "Review the selected implementation.",
                "--delegate-context",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
            ]
        )
        == 0
    )
    assert "delegation: planned: requires --execute" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("delegation_status", "expected_output"),
    [
        ("accepted: ollama-qwen2.5-coder:14b", "delegation: accepted: ollama-qwen2.5-coder:14b"),
        ("rejected: unsuitable task", "delegation: rejected: unsuitable task"),
    ],
)
def test_cli_reports_delegation_decision(
    delegation_status: str,
    expected_output: str,
    capsys,
    monkeypatch,
) -> None:
    from dataclasses import replace

    from ai_provider import (
        AIMessage,
        AIResponse,
        BackendInfo,
        MessageRole,
    )
    from ai_provider import (
        BackendLocation as ProviderBackendLocation,
    )

    catalog = _EXAMPLE.load_model_catalog(
        Path("packages/ai_orchestrator/examples/model_catalog.toml")
    )
    prepared = _EXAMPLE.run_coding_prompt(
        "Review the selected implementation.",
        _EXAMPLE.coding_task_profile(model_override="qwen2.5-coder:14b"),
        catalog,
    )
    prepared = replace(
        prepared,
        response=AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, "review complete"),
            backend=BackendInfo(
                provider="ollama",
                model="qwen2.5-coder:14b",
                location=ProviderBackendLocation.LOCAL,
            ),
        ),
    )
    monkeypatch.setattr(
        _EXAMPLE,
        "run_local_context_delegation",
        lambda *args, **kwargs: ("delegated facts", delegation_status),
    )
    monkeypatch.setattr(_EXAMPLE, "run_coding_prompt", lambda *args, **kwargs: prepared)

    assert (
        main(
            [
                "--mode",
                "review",
                "Review the selected implementation.",
                "--delegate-context",
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
    assert expected_output in output
    assert "execution_status: completed" in output


def test_local_context_delegation_reports_activity(monkeypatch) -> None:
    from ai_orchestrator import PrivacyClass as OrchestratorPrivacyClass
    from ai_provider import AIMessage, AIResponse, BackendInfo, BackendLocation, MessageRole

    class FakeClient:
        backend = BackendInfo(
            provider="ollama",
            model="qwen2.5-coder:14b",
            location=BackendLocation.LOCAL,
        )

        def complete(self, request):
            return AIResponse(
                message=AIMessage(
                    MessageRole.ASSISTANT,
                    "Keep the CLI local-first. [source:src.py:1]",
                ),
                backend=self.backend,
            )

    catalog = _EXAMPLE.load_model_catalog(
        Path("packages/ai_orchestrator/examples/model_catalog.toml")
    )
    profile = _EXAMPLE.coding_task_profile(
        privacy_class=OrchestratorPrivacyClass.LOCAL_ONLY,
        provider_override="ollama",
        model_override="qwen2.5-coder:14b",
    )
    events: list[str] = []

    summary, status = run_local_context_delegation(
        (
            _EXAMPLE.RepoContextFile(
                path=Path("src.py"),
                display_path="src.py",
                content="value = 1\n",
                inside_repo=True,
            ),
        ),
        profile,
        catalog,
        client_factory=lambda config: FakeClient(),
        progress_callback=events.append,
    )

    assert summary == "Keep the CLI local-first. [source:src.py:1]"
    assert status.startswith("accepted:")
    assert events[0] == "delegated_agent_activity: started - context_extraction"
    assert any(event.startswith("delegated_agent_activity: model_request -") for event in events)
    assert any(event.startswith("delegated_agent_activity: completed -") for event in events)


def test_native_agent_can_delegate_small_write_task(tmp_path: Path, monkeypatch) -> None:
    from ai_orchestrator import PrivacyClass as OrchestratorPrivacyClass
    from ai_provider import BackendConfig, ProviderKind

    class PrimaryClient:
        def __init__(self) -> None:
            from ai_provider import BackendInfo, BackendLocation

            self.backend = BackendInfo("ollama", "primary", BackendLocation.LOCAL)
            self.calls = 0

        def complete(self, request):
            from ai_provider import AIMessage, AIResponse, AIToolCall, MessageRole

            self.calls += 1
            if self.calls == 1:
                return AIResponse(
                    message=AIMessage(
                        MessageRole.ASSISTANT,
                        "",
                        tool_calls=(
                            AIToolCall(
                                "delegate-1",
                                "delegate_task",
                                {"task": "Create delegated.txt with delegated content."},
                            ),
                        ),
                    ),
                    backend=self.backend,
                )
            return AIResponse(
                message=AIMessage(MessageRole.ASSISTANT, "primary complete"),
                backend=self.backend,
            )

        def stream(self, request):
            raise NotImplementedError

    class ChildClient:
        def __init__(self) -> None:
            from ai_provider import BackendInfo, BackendLocation

            self.backend = BackendInfo("ollama", "child", BackendLocation.LOCAL)
            self.calls = 0

        def complete(self, request):
            from ai_provider import AIMessage, AIResponse, AIToolCall, MessageRole

            self.calls += 1
            if self.calls == 1:
                return AIResponse(
                    message=AIMessage(
                        MessageRole.ASSISTANT,
                        "",
                        tool_calls=(
                            AIToolCall(
                                "child-write",
                                "create_file",
                                {"path": "delegated.txt", "content": "delegated"},
                            ),
                        ),
                    ),
                    backend=self.backend,
                )
            return AIResponse(
                message=AIMessage(MessageRole.ASSISTANT, "child complete"),
                backend=self.backend,
            )

        def stream(self, request):
            raise NotImplementedError

    clients = [PrimaryClient(), ChildClient()]
    monkeypatch.setattr(_EXAMPLE, "create_chat_client", lambda config: clients.pop(0))
    args = SimpleNamespace(
        start_ollama=False,
        ollama_command="ollama",
        ollama_startup_timeout_seconds=1.0,
        system=None,
        max_action_rounds=3,
        approval_policy="trusted_local",
        ollama_log_file=None,
        ollama_profile=None,
        catalog=Path("packages/ai_orchestrator/examples/model_catalog.toml"),
        timeout_seconds=30.0,
    )
    events: list[str] = []

    result = _run_native_agent(
        "Delegate the small file write.",
        BackendConfig(provider=ProviderKind.OLLAMA, model="primary"),
        _EXAMPLE.coding_task_profile(privacy_class=OrchestratorPrivacyClass.LOCAL_ONLY),
        args,
        tmp_path,
        progress_callback=events.append,
    )

    assert result.response.message.content == "primary complete"
    assert (tmp_path / "delegated.txt").read_text(encoding="utf-8") == "delegated"
    assert result.tool_results[0].name == "delegate_task"
    assert "Delegated task status: completed" in result.tool_results[0].output
    assert "Tool results: 1 total, 0 failed" in result.tool_results[0].output
    assert (
        "- 1. create_file: ok - Successfully created file delegated.txt"
        in result.tool_results[0].output
    )
    assert "Child final response:\nchild complete" in result.tool_results[0].output
    assert any(event.startswith("delegated_agent_activity: model_request -") for event in events)
