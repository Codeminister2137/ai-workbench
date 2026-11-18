"""Loop health diagnostics: toolless streaks and repeated tool batches."""

from __future__ import annotations

from ai_agent import PermissionManager, ToolContext
from ai_agent.contracts import ToolCategory, ToolDefinition, ToolResult
from ai_agent.loop import AgentLoop
from ai_agent.tools.base import BaseTool, ToolRegistry
from ai_provider import AIToolCall


class ScriptedClient:
    backend = None

    def __init__(self, turns: list) -> None:
        from ai_provider import AIMessage, AIResponse, BackendInfo, BackendLocation, MessageRole

        self._turns = list(turns)
        self._factory = (AIMessage, AIResponse, BackendInfo, BackendLocation, MessageRole)
        self.backend = BackendInfo(provider="fake", model="test", location=BackendLocation.LOCAL)

    def complete(self, request):
        AIMessage, AIResponse, _BackendInfo, _Location, MessageRole = self._factory
        assert self._turns, "client script exhausted"
        turn = self._turns.pop(0)
        if isinstance(turn, str):
            message = AIMessage(MessageRole.ASSISTANT, turn)
        else:
            message = AIMessage(MessageRole.ASSISTANT, "", tool_calls=tuple(turn))
        from ai_provider import UsageMetadata

        return AIResponse(message=message, backend=self.backend, usage=UsageMetadata())


class EchoTool(BaseTool):
    @property
    def definition(self):
        return ToolDefinition("echo", "Echo probe", ToolCategory.READ)

    def execute(self, arguments, context):
        return ToolResult("echo", "ok")


def _loop(tmp_path, turns, diagnostics):
    client = ScriptedClient(turns)
    loop = AgentLoop(
        client,
        ToolRegistry((EchoTool(),)),
        ToolContext(tmp_path),
        permissions=PermissionManager(),
        diagnostic=diagnostics.append,
        require_grounded_reports=True,
    )
    return loop


def test_toolless_streak_warns_on_third_quiet_turn(tmp_path) -> None:
    diagnostics: list[str] = []
    loop = _loop(
        tmp_path,
        [
            "I created the thing",  # file-change claim, unsupported
            "I verified the thing",  # inspection claim, unsupported
            "I created and verified everything",  # both classes, unsupported
            "Done, no claims here.",
        ],
        diagnostics,
    )
    result = loop.run("Do it")
    assert result.response.message.content == "Done, no claims here."
    assert any(message.startswith("toolless_streak:") for message in diagnostics)


def test_repeat_tool_batch_warns_on_third_repeat(tmp_path) -> None:
    diagnostics: list[str] = []

    def call(i: int):
        return AIToolCall(f"call-{i}", "echo", {"n": 1})

    loop = _loop(tmp_path, [[call(1)], [call(2)], [call(3)], "Done."], diagnostics)
    loop.run("Do it")
    assert any(message.startswith("repeat_tool_batch:") for message in diagnostics)


def test_varied_batches_stay_quiet(tmp_path) -> None:
    diagnostics: list[str] = []
    loop = _loop(
        tmp_path,
        [
            [AIToolCall("c1", "echo", {"n": 1})],
            [AIToolCall("c2", "echo", {"n": 2})],
            "Done.",
        ],
        diagnostics,
    )
    loop.run("Do it")
    assert not [m for m in diagnostics if m.startswith(("repeat_tool_batch:", "toolless_streak:"))]
