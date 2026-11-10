"""Agent harness acceptance gate (reconstruction S7).

Composed end-to-end scenarios over the real loop, real tools, and a real
workspace. This file is the ship-blocker for routing, grade, budget, and
governance changes: every scenario must stay green, and each one pins a
regression the reconstruction fixed (shallow budgets, overflow refusal,
fabricated verification, unusable delegation, coarse governance, static
grades). Model quality itself is measured by live pilots, not here.
"""

from __future__ import annotations

import time

import pytest
from ai_agent import AgentLoop, PermissionManager, PermissionPolicy, ToolContext
from ai_agent.contracts import PermissionAction, ToolResult
from ai_agent.groundedness import check_groundedness
from ai_agent.tools.base import ToolRegistry
from ai_agent.tools.delegation import DelegateTaskTool
from ai_agent.tools.filesystem import CreateFileTool, EditFileTool, ReadFileTool
from ai_agent.tools.shell import RunCommandTool
from ai_orchestrator import (
    AccessMethod,
    AccessRoute,
    AuthMethod,
    BackendLocation,
    BillingSource,
    CostPolicyTier,
    LatencyTarget,
    ModelBackend,
    ModelCapabilities,
    ModelCatalogEntry,
    ModelPerformanceEstimate,
    QualityThreshold,
    TaskProfile,
    recommend_model,
)
from ai_orchestrator import (
    PrivacyClass as OrchestratorPrivacy,
)
from ai_orchestrator.route_outcomes import (
    RouteOutcome,
    append_outcome,
    load_quality_adjustments,
)
from ai_provider import (
    AIMessage,
    AIResponse,
    AIToolCall,
    BackendInfo,
    FinishReason,
    MessageRole,
    PrivacyClass,
    ProviderError,
    UsageMetadata,
)
from ai_provider import (
    BackendLocation as ProviderLocation,
)


class ScriptedClient:
    """Replies with scripted (tool calls, final text) turns."""

    backend = BackendInfo(provider="fake", model="test", location=ProviderLocation.LOCAL)

    def __init__(self, replies: list[tuple[list, str]]) -> None:
        self.replies = list(replies)
        self.requests = []

    def complete(self, request):
        from ai_provider import AIRequest

        assert isinstance(request, AIRequest)
        self.requests.append(request)
        calls, text = self.replies.pop(0) if self.replies else ([], "Done")
        if request.metadata.get("task_type") == "loop_compaction":
            return AIResponse(
                message=AIMessage(MessageRole.ASSISTANT, "Compacted earlier file work."),
                backend=self.backend,
                finish_reason=FinishReason.STOP,
                usage=UsageMetadata(),
            )
        return AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, text, tool_calls=tuple(calls)),
            backend=self.backend,
            finish_reason=FinishReason.STOP,
            usage=UsageMetadata(),
        )

    def stream(self, request):
        raise NotImplementedError


def _call(call_id: str, name: str, **arguments) -> AIToolCall:
    return AIToolCall(call_id, name, arguments)


def _coding_registry() -> ToolRegistry:
    return ToolRegistry((CreateFileTool(), ReadFileTool(), EditFileTool(), RunCommandTool()))


def test_deep_implement_task_completes_with_compaction_and_evidence(tmp_path) -> None:
    """Nine tool rounds finish: budgets hold, compaction fires, claims grounded."""
    client = ScriptedClient(
        [
            ([_call("c1", "create_file", path="a.txt", content="alpha")], ""),
            ([_call("c2", "read_file", path="a.txt")], ""),
            ([_call("c3", "create_file", path="b.txt", content="beta")], ""),
            ([_call("c4", "read_file", path="b.txt")], ""),
            ([_call("c5", "edit_file", path="a.txt", old_text="alpha", new_text="ALPHA")], ""),
            ([_call("c6", "read_file", path="a.txt")], ""),
            ([_call("c7", "read_file", path="b.txt")], ""),
            ([_call("c8", "read_file", path="a.txt")], ""),
            (
                [],
                "Created a.txt and b.txt, updated a.txt to ALPHA, and read both back to confirm.",
            ),
        ]
    )
    loop = AgentLoop(
        client,
        _coding_registry(),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.permissive()),
        max_iterations=25,
        loop_context_budget_chars=3150,
        compaction_tail_messages=2,
        require_grounded_reports=True,
    )
    result = loop.run("Build the files", privacy_class=PrivacyClass.LOCAL_ONLY)
    assert (tmp_path / "a.txt").read_text() == "ALPHA"
    assert (tmp_path / "b.txt").read_text() == "beta"
    assert result.compactions >= 1
    assert result.iterations <= 12  # burn bound for this fixed task
    verdict = check_groundedness(result.response.message.content, result.tool_results)
    assert verdict.ok
    systems = [
        message.content
        for message in client.requests[-1].messages
        if message.role is MessageRole.SYSTEM
    ]
    assert any("Compacted summary" in text for text in systems)


def test_deep_task_requires_reconstruction_depth(tmp_path) -> None:
    """The same task dies under the old 3-round budget: the gate can go red."""
    client = ScriptedClient(
        [([_call(f"c{i}", "read_file", path="a.txt")], "") for i in range(6)] + [([], "Finished")]
    )
    (tmp_path / "a.txt").write_text("alpha")
    with pytest.raises(ProviderError, match="max_iterations=3"):
        AgentLoop(
            client,
            _coding_registry(),
            ToolContext(tmp_path),
            permissions=PermissionManager(policy=PermissionPolicy.permissive()),
            max_iterations=3,
        ).run("Build the files", privacy_class=PrivacyClass.LOCAL_ONLY)


def test_exhaustion_resumes_to_completion_with_cumulative_count(tmp_path) -> None:
    client = ScriptedClient([([_call("c1", "create_file", path="o.txt", content="ok")], "")])
    loop_kwargs: dict = {
        "permissions": PermissionManager(policy=PermissionPolicy.permissive()),
        "max_iterations": 1,
    }
    loop = AgentLoop(client, _coding_registry(), ToolContext(tmp_path), **loop_kwargs)
    with pytest.raises(ProviderError) as captured:
        loop.run("Create it", privacy_class=PrivacyClass.LOCAL_ONLY)
    assert (tmp_path / "o.txt").read_text() == "ok"
    resume_client = ScriptedClient([([], "Created o.txt.")])
    resumed = AgentLoop(
        resume_client,
        _coding_registry(),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.permissive()),
        max_iterations=2,
        require_grounded_reports=True,
    ).resume(
        captured.value.partial_messages,
        privacy_class=PrivacyClass.LOCAL_ONLY,
        prior_iterations=1,
        prior_tool_results=captured.value.tool_results,
    )
    assert resumed.iterations == 2
    assert resumed.response.message.content == "Created o.txt."
    assert len(resumed.tool_results) == 1
    assert check_groundedness(resumed.response.message.content, resumed.tool_results).ok


def test_fabricated_claims_are_refused_until_downgraded(tmp_path) -> None:
    client = ScriptedClient(
        [
            ([], "I verified the code and all tests passed."),
            ([], "Unverified summary: no checks were run in this turn."),
        ]
    )
    result = AgentLoop(
        client,
        _coding_registry(),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.permissive()),
        max_iterations=4,
        require_grounded_reports=True,
    ).run("Check it", privacy_class=PrivacyClass.LOCAL_ONLY)
    assert "Unverified summary" in result.response.message.content
    assert "groundedness" in client.requests[1].messages[-1].content


def test_delegated_subtasks_return_bounded_summaries_only(tmp_path) -> None:
    def runner(task: str, context: ToolContext) -> ToolResult:
        (context.workspace_root / "child.txt").write_text("SECRET_CHILD_CONTENT", encoding="utf-8")
        return ToolResult("delegate_task", f"summary of {task}")

    client = ScriptedClient(
        [
            (
                [
                    _call("d1", "delegate_task", task="first part"),
                    _call("d2", "delegate_task", task="second part"),
                ],
                "",
            ),
            ([], "Both parts summarized."),
        ]
    )
    result = AgentLoop(
        client,
        ToolRegistry((DelegateTaskTool(runner),)),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.permissive()),
        max_iterations=3,
    ).run("Delegate both", privacy_class=PrivacyClass.LOCAL_ONLY)
    assert len(result.tool_results) == 2
    assert (tmp_path / "child.txt").read_text() == "SECRET_CHILD_CONTENT"
    parent_transcript = " ".join(
        message.content for request in client.requests for message in request.messages
    )
    assert "SECRET_CHILD_CONTENT" not in parent_transcript
    assert "summary of first part" in parent_transcript


def test_denied_tool_hidden_and_refused(tmp_path) -> None:
    client = ScriptedClient([([_call("c1", "run_command", command="echo hi")], ""), ([], "Done")])
    policy = PermissionPolicy(tool_rules=(("run_command", PermissionAction.DENY),))
    result = AgentLoop(
        client,
        _coding_registry(),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=policy),
        max_iterations=3,
    ).run("Run it", privacy_class=PrivacyClass.LOCAL_ONLY)
    names = {tool.name for tool in client.requests[0].tools}
    assert "run_command" not in names
    assert result.tool_results[0].is_error
    assert "not authorized" in result.tool_results[0].output


def _catalog_entry(
    route_id: str, tier: CostPolicyTier, quality: QualityThreshold
) -> ModelCatalogEntry:
    location = (
        BackendLocation.LOCAL if tier is CostPolicyTier.LOCAL_ONLY else BackendLocation.EXTERNAL
    )
    return ModelCatalogEntry(
        backend=ModelBackend(
            route=AccessRoute(
                route_id=route_id,
                provider=route_id.split("/")[0],
                product="p",
                model="m",
                location=location,
                access_method=AccessMethod.LOCAL_RUNTIME
                if location is BackendLocation.LOCAL
                else AccessMethod.PROVIDER_API,
                auth_method=AuthMethod.NONE,
                billing_source=BillingSource.LOCAL_FREE,
                cost_policy_tier=tier,
            ),
            capabilities=ModelCapabilities(),
            estimate=ModelPerformanceEstimate(),
        ),
        quality=quality,
        latency=LatencyTarget.INTERACTIVE,
    )


def test_outcome_demotions_change_routing(tmp_path) -> None:
    strong = _catalog_entry("ext/strong", CostPolicyTier.BILLING_ALLOWED, QualityThreshold.HIGH)
    steady = _catalog_entry("local/steady", CostPolicyTier.LOCAL_ONLY, QualityThreshold.STANDARD)
    profile = TaskProfile(
        privacy_class=OrchestratorPrivacy.EXTERNAL_ALLOWED,
        cost_policy_tier=CostPolicyTier.BILLING_ALLOWED,
    )
    catalog = (strong, steady)
    assert recommend_model(profile, catalog).selected is strong
    path = tmp_path / "route-outcomes.jsonl"
    now = time.time()
    for _ in range(3):
        append_outcome(
            path,
            RouteOutcome(
                route_id="ext/strong",
                mode="implement",
                success=False,
                tool_calls=1,
                iterations=2,
                finished_at=now,
            ),
        )
    adjustments = load_quality_adjustments(path)
    assert adjustments == {"ext/strong": -1}
    assert recommend_model(profile, catalog, quality_adjustments=adjustments).selected is steady


def test_simple_tasks_route_cheap_first(tmp_path) -> None:
    del tmp_path
    pricey = _catalog_entry("ext/pricey", CostPolicyTier.BILLING_ALLOWED, QualityThreshold.STANDARD)
    thrifty = _catalog_entry(
        "ext/thrifty", CostPolicyTier.ALLOWANCES_ALLOWED, QualityThreshold.STANDARD
    )
    profile = TaskProfile(
        privacy_class=OrchestratorPrivacy.EXTERNAL_ALLOWED,
        cost_policy_tier=CostPolicyTier.BILLING_ALLOWED,
        complexity="simple",
    )
    assert recommend_model(profile, (pricey, thrifty)).selected is thrifty
