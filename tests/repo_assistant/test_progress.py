"""Human progress narration over agent telemetry (P4 R1)."""

from __future__ import annotations

import threading
import time

import pytest
from ai_agent.progress import heartbeat, narrate, reporter


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "local_agent_activity: model_request - provider=ollama model=qwen3:14b",
            "Asking qwen3:14b (ollama)…",
        ),
        ("local_agent_activity: ollama_start - base_url=http://x", "Starting local Ollama…"),
        (
            "local_agent_activity: failed - earlier receipts follow",
            "Agent run failed — earlier receipts follow",
        ),
        (
            "local_agent_activity: completed - iterations=3 tool_results=5 usage=1.2k",
            "Finished (completed): 3 iterations, 5 tool results (1.2k)",
        ),
        (
            "local_tool_activity: recorded - read_file: src.py ok",
            "Tool read_file: src.py ok",
        ),
        (
            "local_tool_activity: ok - write_file: done",
            "Tool write_file (ok): done",
        ),
        (
            "delegated_agent_activity: started - coding_subtask xyz",
            "Delegating subtask: coding_subtask xyz",
        ),
        (
            "delegated_agent_activity: started - context_extraction",
            "Delegating subtask: context_extraction",
        ),
        (
            "delegated_agent_activity: model_request - route=codex model=gpt-x",
            "Subagent asking gpt-x (codex)…",
        ),
        (
            "delegated_agent_activity: completed - iterations=2 tool_results=1",
            "Subagent done: 2 iterations, 1 tool results",
        ),
        (
            "delegated_agent_activity: failed - kind=timeout detail=slow",
            "Subagent failed (timeout): slow",
        ),
        ("model_output_errors: 2", "Model output errors so far: 2"),
        ("completion_failures: 1", "Completion failures so far: 1"),
        (
            "delegation_fanout: n=3 workers=a,b,c",
            "Fanning out to 3 workers (a,b,c)…",
        ),
        (
            "loop_compaction: n=2 summarized=10 tail=4",
            "Compacting transcript…",
        ),
        (
            "model_output_error: provider=x category=y cause_kind=z",
            "Model output error — attempting recovery",
        ),
        (
            "completion_recovery: errors=1 action=feedback",
            "Recovery (1 errors): feedback",
        ),
        (
            "completion_check: missing=tests",
            "Completion check: still missing tests",
        ),
        (
            "groundedness_check: unsupported=claims",
            "Groundedness check: unsupported claims",
        ),
        ("fallback_history: full; kept 3", "Fallback: full; kept 3"),
        (
            "context_budget_omitted: big.md",
            "Context: omitted big.md (over budget)",
        ),
        (
            "context_file_truncated: big.md original_chars=99 budget_chars=5",
            "Context: truncated big.md",
        ),
        (
            "scrutiny_activity: failed - bad",
            "Scrutiny failed: bad",
        ),
        (
            "repair_activity: started - fix it",
            "Repair started: fix it",
        ),
        (
            "turn_summary: n=2 tools=read_file,edit_file files=a.py errors=0",
            "Turn 2: read_file,edit_file on a.py (0 errors)",
        ),
        (
            "turn_summary: n=1 tools=list_dir files=- errors=0",
            "Turn 1: list_dir (0 errors)",
        ),
        (
            "turn_summary: n=3 tools=- files=- errors=1",
            "Turn 3: no tools (1 errors)",
        ),
    ],
)
def test_narrate_known_events(raw: str, expected: str) -> None:
    assert narrate(raw) == expected


def test_narrate_passes_unknown_lines_through() -> None:
    assert narrate("something entirely new: x=1") == "something entirely new: x=1"
    assert narrate("") == ""


def test_narrate_never_drops_failure_details() -> None:
    line = "local_agent_activity: failed - boom happened here"
    assert "boom happened here" in narrate(line)


def test_reporter_verbose_prints_raw(capsys: pytest.CaptureFixture) -> None:
    reporter(verbose=True)("local_agent_activity: model_request - provider=a model=b")
    assert capsys.readouterr().out.strip() == (
        "local_agent_activity: model_request - provider=a model=b"
    )


def test_reporter_default_narrates(capsys: pytest.CaptureFixture) -> None:
    reporter(verbose=False)("local_agent_activity: model_request - provider=a model=b")
    assert capsys.readouterr().out.strip() == "Asking b (a)…"


def test_narrate_heartbeat_line() -> None:
    assert narrate("heartbeat: model turn 2 (31s elapsed, still working)") == (
        "Still working: model turn 2 (31s)…"
    )


def test_heartbeat_beats_during_slow_call() -> None:
    events: list[str] = []
    with heartbeat("model turn 1", events.append, interval_seconds=0.05):
        time.sleep(0.22)
    assert len(events) >= 2
    assert all(e.startswith("heartbeat: model turn 1 (") for e in events)
    assert narrate(events[0]).startswith("Still working: model turn 1 (")


def test_heartbeat_silent_when_quick() -> None:
    events: list[str] = []
    with heartbeat("model turn 1", events.append, interval_seconds=60):
        pass
    assert events == []


def test_heartbeat_without_sink_is_noop() -> None:
    before = threading.active_count()
    with heartbeat("model turn 1", None, interval_seconds=0.01):
        time.sleep(0.05)
    assert threading.active_count() <= before


def test_heartbeat_joins_thread_on_error() -> None:
    events: list[str] = []
    before = threading.active_count()
    with pytest.raises(RuntimeError, match="boom"):
        with heartbeat("model turn 1", events.append, interval_seconds=0.01):
            raise RuntimeError("boom")
    assert threading.active_count() <= before


def _streaming_loop_fixture(tmp_path, script):
    from ai_agent import PermissionManager, PermissionPolicy, ToolContext, default_coding_tools
    from ai_agent.loop import AgentLoop
    from ai_provider import (
        AIMessage,
        AIResponse,
        AIStreamDelta,
        AIStreamFinal,
        BackendInfo,
        BackendLocation,
        FinishReason,
        MessageRole,
        UsageMetadata,
    )

    class StreamingClient:
        backend = BackendInfo(provider="fake", model="test", location=BackendLocation.LOCAL)

        def __init__(self, turns):
            self.turns = list(turns)
            self.completed = 0

        def complete(self, request):
            self.completed += 1
            return AIResponse(
                message=AIMessage(MessageRole.ASSISTANT, "fallback"),
                backend=self.backend,
                finish_reason=FinishReason.STOP,
                usage=UsageMetadata(),
            )

        def stream(self, request):
            turn = self.turns.pop(0)
            if isinstance(turn, str):
                yield AIStreamDelta(content=turn)
                yield AIStreamFinal(
                    response=AIResponse(
                        message=AIMessage(MessageRole.ASSISTANT, turn),
                        backend=self.backend,
                        finish_reason=FinishReason.STOP,
                        usage=UsageMetadata(),
                    )
                )
            else:
                yield AIStreamDelta(content="")
                yield AIStreamFinal(
                    response=AIResponse(
                        message=AIMessage(MessageRole.ASSISTANT, "", tool_calls=tuple(turn)),
                        backend=self.backend,
                        finish_reason=FinishReason.STOP,
                        usage=UsageMetadata(),
                    )
                )

    client = StreamingClient(script)
    loop = AgentLoop(
        client,
        default_coding_tools(),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.permissive()),
    )
    return client, loop


def test_loop_streams_text_when_sink_set(tmp_path) -> None:
    chunks: list[str] = []
    client, loop = _streaming_loop_fixture(tmp_path, ["Hello there"])
    loop.stream_text = chunks.append
    result = loop.run("Say hi")
    assert "".join(chunks) == "Hello there"
    assert result.response.message.content == "Hello there"
    assert client.completed == 0


def test_loop_falls_back_to_complete_without_stream(tmp_path) -> None:
    from typing import cast

    from ai_agent import PermissionManager, PermissionPolicy, ToolContext, default_coding_tools
    from ai_agent.loop import AgentLoop
    from ai_provider import (
        AIMessage,
        AIResponse,
        BackendInfo,
        BackendLocation,
        FinishReason,
        MessageRole,
        UsageMetadata,
    )
    from ai_provider.contracts import ChatClient

    class PlainClient:
        # Intentionally stream-less: this test pins the complete() fallback.
        backend = BackendInfo(provider="fake", model="test", location=BackendLocation.LOCAL)

        def complete(self, request):
            return AIResponse(
                message=AIMessage(MessageRole.ASSISTANT, "done"),
                backend=self.backend,
                finish_reason=FinishReason.STOP,
                usage=UsageMetadata(),
            )

    chunks: list[str] = []
    result = AgentLoop(
        cast(ChatClient, PlainClient()),
        default_coding_tools(),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.permissive()),
        stream_text=chunks.append,
    ).run("Say hi")
    assert result.response.message.content == "done"
    assert chunks == []


def test_loop_stream_without_final_raises_retryable(tmp_path) -> None:
    from ai_agent import PermissionManager, PermissionPolicy, ToolContext, default_coding_tools
    from ai_agent.loop import AgentLoop
    from ai_provider import (
        AIStreamDelta,
        BackendInfo,
        BackendLocation,
        ProviderError,
        ProviderErrorCategory,
    )

    class BrokenClient:
        backend = BackendInfo(provider="fake", model="test", location=BackendLocation.LOCAL)

        def complete(self, request):
            raise AssertionError("complete() is not used on the stream path")

        def stream(self, request):
            yield AIStreamDelta(content="partial")

    with pytest.raises(ProviderError) as excinfo:
        AgentLoop(
            BrokenClient(),
            default_coding_tools(),
            ToolContext(tmp_path),
            permissions=PermissionManager(policy=PermissionPolicy.permissive()),
            stream_text=lambda chunk: None,
        ).run("Say hi")
    assert excinfo.value.category is ProviderErrorCategory.RETRYABLE


def test_stream_writer_emits_raw_chunks(capsys: pytest.CaptureFixture) -> None:
    from ai_agent.progress import stream_writer

    write = stream_writer()
    write("hel")
    write("lo")
    assert capsys.readouterr().out == "hello"


def test_consume_stream_forwards_text_and_returns_final() -> None:
    from ai_provider import (
        AIMessage,
        AIRequest,
        AIResponse,
        AIStreamDelta,
        AIStreamFinal,
        BackendInfo,
        BackendLocation,
        FinishReason,
        MessageRole,
        UsageMetadata,
    )
    from ai_provider.contracts import consume_stream

    class FakeClient:
        backend = BackendInfo(provider="fake", model="t", location=BackendLocation.LOCAL)

        def complete(self, request):
            raise AssertionError("complete() is not used on the stream path")

        def stream(self, request):
            yield AIStreamDelta(content="he")
            yield AIStreamDelta(content="llo")
            yield AIStreamFinal(
                response=AIResponse(
                    message=AIMessage(MessageRole.ASSISTANT, "hello"),
                    backend=self.backend,
                    finish_reason=FinishReason.STOP,
                    usage=UsageMetadata(),
                )
            )

    chunks: list[str] = []
    request = AIRequest(messages=(AIMessage(MessageRole.USER, "hi"),))
    response = consume_stream(FakeClient(), request, chunks.append)
    assert "".join(chunks) == "hello"
    assert response.message.content == "hello"


def test_consume_stream_without_final_raises_retryable() -> None:
    from ai_provider import (
        AIMessage,
        AIRequest,
        AIStreamDelta,
        BackendInfo,
        BackendLocation,
        MessageRole,
        ProviderError,
        ProviderErrorCategory,
    )
    from ai_provider.contracts import consume_stream

    class BrokenClient:
        backend = BackendInfo(provider="fake", model="t", location=BackendLocation.LOCAL)

        def complete(self, request):
            raise AssertionError("complete() is not used on the stream path")

        def stream(self, request):
            yield AIStreamDelta(content="partial")

    request = AIRequest(messages=(AIMessage(MessageRole.USER, "hi"),))
    with pytest.raises(ProviderError) as excinfo:
        consume_stream(BrokenClient(), request, lambda chunk: None)
    assert excinfo.value.category is ProviderErrorCategory.RETRYABLE


def test_loop_emits_turn_summary_and_records_it(tmp_path) -> None:
    from ai_agent import PermissionManager, PermissionPolicy, ToolContext, default_coding_tools
    from ai_agent.loop import AgentLoop
    from ai_provider import (
        AIMessage,
        AIResponse,
        AIToolCall,
        BackendInfo,
        BackendLocation,
        FinishReason,
        MessageRole,
        UsageMetadata,
    )

    class ScriptedClient:
        backend = BackendInfo(provider="fake", model="test", location=BackendLocation.LOCAL)

        def __init__(self, turns):
            self.turns = list(turns)

        def complete(self, request):
            turn = self.turns.pop(0)
            message = (
                AIMessage(MessageRole.ASSISTANT, turn)
                if isinstance(turn, str)
                else AIMessage(MessageRole.ASSISTANT, "", tool_calls=tuple(turn))
            )
            return AIResponse(
                message=message,
                backend=self.backend,
                finish_reason=FinishReason.STOP,
                usage=UsageMetadata(),
            )

        def stream(self, request):
            raise NotImplementedError

    events: list[str] = []
    client = ScriptedClient(
        [[AIToolCall("c1", "create_file", {"path": "out.txt", "content": "done"})], "Finished"]
    )
    result = AgentLoop(
        client,
        default_coding_tools(),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.permissive()),
        diagnostic=events.append,
    ).run("Create the file")
    assert result.turn_summaries == ("turn_summary: n=1 tools=create_file files=out.txt errors=0",)
    assert result.turn_summaries[0] in events
    assert narrate(result.turn_summaries[0]) == "Turn 1: create_file on out.txt (0 errors)"
