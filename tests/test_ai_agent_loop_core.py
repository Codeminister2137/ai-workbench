"""Loop-core mechanics: pending/events, never-replay, approvals, recovery."""

from __future__ import annotations

import pytest
from ai_agent import PermissionManager, PermissionPolicy, ToolContext, default_coding_tools
from ai_agent.contracts import ToolCall, ToolCategory, ToolDefinition, ToolResult
from ai_agent.loop import AgentLoop, ToolExecutionEvent
from ai_agent.recovery import (
    MAX_ANSWER_CHARS,
    MAX_QUESTION_CHARS,
    OwnerAnswer,
    PendingOperation,
    RecoveryState,
    digest_text,
)
from ai_agent.shared_approvals import TerminalApproval
from ai_agent.tools.base import BaseTool, ToolRegistry
from ai_agent.tools.base import ToolContext as Ctx
from ai_agent.tools.filesystem import CreateFileTool
from ai_provider import (
    AIMessage,
    AIResponse,
    AIToolCall,
    BackendInfo,
    BackendLocation,
    FinishReason,
    MessageRole,
    ProviderError,
    ProviderErrorCategory,
    UsageMetadata,
)


class ScriptedClient:
    """Serve scripted assistant turns: tool-call lists or final text."""

    backend = BackendInfo(provider="fake", model="test", location=BackendLocation.LOCAL)

    def __init__(self, turns: list) -> None:
        self.turns = list(turns)
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        assert self.turns, "client script exhausted"
        turn = self.turns.pop(0)
        if isinstance(turn, str):
            message = AIMessage(MessageRole.ASSISTANT, turn)
        else:
            message = AIMessage(MessageRole.ASSISTANT, "", tool_calls=tuple(turn))
        return AIResponse(
            message=message,
            backend=self.backend,
            finish_reason=FinishReason.STOP,
            usage=UsageMetadata(),
        )

    def stream(self, request):
        raise NotImplementedError


def permissive() -> PermissionManager:
    return PermissionManager(policy=PermissionPolicy.permissive())


def write_call() -> ToolCall:
    return ToolCall("create_file", {"path": "a.txt", "content": "x"})


# --- loop.py: pending set + tool_started/tool_completed events ---


def test_tool_events_bracket_each_dispatched_execution(tmp_path):
    events: list[ToolExecutionEvent] = []
    client = ScriptedClient(
        [[AIToolCall("call-1", "create_file", {"path": "out.txt", "content": "done"})], "Finished"]
    )
    result = AgentLoop(
        client,
        default_coding_tools(),
        ToolContext(tmp_path),
        permissions=permissive(),
        on_event=events.append,
    ).run("Create the file")

    assert [(e.type, e.name, e.call_id, e.is_error) for e in events] == [
        ("tool_started", "create_file", "call-1", False),
        ("tool_completed", "create_file", "call-1", False),
    ]
    assert result.tool_results[0].is_error is False
    assert (tmp_path / "out.txt").read_text() == "done"


def test_pending_call_is_visible_during_execution_only(tmp_path):
    holder: dict[str, AgentLoop] = {}
    seen: list[tuple] = []

    class PendingProbe(BaseTool):
        @property
        def definition(self):
            return ToolDefinition("probe", "Pending probe", ToolCategory.READ)

        def execute(self, arguments, context):
            seen.append(tuple((c.name, c.call_id) for c in holder["loop"].pending))
            return ToolResult("probe", "ok")

    client = ScriptedClient([[AIToolCall("probe-1", "probe", {})], "Done"])
    loop = AgentLoop(
        client, ToolRegistry((PendingProbe(),)), ToolContext(tmp_path), permissions=permissive()
    )
    holder["loop"] = loop
    assert loop.pending == ()
    loop.run("Probe pending")
    assert seen == [(("probe", "probe-1"),)]
    assert loop.pending == ()


def test_refusals_produce_error_results_without_events(tmp_path):
    events: list[ToolExecutionEvent] = []
    client = ScriptedClient(
        [
            [
                AIToolCall("u1", "missing_tool", {}),
                AIToolCall("d1", "create_file", {"path": "out.txt", "content": "x"}),
            ],
            [AIToolCall("u1", "missing_tool", {})],
            "Stopped",
        ]
    )
    result = AgentLoop(
        client,
        default_coding_tools(),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.read_only()),
        on_event=events.append,
    ).run("Inspect only")

    assert [item.is_error for item in result.tool_results] == [True, True, True]
    assert "unknown tool" in result.tool_results[0].output
    assert "not authorized" in result.tool_results[1].output
    assert "unknown tool" in result.tool_results[2].output
    assert events == []
    assert not list(tmp_path.iterdir())


# --- loop.py: never auto-replay ---


def test_identical_call_in_later_turn_executes_as_new_instruction(tmp_path):
    # Never-replay binds one response batch and host retries, not the model:
    # a later turn re-issuing an identical call is a new instruction and runs.
    events: list[ToolExecutionEvent] = []
    repeated = {"path": "out.txt", "content": "first"}
    client = ScriptedClient(
        [
            [AIToolCall("dup-1", "create_file", dict(repeated))],
            [AIToolCall("dup-1", "create_file", dict(repeated))],
            "Stopped",
        ]
    )
    result = AgentLoop(
        client,
        default_coding_tools(),
        ToolContext(tmp_path),
        permissions=permissive(),
        on_event=events.append,
    ).run("Create the file")

    assert result.iterations == 3
    assert len(result.tool_results) == 2
    assert "not replayed" not in result.tool_results[1].output
    assert (tmp_path / "out.txt").read_text() == "first"
    assert [e.type for e in events] == [
        "tool_started",
        "tool_completed",
        "tool_started",
        "tool_completed",
    ]


def test_failed_call_in_same_batch_is_not_replayed(tmp_path):
    events: list[ToolExecutionEvent] = []
    calls: list[str] = []

    class Flaky(BaseTool):
        @property
        def definition(self):
            return ToolDefinition("flaky", "Always fails", ToolCategory.READ)

        def execute(self, arguments, context):
            calls.append("ran")
            return ToolResult("flaky", "Error: flaky failure", is_error=True)

    client = ScriptedClient(
        [
            [
                AIToolCall("flaky-1", "flaky", {}),
                AIToolCall("flaky-1", "flaky", {}),
            ],
            "Stopped",
        ]
    )
    result = AgentLoop(
        client,
        ToolRegistry((Flaky(),)),
        ToolContext(tmp_path),
        permissions=permissive(),
        on_event=events.append,
    ).run("Exercise flaky tool")

    assert [item.is_error for item in result.tool_results] == [True, True]
    assert "flaky failure" in result.tool_results[0].output
    assert "not replayed" in result.tool_results[1].output
    assert calls == ["ran"]
    assert [e.type for e in events] == ["tool_started", "tool_completed"]


def test_duplicate_call_id_within_one_response_executes_once(tmp_path):
    events: list[ToolExecutionEvent] = []
    client = ScriptedClient(
        [
            [
                AIToolCall("same", "create_file", {"path": "a.txt", "content": "a"}),
                AIToolCall("same", "create_file", {"path": "a.txt", "content": "a"}),
            ],
            "Done",
        ]
    )
    result = AgentLoop(
        client,
        default_coding_tools(),
        ToolContext(tmp_path),
        permissions=permissive(),
        on_event=events.append,
    ).run("Create files")

    assert [item.is_error for item in result.tool_results] == [False, True]
    assert "not replayed" in result.tool_results[1].output
    assert (tmp_path / "a.txt").read_text() == "a"
    assert [e.type for e in events] == ["tool_started", "tool_completed"]


def test_same_id_with_different_operation_is_a_fresh_call(tmp_path):
    # Contract: existing suites reuse one call-id across turns for distinct
    # operations, so only an identical repeated operation counts as a replay.
    events: list[ToolExecutionEvent] = []
    client = ScriptedClient(
        [
            [AIToolCall("shared", "create_file", {"path": "a.txt", "content": "a"})],
            [AIToolCall("shared", "create_file", {"path": "b.txt", "content": "b"})],
            "Done",
        ]
    )
    result = AgentLoop(
        client,
        default_coding_tools(),
        ToolContext(tmp_path),
        permissions=permissive(),
        on_event=events.append,
    ).run("Create two files")

    assert [item.is_error for item in result.tool_results] == [False, False]
    assert (tmp_path / "a.txt").read_text() == "a"
    assert (tmp_path / "b.txt").read_text() == "b"
    assert [e.type for e in events] == [
        "tool_started",
        "tool_completed",
        "tool_started",
        "tool_completed",
    ]


# --- loop.py: recovery-as-result, protocol violations raise ---


def test_tool_error_returns_result_so_model_adapts(tmp_path):
    calls: list[str] = []

    class Boom(BaseTool):
        @property
        def definition(self):
            return ToolDefinition("boom", "Always fails", ToolCategory.READ)

        def execute(self, arguments, context):
            calls.append("ran")
            raise RuntimeError("boom-sentinel")

    registry = ToolRegistry((Boom(), CreateFileTool()))
    client = ScriptedClient(
        [
            [AIToolCall("b1", "boom", {})],
            [AIToolCall("fix", "create_file", {"path": "out.txt", "content": "adapted"})],
            "Done",
        ]
    )
    result = AgentLoop(client, registry, ToolContext(tmp_path), permissions=permissive()).run(
        "Try boom, then adapt"
    )

    assert [item.is_error for item in result.tool_results] == [True, False]
    assert "boom-sentinel" in result.tool_results[0].output
    assert calls == ["ran"]
    assert client.requests[1].messages[-1].role is MessageRole.TOOL
    assert (tmp_path / "out.txt").read_text() == "adapted"


def test_exception_escaping_tool_run_becomes_error_result(tmp_path):
    class RunBoom(BaseTool):
        @property
        def definition(self):
            return ToolDefinition("runboom", "run() raises", ToolCategory.READ)

        def execute(self, arguments, context):
            raise AssertionError("must not reach execute")

        def run(self, call, context):
            raise ValueError("run-override-boom")

    client = ScriptedClient([[AIToolCall("r1", "runboom", {})], "Done"])
    result = AgentLoop(
        client, ToolRegistry((RunBoom(),)), ToolContext(tmp_path), permissions=permissive()
    ).run("Exercise run override")

    assert result.tool_results[0].is_error is True
    assert "run-override-boom" in result.tool_results[0].output
    assert result.response.message.content == "Done"


def test_provider_error_from_tool_raises_and_keeps_pending(tmp_path):
    events: list[ToolExecutionEvent] = []

    class ProtocolBoom(BaseTool):
        @property
        def definition(self):
            return ToolDefinition("protocolboom", "Protocol failure", ToolCategory.READ)

        def execute(self, arguments, context):  # pragma: no cover - run() raises first
            raise AssertionError("must not reach execute")

        def run(self, call, context: Ctx):
            raise ProviderError("protocol boom", category=ProviderErrorCategory.NON_RETRYABLE)

    client = ScriptedClient([[AIToolCall("p1", "protocolboom", {})]])
    loop = AgentLoop(
        client,
        ToolRegistry((ProtocolBoom(),)),
        ToolContext(tmp_path),
        permissions=permissive(),
        on_event=events.append,
    )
    with pytest.raises(ProviderError, match="protocol boom") as raised:
        loop.run("Exercise protocol failure")
    assert raised.value.partial_messages
    assert [(c.name, c.call_id) for c in loop.pending] == [("protocolboom", "p1")]
    assert [e.type for e in events] == ["tool_started"]


# --- shared_approvals.py: expiry window + evidence re-verify + revalidate ---


def test_approval_without_window_keeps_legacy_outcomes(tmp_path):
    yes = TerminalApproval("task", "run", tmp_path, approval_reader=lambda p, a: "yes")
    assert yes(write_call(), ToolCategory.WRITE) is True
    assert yes.last_outcome == "approved"
    no = TerminalApproval("task", "run", tmp_path, approval_reader=lambda p, a: "no")
    assert no(write_call(), ToolCategory.WRITE) is False
    assert no.last_outcome == "denied"


def test_late_yes_is_refused_as_expired(tmp_path, monkeypatch):
    approval = TerminalApproval(
        "task", "run", tmp_path, approval_reader=lambda p, a: "yes", timeout_seconds=5.0
    )
    times = iter([0.0, 10.0])
    monkeypatch.setattr("ai_agent.shared_approvals.time.monotonic", lambda: next(times))
    assert approval(write_call(), ToolCategory.WRITE) is False
    assert approval.last_outcome == "expired"


def test_timely_yes_is_approved_within_window(tmp_path, monkeypatch):
    approval = TerminalApproval(
        "task", "run", tmp_path, approval_reader=lambda p, a: "yes", timeout_seconds=5.0
    )
    times = iter([0.0, 2.0])
    monkeypatch.setattr("ai_agent.shared_approvals.time.monotonic", lambda: next(times))
    assert approval(write_call(), ToolCategory.WRITE) is True
    assert approval.last_outcome == "approved"


def test_evidence_change_between_prompt_and_approve_fails_closed(tmp_path):
    state = {"digest": "base"}

    def approve(prompt, active):
        state["digest"] = "changed"
        return "yes"

    approval = TerminalApproval(
        "task",
        "run",
        tmp_path,
        approval_reader=approve,
        evidence_reader=lambda call: state["digest"],
    )
    assert approval(write_call(), ToolCategory.WRITE) is False
    assert approval.last_outcome == "evidence_changed"


def test_stable_evidence_approves(tmp_path):
    approval = TerminalApproval(
        "task",
        "run",
        tmp_path,
        approval_reader=lambda p, a: "yes",
        evidence_reader=lambda call: "steady",
    )
    assert approval(write_call(), ToolCategory.WRITE) is True
    assert approval.last_outcome == "approved"


def test_evidence_reader_error_fails_closed(tmp_path):
    def broken(call):
        raise OSError("evidence unavailable")

    approval = TerminalApproval(
        "task", "run", tmp_path, approval_reader=lambda p, a: "yes", evidence_reader=broken
    )
    assert approval(write_call(), ToolCategory.WRITE) is False
    assert approval.last_outcome == "evidence_changed"


def test_revalidate_after_expiry_grants_fresh_window(tmp_path, monkeypatch):
    approval = TerminalApproval(
        "task", "run", tmp_path, approval_reader=lambda p, a: "yes", timeout_seconds=5.0
    )
    times = iter([0.0, 10.0])
    monkeypatch.setattr("ai_agent.shared_approvals.time.monotonic", lambda: next(times))
    assert approval(write_call(), ToolCategory.WRITE) is False
    assert approval.last_outcome == "expired"
    fresh = iter([100.0, 101.0])
    monkeypatch.setattr("ai_agent.shared_approvals.time.monotonic", lambda: next(fresh))
    assert approval.revalidate(write_call(), ToolCategory.WRITE) is True
    assert approval.last_outcome == "approved"


def test_revalidate_resnapshots_evidence(tmp_path):
    state = {"digest": "v1"}
    mutate = {"on": True}

    def approve(prompt, active):
        if mutate["on"]:
            state["digest"] = "tampered"
        return "yes"

    approval = TerminalApproval(
        "task",
        "run",
        tmp_path,
        approval_reader=approve,
        evidence_reader=lambda call: state["digest"],
    )
    assert approval(write_call(), ToolCategory.WRITE) is False
    assert approval.last_outcome == "evidence_changed"
    mutate["on"] = False
    state["digest"] = "v2"
    assert approval.revalidate(write_call(), ToolCategory.WRITE) is True
    assert approval.last_outcome == "approved"


@pytest.mark.parametrize("timeout", [0.0, -1.0, float("inf"), float("nan"), True])
def test_invalid_approval_timeout_is_refused(tmp_path, timeout):
    with pytest.raises(ValueError, match="finite positive seconds"):
        TerminalApproval("task", "run", tmp_path, timeout_seconds=timeout)


# --- recovery.py: park/resume + reconcile ---


def test_park_and_answer_roundtrip():
    state = RecoveryState()
    assert state.status == "ready"
    assert state.is_waiting is False
    assert state.park_question("  Use SQLite? ") == "Use SQLite?"
    assert state.status == "waiting_on_owner"
    assert state.is_waiting is True
    assert state.parked_question == "Use SQLite?"
    recorded = state.answer("Yes, SQLite.")
    assert isinstance(recorded, OwnerAnswer) and recorded.text == "Yes, SQLite."
    assert state.answers == (recorded,)
    assert state.status == "paused"
    assert state.is_waiting is False
    assert state.parked_question is None


@pytest.mark.parametrize("bad", ["", "   ", "x" * (MAX_QUESTION_CHARS + 1), None, 123])
def test_park_question_validates_bounds(bad):
    with pytest.raises(ValueError):
        RecoveryState().park_question(bad)


def test_double_park_is_refused():
    state = RecoveryState()
    state.park_question("First?")
    with pytest.raises(ValueError, match="already parked"):
        state.park_question("Second?")
    assert state.parked_question == "First?"


def test_park_refuses_while_operation_uncertain():
    state = RecoveryState()
    state.track_pending(
        PendingOperation("create_file", {"path": "a"}, ToolCategory.WRITE, call_id="w1")
    )
    with pytest.raises(ValueError, match="reconciliation first"):
        state.park_question("Proceed?")


@pytest.mark.parametrize("bad", ["", "   ", "x" * (MAX_ANSWER_CHARS + 1), None])
def test_answer_validates_bounds(bad):
    state = RecoveryState()
    state.park_question("Proceed?")
    with pytest.raises(ValueError):
        state.answer(bad)
    assert state.is_waiting is True


def test_answer_without_parked_question_raises():
    with pytest.raises(ValueError, match="No parked owner question"):
        RecoveryState().answer("Yes")


def test_reconcile_adopts_matching_write():
    state = RecoveryState()
    state.track_pending(
        PendingOperation("create_file", {"path": "a.txt"}, ToolCategory.WRITE, call_id="w1")
    )
    expected = digest_text("new-bytes")
    adopted = state.reconcile(expected_digest=expected, actual_digest=digest_text("new-bytes"))
    assert adopted.is_error is False
    assert adopted.call_id == "w1"
    assert adopted.metadata == {"digest": expected, "reconciled": True}
    assert state.pending is None
    assert state.status == "paused"


@pytest.mark.parametrize("actual", [digest_text("other-bytes"), None])
def test_reconcile_refuses_mismatched_write(actual):
    state = RecoveryState()
    state.track_pending(PendingOperation("create_file", {"path": "a.txt"}, ToolCategory.WRITE))
    with pytest.raises(ValueError, match="manual inspection"):
        state.reconcile(expected_digest=digest_text("new-bytes"), actual_digest=actual)
    assert state.pending is not None


@pytest.mark.parametrize(
    "category", [ToolCategory.READ, ToolCategory.SHELL, ToolCategory.SEARCH, ToolCategory.CUSTOM]
)
def test_reconcile_refuses_non_write_replay(category):
    state = RecoveryState()
    state.track_pending(PendingOperation("read_file", {"path": "a.txt"}, category))
    with pytest.raises(ValueError, match="non-write"):
        state.reconcile(expected_digest="whatever", actual_digest="whatever")
    assert state.pending is not None


def test_reconcile_without_pending_raises():
    with pytest.raises(ValueError, match="No uncertain operation"):
        RecoveryState().reconcile(expected_digest="a", actual_digest="a")


def test_track_pending_refuses_when_occupied():
    state = RecoveryState()
    first = PendingOperation("create_file", {}, ToolCategory.WRITE)
    state.track_pending(first)
    with pytest.raises(ValueError, match="reconciliation first"):
        state.track_pending(first)
    assert state.pending is first
