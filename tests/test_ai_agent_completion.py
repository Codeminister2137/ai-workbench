"""Completion feedback preserves real effects, limits, permissions and authorship."""

from __future__ import annotations

import subprocess

import pytest
from ai_agent import (
    AgentLoop,
    CompletionRequirement,
    PermissionManager,
    PermissionPolicy,
    ToolContext,
    default_coding_tools,
)
from ai_provider import (
    AIMessage,
    AIResponse,
    AIToolCall,
    BackendInfo,
    BackendLocation,
    FinishReason,
    MessageRole,
    ProviderContinuation,
    ProviderError,
    ProviderErrorCategory,
)


class ScriptedClient:
    backend = BackendInfo(provider="scripted", model="test", location=BackendLocation.LOCAL)

    def __init__(self, *responses):
        self.responses = iter(responses)
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        return next(self.responses)


def answer(text="Candidate", *, calls=(), continuation=None, reason=FinishReason.STOP):
    return AIResponse(
        AIMessage(MessageRole.ASSISTANT, text, tool_calls=calls, continuation=continuation),
        ScriptedClient.backend,
        finish_reason=reason,
    )


def tool(name, **arguments):
    return answer("", calls=(AIToolCall("call", name, arguments),))


def successful(name):
    return CompletionRequirement(
        name,
        lambda results: any(result.name == name and not result.is_error for result in results),
    )


def loop(tmp_path, client, **kwargs):
    return AgentLoop(
        client,
        default_coding_tools(),
        ToolContext(tmp_path),
        permissions=kwargs.pop(
            "permissions", PermissionManager(policy=PermissionPolicy.permissive())
        ),
        **kwargs,
    )


def test_missing_diff_corrected_in_same_history_with_actual_git_effects(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "source.txt").write_text("original\n")
    subprocess.run(["git", "add", "source.txt"], cwd=tmp_path, check=True)
    (tmp_path / "source.txt").write_text("changed\n")
    continuation = ProviderContinuation("scripted", "test", "local", {"opaque": "PRIVATE"})
    client = ScriptedClient(
        answer("Premature claim", continuation=continuation),
        tool("git_diff"),
        answer("Reviewed actual diff; no writes performed in this review."),
    )
    events = []
    requirement = CompletionRequirement(
        "git_diff",
        lambda results: any(
            result.name == "git_diff"
            and not result.is_error
            and type(result.metadata.get("exit_code")) is int
            and result.metadata["exit_code"] == 0
            for result in results
        ),
    )
    result = loop(
        tmp_path,
        client,
        completion_requirements=(requirement,),
        max_iterations=3,
        diagnostic=events.append,
    ).run("Review the changes", system_prompt="No writes; preserve all instructions.")
    assert result.iterations == 3 and result.completion_failures == 1
    assert result.model_output_errors == 0
    assert (tmp_path / "source.txt").read_text() == "changed\n"
    assert "+changed" in result.tool_results[0].output
    assert client.requests[1].messages[:3] == (
        client.requests[0].messages[0],
        client.requests[0].messages[1],
        AIMessage(MessageRole.ASSISTANT, "Premature claim", continuation=continuation),
    )
    assert client.requests[1].messages[-1].role is MessageRole.USER
    assert "Host completion feedback" in client.requests[1].messages[-1].content
    assert client.requests[1].messages[2].continuation is continuation
    assert all(len(request.tools) == 13 for request in client.requests)
    assert "completion_recovery: errors=1 action=feedback" in events
    assert all("PRIVATE" not in event for event in events)


def test_no_requirements_preserves_existing_completion(tmp_path):
    candidate = answer("No tools needed")
    client = ScriptedClient(candidate)
    result = loop(tmp_path, client).run("Answer a question")
    assert result.response is candidate and result.completion_failures == 0
    assert len(client.requests) == 1


def test_unknown_finish_metadata_cannot_bypass_required_evidence(tmp_path):
    client = ScriptedClient(answer(reason=FinishReason.UNKNOWN))
    with pytest.raises(ProviderError, match="allowance ended"):
        loop(
            tmp_path, client, max_iterations=1, completion_requirements=(successful("git_diff"),)
        ).run("Task")


def test_same_missing_check_stops_without_third_request(tmp_path):
    client = ScriptedClient(answer("First"), answer("Reworded, still missing evidence"))
    with pytest.raises(ProviderError, match="same blocker") as captured:
        loop(tmp_path, client, completion_requirements=(successful("git_diff"),)).run("Review")
    assert len(client.requests) == 2
    assert captured.value.partial_messages[-1].content == "Reworded, still missing evidence"
    assert captured.value.category is ProviderErrorCategory.NON_RETRYABLE


def test_last_candidate_cannot_start_a_new_allowance(tmp_path):
    client = ScriptedClient(answer("Incomplete"))
    with pytest.raises(ProviderError, match="allowance ended") as captured:
        loop(
            tmp_path, client, max_iterations=1, completion_requirements=(successful("git_diff"),)
        ).run("Review")
    assert len(client.requests) == 1
    assert captured.value.partial_messages[-1].role is MessageRole.ASSISTANT


def test_new_successful_read_observation_counts_as_progress_without_writes(tmp_path):
    (tmp_path / "first.txt").write_text("one")
    client = ScriptedClient(
        answer(), tool("read_file", path="first.txt"), answer(), tool("git_status"), answer()
    )
    # Read progress changes the missing requirements, even with an unchanged file state.
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    result = loop(
        tmp_path,
        client,
        max_iterations=5,
        completion_requirements=(successful("read_file"), successful("git_status")),
    ).run("Read and inspect status")
    assert result.completion_failures == 2 and result.iterations == 5


@pytest.mark.parametrize("values", [("A", "B", "A"), ("A", "A")])
def test_cycles_and_noop_writes_do_not_reset_completion_blocker(tmp_path, values):
    responses = []
    for value in values:
        responses += [tool("edit_file", path="state.txt", new_text=value), answer()]
    (tmp_path / "state.txt").write_text("initial")
    client = ScriptedClient(*responses)
    with pytest.raises(ProviderError, match="same blocker"):
        loop(
            tmp_path, client, max_iterations=10, completion_requirements=(successful("git_diff"),)
        ).run("Inspect then finish")
    assert len(client.requests) == len(values) * 2
    assert (tmp_path / "state.txt").read_text() == values[-1]


@pytest.mark.parametrize("value", [None, 1, "yes", RuntimeError("PRIVATE checker exception")])
def test_unknown_or_failed_predicate_stops_without_echo_or_retry(tmp_path, value):
    def predicate(results):
        if isinstance(value, Exception):
            raise value
        return value

    client = ScriptedClient(answer("Candidate retained"))
    with pytest.raises(ProviderError, match="checker failed") as captured:
        loop(
            tmp_path, client, completion_requirements=(CompletionRequirement("check", predicate),)
        ).run("Task")
    assert "PRIVATE" not in str(captured.value)
    assert captured.value.__cause__ is None
    assert captured.value.partial_messages[-1].content == "Candidate retained"
    assert len(client.requests) == 1


def test_checker_cannot_extend_elapsed_deadline(tmp_path, monkeypatch):
    now = 0.0

    def predicate(results):
        nonlocal now
        now = 11.0
        return False

    monkeypatch.setattr("ai_agent.loop.time.perf_counter", lambda: now)
    client = ScriptedClient(answer())
    with pytest.raises(ProviderError) as captured:
        loop(
            tmp_path,
            client,
            deadline=10.0,
            completion_requirements=(CompletionRequirement("check", predicate),),
        ).run("Task")
    assert captured.value.category is ProviderErrorCategory.TIMEOUT
    assert len(client.requests) == 1


@pytest.mark.parametrize("path", ["denied.txt", "../outside-completion.txt"])
def test_feedback_does_not_override_tool_permissions_or_workspace(tmp_path, path):
    client = ScriptedClient(answer(), tool("create_file", path=path, content="forbidden"), answer())
    permissions = (
        PermissionManager()
        if path == "denied.txt"
        else PermissionManager(policy=PermissionPolicy.permissive())
    )
    with pytest.raises(ProviderError) as captured:
        loop(
            tmp_path,
            client,
            permissions=permissions,
            completion_requirements=(successful("create_file"),),
        ).run("Read-only task")
    assert not (tmp_path / path).exists()
    assert any(
        message.role is MessageRole.TOOL and "Error" in message.content
        for message in captured.value.partial_messages
    )


@pytest.mark.parametrize("text,reason", [("", FinishReason.STOP), ("Partial", FinishReason.LENGTH)])
def test_invalid_native_reports_are_not_reclassified_as_completion_corrections(
    tmp_path, text, reason
):
    client = ScriptedClient(answer(text, reason=reason))
    result = loop(tmp_path, client, completion_requirements=(successful("git_diff"),)).run("Task")
    assert result.completion_failures == 0 and len(client.requests) == 1


@pytest.mark.parametrize("identifier", ["", "UPPER", "raw\nPRIVATE", "a" * 81])
def test_requirement_labels_are_bounded(identifier):
    with pytest.raises(ValueError):
        CompletionRequirement(identifier, lambda results: True)


def test_duplicate_and_excess_requirements_refused_before_inference(tmp_path):
    client = ScriptedClient()
    item = successful("git_diff")
    for requirements in ((item, item), (item,) * 17):
        with pytest.raises(ValueError):
            loop(tmp_path, client, completion_requirements=requirements)
    assert not client.requests
