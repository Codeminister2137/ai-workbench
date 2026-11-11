"""Loop usage metering: per-call accumulation exposed on the result."""

from __future__ import annotations

from ai_agent import (
    AgentLoop,
    PermissionManager,
    PermissionPolicy,
    ToolContext,
)
from ai_agent.external_reporting import usage_summary
from ai_agent.loop import _combine_usage
from ai_agent.tools.base import ToolRegistry
from ai_provider import (
    AIMessage,
    AIResponse,
    AIToolCall,
    BackendInfo,
    BackendLocation,
    FinishReason,
    MessageRole,
    PrivacyClass,
    UsageMetadata,
    UsageSource,
)


def _usage(
    source=UsageSource.PROVIDER_REPORTED,
    input_tokens=None,
    output_tokens=None,
    total_tokens=None,
    reported_cost_usd=None,
):
    return UsageMetadata(
        source=source,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        reported_cost_usd=reported_cost_usd,
    )


class MeteredClient:
    backend = BackendInfo(provider="fake", model="test", location=BackendLocation.LOCAL)

    def __init__(self, usages):
        self.usages = list(usages)
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        usage = self.usages.pop(0) if self.usages else UsageMetadata()
        return AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, "Done"),
            backend=self.backend,
            finish_reason=FinishReason.STOP,
            usage=usage,
        )

    def stream(self, request):
        raise NotImplementedError


def _run(client, tmp_path, **kwargs):
    loop = AgentLoop(
        client,
        ToolRegistry(()),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.permissive()),
        **kwargs,
    )
    return loop.run("Go", privacy_class=PrivacyClass.LOCAL_ONLY)


def test_combine_sums_and_weakest_link_source() -> None:
    reported = _combine_usage(
        _usage(input_tokens=10, output_tokens=5, reported_cost_usd=0.01),
        _usage(input_tokens=20, output_tokens=7, reported_cost_usd=0.02),
    )
    assert reported.source is UsageSource.PROVIDER_REPORTED
    assert (reported.input_tokens, reported.output_tokens) == (30, 12)
    assert reported.total_tokens == 42
    assert reported.reported_cost_usd == 0.03

    mixed = _combine_usage(
        _usage(UsageSource.PROVIDER_REPORTED, input_tokens=1),
        _usage(UsageSource.ESTIMATED, input_tokens=1),
    )
    assert mixed.source is UsageSource.ESTIMATED

    gapped = _combine_usage(
        _usage(UsageSource.PROVIDER_REPORTED, input_tokens=1),
        _usage(UsageSource.UNAVAILABLE),
    )
    assert gapped.source is UsageSource.UNAVAILABLE
    assert gapped.input_tokens == 1  # partial sums still exposed

    assert _combine_usage(UsageMetadata(), UsageMetadata()) == UsageMetadata()


def test_run_accumulates_iterations(tmp_path) -> None:
    class TwoTurnClient(MeteredClient):
        def complete(self, request):
            self.requests.append(request)
            if len(self.requests) == 1:
                return AIResponse(
                    message=AIMessage(
                        MessageRole.ASSISTANT,
                        "",
                        tool_calls=(AIToolCall("c1", "missing_tool", {}),),
                    ),
                    backend=self.backend,
                    finish_reason=FinishReason.STOP,
                    usage=_usage(input_tokens=100, output_tokens=10),
                )
            return super().complete(request)

    result = _run(
        TwoTurnClient([_usage(input_tokens=50, output_tokens=5)]),
        tmp_path,
        max_iterations=3,
    )
    assert result.usage.source is UsageSource.PROVIDER_REPORTED
    assert (result.usage.input_tokens, result.usage.output_tokens) == (150, 15)


def test_unknown_calls_stay_unavailable(tmp_path) -> None:
    result = _run(MeteredClient([]), tmp_path)
    assert result.usage.source is UsageSource.UNAVAILABLE
    assert result.usage.input_tokens is None


def test_compaction_usage_is_included(tmp_path) -> None:
    from ai_agent.tools.filesystem import CreateFileTool

    class CompactingMeteredClient(MeteredClient):
        def __init__(self):
            super().__init__(
                [
                    _usage(input_tokens=100, output_tokens=10),
                    _usage(input_tokens=300, output_tokens=40),
                    _usage(input_tokens=120, output_tokens=12),
                ]
            )
            self.task_calls = 0

        def complete(self, request):
            if request.metadata.get("task_type") == "loop_compaction":
                usage = self.usages.pop(0)
                return AIResponse(
                    message=AIMessage(MessageRole.ASSISTANT, "SUMMARY: in progress"),
                    backend=self.backend,
                    finish_reason=FinishReason.STOP,
                    usage=usage,
                )
            self.task_calls += 1
            usage = self.usages.pop(0)
            if self.task_calls == 1:
                message = AIMessage(
                    MessageRole.ASSISTANT,
                    "",
                    tool_calls=(
                        AIToolCall("call-1", "create_file", {"path": "o.txt", "content": "d"}),
                    ),
                )
            else:
                message = AIMessage(MessageRole.ASSISTANT, "Finished")
            return AIResponse(
                message=message,
                backend=self.backend,
                finish_reason=FinishReason.STOP,
                usage=usage,
            )

    client = CompactingMeteredClient()
    loop = AgentLoop(
        client,
        ToolRegistry((CreateFileTool(),)),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.permissive()),
        max_iterations=5,
        loop_context_budget_chars=1000,
        compaction_tail_messages=2,
    )
    result = loop.run(
        system_prompt="IMMUNE RULES: never delete files.",
        prompt="Create the output file, then report completion. " + "x" * 350,
        privacy_class=PrivacyClass.LOCAL_ONLY,
    )
    assert result.compactions == 1
    assert result.usage.input_tokens == 520
    assert result.usage.output_tokens == 62
    assert result.usage.source is UsageSource.PROVIDER_REPORTED


def test_usage_summary_formats_gaps() -> None:
    assert usage_summary(None) == "unavailable"
    assert (
        usage_summary(_usage(input_tokens=10, output_tokens=5)) == "in=10 out=5 (provider_reported)"
    )
    assert (
        usage_summary(_usage(UsageSource.ESTIMATED, input_tokens=10)) == "in=10 out=? (estimated)"
    )
    assert usage_summary(UsageMetadata()) == "in=? out=? (unavailable)"
