"""Exact reviewed-input admission and tool-free CLI egress controls."""

from dataclasses import replace

import pytest
from ai_agent import reviewed_task
from ai_provider import AIMessage, AIResponse, AIToolCall, MessageRole, PrivacyClass
from ai_provider.contracts import BackendInfo, BackendLocation, FinishReason, ProviderContinuation
from ai_provider.errors import ProviderError, ProviderErrorCategory
from ai_provider.reviewed_input import (
    has_reviewed_non_sensitive_input,
    reviewed_input_request,
    reviewed_input_sha256,
)

TEXT = "Review this non-sensitive example: def add(a, b): return a + b\n"


def reviewed(text=TEXT):
    return reviewed_input_request(
        text, approved_sha256=reviewed_input_sha256(text), model=reviewed_task.DEFAULT_MODEL
    )


@pytest.mark.parametrize(
    "text", [TEXT, "\u03bb\r\n", "a" * 65_536], ids=["code", "unicode", "limit"]
)
def test_exact_review_retains_bytes_without_claiming_public(text):
    request = reviewed(text)
    assert has_reviewed_non_sensitive_input(request)
    assert request.messages == (AIMessage(MessageRole.USER, text),)
    assert "public_or_synthetic" not in request.metadata


@pytest.mark.parametrize(
    "text", ["", "  \n", "\u03bb" * 32_769], ids=["empty", "blank", "oversized"]
)
def test_empty_or_oversized_input_refused(text):
    with pytest.raises(ValueError):
        reviewed(text)


@pytest.mark.parametrize("digest", [None, True, "0" * 64, "A" * 64, "\u03bb" * 64])
def test_unapproved_or_mismatched_digest_refused(digest):
    with pytest.raises(ValueError, match="Approval digest"):
        reviewed_input_request(TEXT, approved_sha256=digest, model=reviewed_task.DEFAULT_MODEL)


@pytest.mark.parametrize(
    "change",
    [
        {"content": TEXT + "added private context"},
        {"role": MessageRole.SYSTEM},
        {"role": MessageRole.TOOL},
        {"role": MessageRole.ASSISTANT},
        {"name": "source"},
        {"tool_call_id": "result"},
        {"tool_calls": (AIToolCall("x", "read_file", {"path": ".env"}),)},
        {"continuation": ProviderContinuation("openrouter", "model", "url", {"x": "secret"})},
    ],
)
def test_changed_content_or_message_context_invalidates_review(change):
    request = reviewed()
    assert not has_reviewed_non_sensitive_input(
        replace(request, messages=(replace(request.messages[0], **change),))
    )


@pytest.mark.parametrize(
    "change",
    [
        {"privacy_class": PrivacyClass.LOCAL_ONLY},
        {"privacy_class": PrivacyClass.EXTERNAL_ALLOWED},
        {"privacy_class": PrivacyClass.SENSITIVE_REVIEW_REQUIRED},
        {"messages": ()},
        {"messages": (AIMessage(MessageRole.SYSTEM, "private instructions"), *reviewed().messages)},
        {"max_output_tokens": None},
        {"max_output_tokens": True},
        {"max_output_tokens": 0},
        {"max_output_tokens": 8193},
    ],
)
def test_expanded_request_does_not_inherit_review(change):
    assert not has_reviewed_non_sensitive_input(replace(reviewed(), **change))


def test_tool_schema_invalidates_review():
    from ai_agent.loop import _tool_definition
    from ai_agent.tools.filesystem import ReadFileTool

    assert not has_reviewed_non_sensitive_input(
        replace(reviewed(), tools=(_tool_definition(ReadFileTool().definition),))
    )


def test_prepare_does_not_create_client_or_read_ambient_context(monkeypatch, tmp_path, capsys):
    path = tmp_path / "task.txt"
    path.write_text(TEXT, encoding="utf-8", newline="")
    (tmp_path / "AGENTS.md").write_text("private instructions", encoding="utf-8")
    (tmp_path / "CURRENT_CONTEXT.md").write_text("private handoff", encoding="utf-8")
    monkeypatch.setattr(reviewed_task, "create_chat_client", lambda _: pytest.fail("network"))
    assert reviewed_task.main([str(path)]) == 0
    output = capsys.readouterr().out
    assert reviewed_input_sha256(TEXT) in output
    assert TEXT not in output and "private handoff" not in output
    assert '"mode": "prepare_only"' in output


@pytest.mark.parametrize(
    "extra", [[], ["--confirm-non-sensitive"], ["--approved-sha256", "0" * 64]]
)
def test_execute_needs_both_explicit_confirmation_and_digest(tmp_path, extra):
    with pytest.raises(SystemExit):
        reviewed_task.main([str(tmp_path / "missing"), "--execute", *extra])


def test_modified_input_refused_before_client_creation(monkeypatch, tmp_path, capsys):
    path = tmp_path / "task.txt"
    path.write_text(TEXT + "private later edit", encoding="utf-8")
    monkeypatch.setattr(reviewed_task, "create_chat_client", lambda _: pytest.fail("network"))
    assert (
        reviewed_task.main(
            [
                str(path),
                "--execute",
                "--confirm-non-sensitive",
                "--approved-sha256",
                reviewed_input_sha256(TEXT),
            ]
        )
        == 2
    )
    assert "private later edit" not in capsys.readouterr().out


def test_exact_input_only_and_one_call_even_if_provider_requests_tool(
    monkeypatch, tmp_path, capsys
):
    path = tmp_path / "task.txt"
    path.write_text(TEXT, encoding="utf-8", newline="")
    monkeypatch.setenv("UNRELATED_FAKE_KEY", "must-not-be-in-request")
    requests = []

    class Client:
        def complete(self, request):
            requests.append(request)
            return AIResponse(
                AIMessage(MessageRole.ASSISTANT, "unverified reply"),
                backend=BackendInfo("mock", "synthetic", BackendLocation.LOCAL),
                finish_reason=FinishReason.STOP,
                tool_calls=(AIToolCall("x", "read_file", {"path": ".env"}),),
            )

    def factory(config):
        assert config.require_free_model
        assert config.provider.value == "openrouter"
        return Client()

    monkeypatch.setattr(reviewed_task, "create_chat_client", factory)
    assert (
        reviewed_task.main(
            [
                str(path),
                "--execute",
                "--confirm-non-sensitive",
                "--approved-sha256",
                reviewed_input_sha256(TEXT),
            ]
        )
        == 1
    )
    assert len(requests) == 1 and has_reviewed_non_sensitive_input(requests[0])
    assert requests[0].messages[0].content == TEXT
    assert "must-not-be-in-request" not in repr(requests)
    assert "no tool execution or continuation" in capsys.readouterr().out


def test_provider_refusal_is_not_retried_or_echoed(monkeypatch, tmp_path, capsys):
    path = tmp_path / "task.txt"
    path.write_text(TEXT, encoding="utf-8", newline="")
    calls = []

    class Client:
        def complete(self, request):
            calls.append(request)
            raise ProviderError("private upstream error", category=ProviderErrorCategory.RATE_LIMIT)

    monkeypatch.setattr(reviewed_task, "create_chat_client", lambda _: Client())
    assert (
        reviewed_task.main(
            [
                str(path),
                "--execute",
                "--confirm-non-sensitive",
                "--approved-sha256",
                reviewed_input_sha256(TEXT),
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    assert len(calls) == 1 and "private upstream error" not in output
    assert "rate_limit" in output
