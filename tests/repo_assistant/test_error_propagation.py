"""Deterministic failures through real CLI/native/fallback and reopened chat storage."""

import json
from pathlib import Path

import pytest
from ai_agent import repo_coding_assistant as cli
from ai_agent.coding_chat import CodingChatController, CodingTurnResult
from ai_provider import (
    AIMessage,
    AIResponse,
    BackendInfo,
    BackendLocation,
    MessageRole,
    ProviderError,
    ProviderErrorCategory,
)
from ai_provider.chat_transcripts import SQLiteChatTranscriptStore
from ai_provider.closeout import format_cli_closeout, safe_fallback_handoff


@pytest.mark.parametrize("scenario", ["limited", "empty", "transport_after_tool"])
def test_failed_native_report_survives_cli_and_chat_restart(
    tmp_path, monkeypatch, capsys, scenario
):
    from ai_provider import AIToolCall
    from ai_provider.contracts import FinishReason

    catalog = tmp_path / "catalog.toml"
    catalog.write_text(
        """[[models]]
route_id = "primary"
provider = "ollama"
product = "ollama"
model = "primary"
location = "local"
access_method = "local_runtime"
auth_method = "none"
billing_source = "local_free"
cost_policy_tier = "local_only"
quality = "high"
[models.capabilities]
chat = true
tools = true
""",
        encoding="utf-8",
    )
    (tmp_path / "user-config.toml").write_text("[fallback]\nenabled = false\n")
    (tmp_path / "review.txt").write_text("Read-only input")
    calls = []

    class Client:
        def complete(self, request):
            calls.append(request)
            if scenario == "transport_after_tool":
                if len(calls) > 1:
                    raise ProviderError("Synthetic transport failure")
                tools = (AIToolCall("read", "read_file", {"path": "review.txt"}),)
                return AIResponse(
                    AIMessage(MessageRole.ASSISTANT, "Intermediate tool request", tool_calls=tools),
                    BackendInfo("ollama", "primary", BackendLocation.LOCAL),
                    tool_calls=tools,
                )
            return AIResponse(
                AIMessage(
                    MessageRole.ASSISTANT,
                    "Partial review ends here" if scenario == "limited" else "",
                ),
                BackendInfo("ollama", "primary", BackendLocation.LOCAL),
                finish_reason=FinishReason.LENGTH,
            )

    monkeypatch.setattr(cli, "create_chat_client", lambda config: Client())
    monkeypatch.setattr(cli, "_fallback_target_compatible", lambda *args, **kwargs: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "/exit")
    assert (
        cli.main(
            [
                "--mode",
                "coding-chat",
                "--execute",
                "--shared-tools",
                "coding",
                "--approval-policy",
                "read_only",
                "--repo-root",
                str(tmp_path),
                "--catalog",
                str(catalog),
                "--provider",
                "ollama",
                "--model",
                "primary",
                "--skip-prompt-review",
                "Review the supplied input.",
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    store = SQLiteChatTranscriptStore(tmp_path / "data/repo-assistant-chats.sqlite3")
    session = store.latest_session(repo_root=tmp_path)
    assert session is not None
    saved = store.list_messages(session.session_id)[-1]
    assert saved.metadata is not None
    assert saved.metadata["returncode"] == 1
    assert saved.metadata["execution_status"] == "failed"
    assert output.count("## **SUMMARY**") == 1
    if scenario == "limited":
        label = "Incomplete agent report (execution failed; not accepted):"
        assert label in output and label in saved.content
        assert "Partial review ends here" in output and "Partial review ends here" in saved.content
        assert "No final response was captured" not in output
    else:
        assert "No final response was captured" in output
        assert "Incomplete agent report" not in saved.content
        assert "Intermediate tool request" not in saved.content


@pytest.mark.parametrize("scenario", ["direct", "switch", "exhausted", "unknown", "recovered"])
def test_native_cli_error_context_survives_chat_restart(tmp_path, monkeypatch, capsys, scenario):
    catalog = tmp_path / "catalog.toml"
    models = ("primary", "secondary") if scenario in {"switch", "recovered"} else ("primary",)
    catalog.write_text(
        "\n".join(
            f'''[[models]]
route_id = "{model}"
provider = "ollama"
product = "ollama"
model = "{model}"
location = "local"
access_method = "local_runtime"
auth_method = "none"
billing_source = "local_free"
cost_policy_tier = "local_only"
quality = "high"
[models.capabilities]
chat = true
tools = true
'''
            for model in models
        ),
        encoding="utf-8",
    )
    (tmp_path / "user-config.toml").write_text(
        '[fallback]\nquality_policy = "preserve_quality"\n', encoding="utf-8"
    )
    sentinel = "PRIVATE_ERROR_BODY_SENTINEL"
    primary = ProviderError(
        "model is overloaded"
        if scenario in {"switch", "recovered"}
        else "Synthetic request failed",
        provider=None if scenario == "unknown" else "ollama",
        category=(
            ProviderErrorCategory.USAGE_LIMIT
            if scenario == "exhausted"
            else ProviderErrorCategory.RETRYABLE
        ),
        raw_error=None if scenario == "unknown" else OSError(sentinel),
    )
    secondary = ProviderError(
        "Synthetic request failed",
        provider="secondary_service",
        category=ProviderErrorCategory.TIMEOUT,
        raw_error=TimeoutError(sentinel),
    )
    calls = []

    class Client:
        def __init__(self, model):
            self.model = model

        def complete(self, request):
            calls.append(self.model)
            assert request.tools
            if self.model == "secondary" and scenario == "recovered":
                return AIResponse(
                    AIMessage(MessageRole.ASSISTANT, "Inspection complete."),
                    BackendInfo("ollama", self.model, BackendLocation.LOCAL),
                )
            failure = secondary if self.model == "secondary" else primary
            cause = failure.raw_error
            assert cause is None or isinstance(cause, BaseException)
            raise failure from cause

    # Only transport/client admission and readiness are synthetic. Do not replace
    # native wrappers, AgentLoop, FallbackSession, CLI catch/observer or chat executor.
    monkeypatch.setattr(cli, "create_chat_client", lambda config: Client(config.model))
    monkeypatch.setattr(cli, "_fallback_target_compatible", lambda *args, **kwargs: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "/exit")
    code = cli.main(
        [
            "--mode",
            "coding-chat",
            "--execute",
            "--repo-root",
            str(tmp_path),
            "--catalog",
            str(catalog),
            "--provider",
            "ollama",
            "--model",
            "primary",
            "--skip-prompt-review",
            "Inspect this synthetic workspace.",
        ]
    )
    assert code == (0 if scenario == "recovered" else 1)
    assert calls == list(models)
    output = capsys.readouterr().out
    summary = output.split("## **SUMMARY**")[-1]
    # Reopen the actual default transcript DB after the terminal executor closed.
    store = SQLiteChatTranscriptStore(tmp_path / "data/repo-assistant-chats.sqlite3")
    session = store.latest_session(repo_root=tmp_path)
    assert session is not None
    chat = CodingChatController(store, session.session_id, tmp_path, "local_only")
    metadata = store.list_messages(session.session_id)[-1].metadata
    assert metadata is not None and metadata["returncode"] == code
    history = chat.history()
    assert sentinel not in output + history + json.dumps(metadata)
    if scenario == "recovered":
        assert metadata["execution_status"] == "completed"
        assert "category" not in metadata
        assert metadata["effective_route_id"] == "secondary"
        attempts = metadata["fallback_attempts"]
        assert isinstance(attempts, list) and attempts[0]["status"] == "model_overload"
        return
    failure = secondary if scenario == "switch" else primary
    assert failure.partial_messages  # Actual loop attached transient messages.
    assert metadata["category"] == failure.category.value
    assert f"category={failure.category.value}" in summary
    if scenario == "unknown":
        assert "provider=unknown" in summary and "cause_kind=unknown" in summary
        assert "provider" not in metadata and "cause_kind" not in metadata
    else:
        assert metadata["provider"] == failure.provider
        assert metadata["cause_kind"] == type(failure.raw_error).__name__
        assert f"provider={failure.provider}" in summary
        assert f"cause_kind={type(failure.raw_error).__name__}" in summary
        assert failure.provider is not None and failure.provider in history
    if scenario == "switch":
        assert metadata["effective_route_id"] == "secondary"
        assert metadata["fallback_attempts"] == [
            {"route_id": "primary", "status": "model_overload"}
        ]
    if scenario == "exhausted":
        handoff = metadata["fallback_handoff"]
        assert isinstance(handoff, dict)
        assert handoff["status"] == "continuation_stopped"
        assert handoff["failed_route_id"] == "primary"
        assert "observed" not in handoff
        assert "fallback_handoff=status:continuation_stopped" in summary
        assert "continuation_stopped" in history


def test_handoff_projection_excludes_free_text_and_bounds_identifiers(tmp_path: Path):
    handoff = {
        "status": "continuation_stopped",
        "reason": "PRIVATE_REASON",
        "failure_kind": "usage_limit",
        "failed_route_id": "x" * 161,
        "quality_policy": "preserve_quality",
        "observed": ["PRIVATE_OBSERVATION"],
        "save_error": "PRIVATE_SAVE_ERROR",
        "objective": "PRIVATE_OBJECTIVE",
    }
    expected = {
        "status": "continuation_stopped",
        "failure_kind": "usage_limit",
        "quality_policy": "preserve_quality",
    }
    assert safe_fallback_handoff(handoff) == expected
    result = CodingTurnResult(1, None, "failed", fallback_handoff=handoff)
    assert result.fallback_handoff == expected
    handoff["status"] = "mutated"
    assert result.fallback_handoff == expected
    output = format_cli_closeout(
        response_text=None,
        status="failed",
        execution_status="failed",
        failure_reason="Generic failure",
        fallback_handoff=handoff,
        provider="provider\nPRIVATE_INJECTION",
        cause_kind="C" * 161,
    )
    assert "PRIVATE" not in output
    assert "provider=unknown" in output and "cause_kind=unknown" in output

    store = SQLiteChatTranscriptStore(tmp_path / "legacy.sqlite3")
    CodingChatController.create(store, "legacy", tmp_path, "local_only", "Legacy")
    chat = CodingChatController(store, "legacy", tmp_path, "local_only")
    chat.turn("Old turn", lambda request: CodingTurnResult(1, None, "failed", "Old failure"))
    assert "Old failure" in chat.history()  # Records without new fields still load.
    # Previous experimental records must not reintroduce arbitrary handoff text.
    store.append_message(
        "legacy",
        role="assistant",
        content="Failure",
        metadata={
            "fallback_handoff": handoff,
            "provider": "provider\nPRIVATE_INJECTION",
        },
    )
    assert "PRIVATE" not in chat.history()
