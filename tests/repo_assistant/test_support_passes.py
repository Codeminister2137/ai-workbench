"""Reusable support passes preserve local constraints and honest failure status."""

from dataclasses import replace
from pathlib import Path

import pytest
from ai_agent import support_passes
from ai_agent.external_reporting import activity_preview
from ai_orchestrator import CostPolicyTier, PrivacyClass, TaskType, load_model_catalog
from ai_provider import AIMessage, AIResponse, BackendInfo, BackendLocation, MessageRole
from ai_provider.coding_assist import CodingAssistResult, coding_task_profile
from ai_provider.repo_context import RepoContextFile


@pytest.mark.parametrize("limit", [0, 1, 5, 14, 15, 20, 160])
def test_activity_preview_never_exceeds_limit(limit: int):
    text = activity_preview("word \n" * 100, limit=limit)
    assert len(text) <= limit
    assert "\n" not in text


def test_auxiliary_review_does_not_inherit_primary_cloud_overrides(monkeypatch):
    parent = coding_task_profile(
        privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        provider_override="openai",
        model_override="gpt-5.5",
    )
    captured = {}

    def run(prompt, profile, catalog, **kwargs):
        captured["profile"] = profile
        captured.update(kwargs)
        from ai_orchestrator import OrchestrationResult, OrchestrationStatus

        return CodingAssistResult(
            OrchestrationResult(
                prompt,
                profile,
                OrchestrationStatus.MODEL_SELECTION_FAILED,
                None,
                None,
                None,
                failure_reason="no eligible local route",
            )
        )

    monkeypatch.setattr(support_passes, "run_coding_prompt", run)
    result = support_passes.run_auxiliary_panel("review the task", parent, ())
    profile = captured["profile"]
    assert profile.privacy_class is PrivacyClass.LOCAL_ONLY
    assert profile.cost_policy_tier is CostPolicyTier.LOCAL_ONLY
    assert profile.user_backend_override is None
    assert profile.user_model_override is None
    assert captured["review_prompt"] is False
    assert result.status == "failed"
    assert result.failure_reason == "no eligible local route"


def test_auxiliary_without_local_route_never_uses_cloud_parent():
    profile = coding_task_profile(
        privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        provider_override="openai",
        model_override="gpt-5.5",
    )
    catalog = load_model_catalog(Path("packages/ai_orchestrator/examples/model_catalog.toml"))
    cloud_catalog = tuple(item for item in catalog if item.backend.provider != "ollama")

    def forbidden(config):
        pytest.fail("support pass fell through to a cloud route")

    result = support_passes.run_auxiliary_panel(
        "task", profile, cloud_catalog, client_factory=forbidden
    )
    assert result.status == "failed"
    assert result.response_text is None


def test_context_execution_uses_planned_target_configuration(monkeypatch):
    catalog = load_model_catalog(Path("packages/ai_orchestrator/examples/model_catalog.toml"))
    parent = coding_task_profile(provider_override="ollama", model_override="qwen2.5-coder:14b")
    plan = support_passes.plan_delegated_subtask(
        parent_profile=parent,
        catalog=catalog,
        task_type=TaskType.SUMMARIZATION,
        cost_policy_tier=CostPolicyTier.LOCAL_ONLY,
    )
    target = replace(
        plan.execution_plan.target, base_url="http://fixture.invalid:11434", timeout_seconds=7.25
    )
    plan = replace(plan, execution_plan=replace(plan.execution_plan, target=target))
    monkeypatch.setattr(support_passes, "plan_delegated_subtask", lambda **kw: plan)
    captured = {}

    class Client:
        backend = BackendInfo("ollama", target.model, BackendLocation.LOCAL)

        def complete(self, request):
            captured["request"] = request
            return AIResponse(
                AIMessage(MessageRole.ASSISTANT, "Fact [source:a.py:1]"), self.backend
            )

        def stream(self, request):
            raise NotImplementedError

    def factory(config):
        captured["config"] = config
        return Client()

    summary, status = support_passes.run_local_context_delegation(
        (RepoContextFile(Path("a.py"), "a.py", "value = 1", True),),
        parent,
        catalog,
        client_factory=factory,
    )
    config = captured["config"]
    assert config.base_url == target.base_url
    assert config.timeout_seconds == 7.25
    assert config.model == target.model
    assert captured["request"].privacy_class.value == plan.profile.privacy_class.value
    assert status == f"accepted: {target.route_id}"
    assert summary == "Fact [source:a.py:1]"


@pytest.mark.parametrize("kind", ["context", "auxiliary"])
def test_expired_support_pass_never_starts_model_request(monkeypatch, kind):
    monkeypatch.setattr(support_passes.time, "perf_counter", lambda: 11.0)

    def forbidden(config):
        pytest.fail("Expired support pass created a client")

    parent = coding_task_profile()
    if kind == "context":
        summary, status = support_passes.run_local_context_delegation(
            (), parent, (), deadline=10.0, client_factory=forbidden
        )
        assert summary is None and "expired" in status
    else:
        result = support_passes.run_auxiliary_panel(
            "task", parent, (), deadline=10.0, client_factory=forbidden
        )
        assert result.failure_reason is not None
        assert result.status == "failed" and "expired" in result.failure_reason


@pytest.mark.parametrize("kind", ["context", "auxiliary"])
def test_support_pass_caps_timeout_and_rejects_late_completion(monkeypatch, kind):
    now = 0.0
    configs = []
    monkeypatch.setattr(support_passes.time, "perf_counter", lambda: now)
    catalog = load_model_catalog(Path("packages/ai_orchestrator/examples/model_catalog.toml"))
    parent = coding_task_profile()

    class Client:
        backend = BackendInfo("ollama", "unused", BackendLocation.LOCAL)

        def stream(self, request):
            raise NotImplementedError

        def complete(self, request):
            nonlocal now
            now = 11.0
            return AIResponse(
                AIMessage(MessageRole.ASSISTANT, "Fact [source:a.py:1]"), self.backend
            )

    def factory(config):
        configs.append(config)
        return Client()

    if kind == "context":
        summary, status = support_passes.run_local_context_delegation(
            (RepoContextFile(Path("a.py"), "a.py", "value = 1", True),),
            parent,
            catalog,
            deadline=10.0,
            client_factory=factory,
        )
        assert summary is None and "expired" in status
    else:
        result = support_passes.run_auxiliary_panel(
            "task", parent, catalog, deadline=10.0, client_factory=factory
        )
        assert result.failure_reason is not None
        assert result.status == "failed" and "expired" in result.failure_reason.lower()
    assert configs and all(0 < config.timeout_seconds <= 10 for config in configs)
