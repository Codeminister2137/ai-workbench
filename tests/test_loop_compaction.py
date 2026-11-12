"""Loop-level compaction: summarize-then-continue with immune instructions."""

from __future__ import annotations

import pytest
from ai_agent import (
    AgentLoop,
    PermissionManager,
    PermissionPolicy,
    ToolContext,
)
from ai_provider import (
    AIMessage,
    AIResponse,
    AIToolCall,
    BackendInfo,
    BackendLocation,
    FinishReason,
    MessageRole,
    PrivacyClass,
    ProviderError,
    ProviderErrorCategory,
    UsageMetadata,
)


class CompactingClient:
    backend = BackendInfo(provider="fake", model="test", location=BackendLocation.LOCAL)

    def __init__(self, summary_text: str = "SUMMARY: task in progress") -> None:
        self.requests = []
        self.task_calls = 0
        self.summary_text = summary_text

    def complete(self, request):
        self.requests.append(request)
        if request.metadata.get("task_type") == "loop_compaction":
            return AIResponse(
                message=AIMessage(MessageRole.ASSISTANT, self.summary_text),
                backend=self.backend,
                finish_reason=FinishReason.STOP,
                usage=UsageMetadata(),
            )
        self.task_calls += 1
        if self.task_calls == 1:
            message = AIMessage(
                MessageRole.ASSISTANT,
                "",
                tool_calls=(
                    AIToolCall("call-1", "create_file", {"path": "out.txt", "content": "done"}),
                ),
            )
        else:
            message = AIMessage(MessageRole.ASSISTANT, "Finished")
        return AIResponse(
            message=message,
            backend=self.backend,
            finish_reason=FinishReason.STOP,
            usage=UsageMetadata(),
        )

    def stream(self, request):
        raise NotImplementedError


def _loop(client, tmp_path, **kwargs):
    from ai_agent.tools.base import ToolRegistry
    from ai_agent.tools.filesystem import CreateFileTool

    return AgentLoop(
        client,
        ToolRegistry((CreateFileTool(),)),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.permissive()),
        **kwargs,
    )


def test_compaction_continues_past_budget_with_immune_system(tmp_path) -> None:
    client = CompactingClient()
    system = "IMMUNE RULES: never delete files."
    prompt = "Create the output file, then report completion. " + "x" * 350
    result = _loop(
        client,
        tmp_path,
        max_iterations=5,
        loop_context_budget_chars=1000,
        compaction_tail_messages=2,
    ).run(system_prompt=system, prompt=prompt, privacy_class=PrivacyClass.LOCAL_ONLY)

    assert result.response.message.content == "Finished"
    assert result.compactions == 1
    assert (tmp_path / "out.txt").read_text() == "done"
    summary_requests = [
        request
        for request in client.requests
        if request.metadata.get("task_type") == "loop_compaction"
    ]
    assert len(summary_requests) == 1
    final_request = client.requests[-1]
    systems = [
        message.content for message in final_request.messages if message.role is MessageRole.SYSTEM
    ]
    assert systems[0] == system
    assert any("Compacted summary of earlier turns" in text for text in systems)
    assert any("SUMMARY: task in progress" in text for text in systems)
    tools = [message for message in final_request.messages if message.role is MessageRole.TOOL]
    assert tools and tools[-1].tool_call_id == "call-1"


def test_compaction_disabled_by_default(tmp_path) -> None:
    client = CompactingClient()
    loop = _loop(client, tmp_path, max_iterations=3)
    assert loop.loop_context_budget_chars is None
    result = loop.run("Create the file", privacy_class=PrivacyClass.LOCAL_ONLY)
    assert result.compactions == 0
    assert result.response.message.content == "Finished"


def test_compaction_thrash_limit_refuses_instead_of_looping(tmp_path) -> None:
    client = CompactingClient()
    with pytest.raises(ProviderError, match="after 0 compactions"):
        _loop(
            client,
            tmp_path,
            max_iterations=5,
            loop_context_budget_chars=950,
            compaction_tail_messages=2,
            max_compactions=0,
        ).run(
            system_prompt="SYS",
            prompt="Create the output file, then report completion. " + "x" * 350,
            privacy_class=PrivacyClass.LOCAL_ONLY,
        )


def test_compaction_falls_back_on_empty_summary(tmp_path) -> None:
    client = CompactingClient(summary_text="   ")
    result = _loop(
        client,
        tmp_path,
        max_iterations=5,
        loop_context_budget_chars=950,
        compaction_tail_messages=2,
    ).run(
        system_prompt="SYS",
        prompt="Create the output file, then report completion. " + "x" * 350,
        privacy_class=PrivacyClass.LOCAL_ONLY,
    )
    assert result.compactions == 1
    markers = [
        message.content
        for message in result.messages
        if message.role is MessageRole.SYSTEM and "mechanical fallback" in message.content
    ]
    assert len(markers) == 1
    assert "empty model summary" in markers[0] and "Do not claim" in markers[0]


def test_compaction_retries_empty_summary_once(tmp_path) -> None:
    class FlakyClient(CompactingClient):
        def __init__(self) -> None:
            super().__init__(summary_text="SUMMARY: recovered")
            self.compaction_calls = 0

        def complete(self, request):
            if request.metadata.get("task_type") == "loop_compaction":
                self.compaction_calls += 1
                if self.compaction_calls == 1:
                    return AIResponse(
                        message=AIMessage(MessageRole.ASSISTANT, "  "),
                        backend=self.backend,
                    )
            return super().complete(request)

    result = _loop(
        FlakyClient(),
        tmp_path,
        max_iterations=5,
        loop_context_budget_chars=950,
        compaction_tail_messages=2,
    ).run(
        system_prompt="SYS",
        prompt="Create the output file, then report completion. " + "x" * 350,
        privacy_class=PrivacyClass.LOCAL_ONLY,
    )
    assert result.compactions == 1
    assert not any("mechanical fallback" in m.content for m in result.messages)
    assert any("SUMMARY: recovered" in m.content for m in result.messages)


def test_compaction_falls_back_on_summarizer_error(tmp_path) -> None:
    class FailingClient(CompactingClient):
        def complete(self, request):
            if request.metadata.get("task_type") == "loop_compaction":
                raise ProviderError(
                    "boom",
                    category=ProviderErrorCategory.TIMEOUT,
                    provider=self.backend.provider,
                )
            return super().complete(request)

    result = _loop(
        FailingClient(),
        tmp_path,
        max_iterations=5,
        loop_context_budget_chars=950,
        compaction_tail_messages=2,
    ).run(
        system_prompt="SYS",
        prompt="Create the output file, then report completion. " + "x" * 350,
        privacy_class=PrivacyClass.LOCAL_ONLY,
    )
    assert result.compactions == 1
    assert any(
        "mechanical fallback" in m.content and "summarizer failed" in m.content
        for m in result.messages
    )


def test_tool_message_content_is_capped_with_marker(tmp_path) -> None:
    from ai_agent.loop import TOOL_MESSAGE_MAX_CHARS

    class LoudClient(CompactingClient):
        def complete(self, request):
            self.requests.append(request)
            if request.metadata.get("task_type") == "loop_compaction":
                return super().complete(request)
            self.task_calls += 1
            if self.task_calls == 1:
                message = AIMessage(
                    MessageRole.ASSISTANT,
                    "",
                    tool_calls=(AIToolCall("call-1", "read_file", {"path": "big.txt"}),),
                )
            else:
                message = AIMessage(MessageRole.ASSISTANT, "Finished")
            return AIResponse(
                message=message,
                backend=self.backend,
                finish_reason=FinishReason.STOP,
                usage=UsageMetadata(),
            )

    (tmp_path / "big.txt").write_text("y" * (TOOL_MESSAGE_MAX_CHARS + 5000), encoding="utf-8")
    from ai_agent.tools.base import ToolRegistry
    from ai_agent.tools.filesystem import ReadFileTool

    loop = AgentLoop(
        LoudClient(),
        ToolRegistry((ReadFileTool(),)),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.permissive()),
        max_iterations=5,
    )
    result = loop.run("Read it.", privacy_class=PrivacyClass.LOCAL_ONLY)
    tool_messages = [m for m in result.messages if m.role is MessageRole.TOOL]
    assert len(tool_messages) == 1
    assert len(tool_messages[0].content) < TOOL_MESSAGE_MAX_CHARS + 500
    assert "Output truncated" in tool_messages[0].content
    assert len(result.tool_results[0].output) > TOOL_MESSAGE_MAX_CHARS + 5000


def test_compaction_validates_budgets(tmp_path) -> None:
    with pytest.raises(ValueError, match="loop_context_budget_chars"):
        _loop(CompactingClient(), tmp_path, loop_context_budget_chars=0)
    with pytest.raises(ValueError, match="compaction_tail_messages"):
        _loop(CompactingClient(), tmp_path, compaction_tail_messages=0)
    with pytest.raises(ValueError, match="max_compactions"):
        _loop(CompactingClient(), tmp_path, max_compactions=-1)


def test_loop_budget_flag_defaults_to_enabled() -> None:
    from ai_agent.repo_assistant_args import build_argument_parser

    assert build_argument_parser().parse_args([]).loop_context_budget_chars == 100_000


def test_second_compaction_folds_prior_summary(tmp_path) -> None:
    class TwoToolClient(CompactingClient):
        def complete(self, request):
            self.requests.append(request)
            if request.metadata.get("task_type") == "loop_compaction":
                return AIResponse(
                    message=AIMessage(MessageRole.ASSISTANT, self.summary_text),
                    backend=self.backend,
                )
            self.task_calls += 1
            if self.task_calls <= 2:
                message = AIMessage(
                    MessageRole.ASSISTANT,
                    "",
                    tool_calls=(
                        AIToolCall(
                            f"call-{self.task_calls}",
                            "create_file",
                            {
                                "path": f"out{self.task_calls}.txt",
                                "content": "done",
                            },
                        ),
                    ),
                )
            else:
                message = AIMessage(MessageRole.ASSISTANT, "Finished")
            return AIResponse(
                message=message,
                backend=self.backend,
                finish_reason=FinishReason.STOP,
                usage=UsageMetadata(),
            )

    client = TwoToolClient()
    result = _loop(
        client,
        tmp_path,
        max_iterations=6,
        loop_context_budget_chars=700,
        compaction_tail_messages=2,
    ).run(
        system_prompt="SYS",
        prompt="Create the output files, then report completion. " + "x" * 100,
        privacy_class=PrivacyClass.LOCAL_ONLY,
    )
    assert result.response.message.content == "Finished"
    assert result.compactions == 2
    assert (tmp_path / "out1.txt").read_text() == "done"
    assert (tmp_path / "out2.txt").read_text() == "done"
    task_requests = [
        request
        for request in client.requests
        if request.metadata.get("task_type") != "loop_compaction"
    ]
    summaries = [
        message
        for message in task_requests[-1].messages
        if message.role is MessageRole.SYSTEM
        and "Compacted summary of earlier turns" in message.content
    ]
    assert len(summaries) == 1
