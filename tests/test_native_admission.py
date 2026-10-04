"""Offline compatibility invalidation and complete-input refusal contracts."""

from argparse import Namespace
from dataclasses import replace
from types import SimpleNamespace

import pytest
from ai_orchestrator import load_model_catalog, recommend_model
from ai_provider import (
    AIMessage,
    AIRequest,
    AIResponse,
    AIToolCall,
    AIToolDefinition,
    BackendConfig,
    BackendInfo,
    BackendLocation,
    MessageRole,
    ProviderError,
    ProviderKind,
)
from ai_provider.coding_assist import coding_task_profile
from ai_provider.native_admission import (
    NATIVE_TOOL_EVIDENCE,
    NativeCodingClient,
    native_coding_catalog,
    native_tool_incompatibility,
    prepare_native_coding_client,
)

CATALOG = "packages/ai_orchestrator/examples/model_catalog.toml"


class RecordingClient:
    backend = BackendInfo("ollama", "gpt-oss:20b", BackendLocation.LOCAL)

    def __init__(self):
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        return AIResponse(AIMessage(MessageRole.ASSISTANT, "done"), self.backend)

    def stream(self, request):
        self.requests.append(request)
        return iter(())


@pytest.fixture
def admitted(monkeypatch):
    evidence = NATIVE_TOOL_EVIDENCE[0]
    monkeypatch.setattr(
        "ai_provider.native_admission.installed_native_identity",
        lambda config: (evidence.model_digest, evidence.runtime_version),
    )
    client = RecordingClient()
    diagnostics = []
    wrapper = NativeCodingClient(
        client, BackendConfig(ProviderKind.OLLAMA, evidence.model), 8192, diagnostics.append
    )
    return wrapper, client, diagnostics


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("changed", ["model", "digest", "runtime", "contract", "missing"])
def test_positive_and_negative_evidence_invalidates(index, changed):
    evidence = NATIVE_TOOL_EVIDENCE[index]
    values = dict(
        model=evidence.model,
        model_digest=evidence.model_digest,
        runtime_version=evidence.runtime_version,
        contract_version=evidence.contract_version,
    )
    key = {"digest": "model_digest", "runtime": "runtime_version", "contract": "contract_version"}
    if changed == "missing":
        values["model_digest"] = None
    else:
        values[key.get(changed, changed)] = 99 if changed == "contract" else "changed"
    reason = native_tool_incompatibility(**values)
    assert reason and ("unknown" in reason if changed == "model" else "stale" in reason)


def test_valid_receipts_distinguish_support_from_quality():
    for evidence in NATIVE_TOOL_EVIDENCE:
        reason = native_tool_incompatibility(
            evidence.model,
            model_digest=evidence.model_digest,
            runtime_version=evidence.runtime_version,
        )
        assert (reason is None) is evidence.supported
        if reason:
            assert "failed the runtime compatibility probe" in reason


def test_automatic_catalog_prefers_tested_local_tools_preserving_explicit_choices():
    catalog = load_model_catalog(CATALOG)
    profile = coding_task_profile()
    eligible = native_coding_catalog(catalog, profile)
    assert recommend_model(profile, eligible).selected.backend.model == "gpt-oss:20b"
    for profile in (
        coding_task_profile(model_override="qwen2.5-coder:14b"),
        coding_task_profile(route_id_override="ollama-qwen2-5-coder-14b"),
    ):
        assert native_coding_catalog(catalog, profile) is catalog
        assert recommend_model(profile, catalog).selected.backend.model == "qwen2.5-coder:14b"


def test_complete_instructions_and_metadata_survive_estimated_admission(admitted):
    wrapper, client, diagnostics = admitted
    request = AIRequest(
        (
            AIMessage(MessageRole.SYSTEM, "All instructions \u6f22\u5b57"),
            AIMessage(MessageRole.USER, "task"),
        ),
        model="gpt-oss:20b",
        metadata={"task": "coding"},
        tools=(AIToolDefinition("read_file", "Read a file"),),
    )
    wrapper.complete(request)
    forwarded = client.requests[0]
    assert forwarded.messages is request.messages
    assert forwarded.tools is request.tools
    assert forwarded.metadata == {"task": "coding", "ollama_context_length": 8192}
    assert forwarded.max_output_tokens == 2048
    assert "ollama_context_length" not in request.metadata
    assert "estimated_utf8" in diagnostics[0] and "verified_token_count=false" in diagnostics[0]


@pytest.mark.parametrize("component", ["instructions", "tool_schema", "history", "output"])
def test_overflow_refuses_without_truncation_or_inference(admitted, component):
    wrapper, client, _ = admitted
    request = AIRequest((AIMessage(MessageRole.SYSTEM, "required"),), model="gpt-oss:20b")
    if component == "instructions":
        request = replace(request, messages=(AIMessage(MessageRole.SYSTEM, "\u6f22" * 12000),))
    elif component == "tool_schema":
        request = replace(request, tools=(AIToolDefinition("huge", "schema" * 8000),))
    elif component == "history":
        request = replace(
            request, messages=(*request.messages, AIMessage(MessageRole.TOOL, "x" * 20000))
        )
    else:
        request = replace(request, max_output_tokens=8192)
    original = request
    with pytest.raises(
        ProviderError, match="complete instructions, schemas and history were preserved"
    ):
        wrapper.complete(request)
    assert request == original and not client.requests


def test_each_turn_rechecks_identity_and_keeps_original_model(admitted, monkeypatch):
    wrapper, client, _ = admitted
    request = AIRequest((AIMessage(MessageRole.USER, "task"),), model="gpt-oss:20b")
    wrapper.complete(request)
    monkeypatch.setattr(
        "ai_provider.native_admission.installed_native_identity",
        lambda config: ("updated", "0.32.5"),
    )
    with pytest.raises(ProviderError, match="stale"):
        wrapper.complete(request)
    assert len(client.requests) == 1
    assert client.requests[0].model == "gpt-oss:20b"


def test_stream_also_refuses_overflow(admitted):
    wrapper, client, _ = admitted
    with pytest.raises(ProviderError, match="does not fit"):
        list(wrapper.stream(AIRequest((AIMessage(MessageRole.USER, "x" * 20000),))))
    assert not client.requests


def test_runtime_profile_is_capped_by_model_window(admitted):
    _, client, _ = admitted
    wrapped = prepare_native_coding_client(
        client,
        BackendConfig(ProviderKind.OLLAMA, "gpt-oss:20b"),
        SimpleNamespace(catalog=CATALOG, ollama_profile="balanced"),
        None,
    )
    assert isinstance(wrapped, NativeCodingClient)
    assert wrapped.context_tokens == 8192


def test_known_cloud_capacity_and_unknown_capacity_are_distinct():
    client = RecordingClient()
    config = BackendConfig(ProviderKind.OPENAI, "custom")
    request = AIRequest((AIMessage(MessageRole.USER, "x" * 20000),), model="custom")
    with pytest.raises(ProviderError, match="does not fit"):
        NativeCodingClient(client, config, 8192).complete(request)
    diagnostics = []
    NativeCodingClient(client, config, None, diagnostics.append).complete(request)
    assert "unknown context capacity" in diagnostics[0]


def test_cli_native_boundary_enforces_guard_with_no_model_call(tmp_path, monkeypatch):
    from ai_provider import repo_coding_assistant as cli

    client = RecordingClient()
    monkeypatch.setattr(cli, "create_chat_client", lambda config: client)
    monkeypatch.setattr(
        "ai_provider.native_admission.installed_native_identity", lambda config: ("stale", "0.32.5")
    )
    args = Namespace(
        start_ollama=False,
        system=None,
        max_action_rounds=2,
        catalog=CATALOG,
        required_context="Complete required instructions",
        skill_instructions="Required skill",
    )
    with pytest.raises(ProviderError, match="stale"):
        cli._run_native_agent(
            "task",
            BackendConfig(ProviderKind.OLLAMA, "gpt-oss:20b"),
            coding_task_profile(),
            args,
            tmp_path,
        )
    assert not client.requests


def test_cli_native_boundary_preserves_required_instructions(admitted, tmp_path, monkeypatch):
    from ai_provider import repo_coding_assistant as cli

    _, client, _ = admitted
    monkeypatch.setattr(cli, "create_chat_client", lambda config: client)
    args = Namespace(
        start_ollama=False,
        system="Custom system instruction",
        max_action_rounds=2,
        catalog=CATALOG,
        ollama_profile="full",
        required_context="Complete required instructions \u6f22\u5b57",
        skill_instructions="Required skill instruction",
    )
    cli._run_native_agent(
        "task",
        BackendConfig(ProviderKind.OLLAMA, "gpt-oss:20b"),
        coding_task_profile(),
        args,
        tmp_path,
    )
    request = client.requests[0]
    assert args.system in request.messages[0].content
    assert args.required_context in request.messages[1].content
    assert args.skill_instructions in request.messages[1].content
    assert request.tools and request.metadata["ollama_context_length"] == 32768


def test_unknown_model_refuses_without_metadata_probe(monkeypatch):
    def forbidden(config):
        pytest.fail("unknown compatibility must not contact a runtime")

    monkeypatch.setattr("ai_provider.native_admission.installed_native_identity", forbidden)
    client = RecordingClient()
    wrapper = NativeCodingClient(client, BackendConfig(ProviderKind.OLLAMA, "unknown"), 8192)
    with pytest.raises(ProviderError, match="compatibility is unknown"):
        wrapper.complete(AIRequest((AIMessage(MessageRole.USER, "task"),)))
    assert not client.requests


def test_changed_active_contract_excludes_old_positive_receipt(monkeypatch):
    monkeypatch.setattr("ai_provider.native_admission.NATIVE_CONTRACT_VERSION", 2)
    eligible = native_coding_catalog(load_model_catalog(CATALOG), coding_task_profile())
    assert all(item.backend.provider != "ollama" for item in eligible)


def test_offline_native_readiness_selects_tested_route_without_metadata(
    tmp_path, monkeypatch, capsys
):
    import json

    from ai_provider import repo_coding_assistant as cli

    def forbidden(*args, **kwargs):
        pytest.fail("offline readiness must not contact a runtime")

    monkeypatch.setattr(cli, "installed_native_identity", forbidden)
    monkeypatch.setattr("ai_provider.native_admission.installed_native_identity", forbidden)
    assert (
        cli.main(
            [
                "--fallback-readiness",
                "--repo-root",
                str(tmp_path),
                "--native-tools",
                "--cost-policy",
                "local_only",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert "gpt-oss" in str(report)


@pytest.mark.parametrize("context,output", [(True, 10), (0, 10), (8192, True), (8192, 0)])
def test_invalid_budgets_refuse_before_inference(admitted, context, output):
    wrapper, client, _ = admitted
    wrapper.context_tokens = context
    with pytest.raises(ProviderError, match="Invalid native"):
        wrapper.complete(
            AIRequest((AIMessage(MessageRole.USER, "task"),), max_output_tokens=output)
        )
    assert not client.requests


def test_history_overflow_preserves_observed_tool_receipt(admitted, tmp_path, monkeypatch):
    from ai_agent import AgentLoop, PermissionManager, PermissionPolicy, ToolContext
    from ai_agent.tools import ReadFileTool, ToolRegistry

    wrapper, client, _ = admitted
    contents = "receipt data " * 2000
    (tmp_path / "large.txt").write_text(contents, encoding="utf-8")

    def read_call(request):
        client.requests.append(request)
        return AIResponse(
            AIMessage(MessageRole.ASSISTANT, ""),
            client.backend,
            tool_calls=(AIToolCall("read-1", "read_file", {"path": "large.txt"}),),
        )

    monkeypatch.setattr(client, "complete", read_call)
    agent = AgentLoop(
        wrapper,
        ToolRegistry(tools=(ReadFileTool(),)),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.read_only()),
    )
    with pytest.raises(ProviderError, match="does not fit") as caught:
        agent.run(
            "Read large.txt", system_prompt="Preserve complete requirements", model="gpt-oss:20b"
        )
    assert len(client.requests) == 1
    assert any(
        message.role is MessageRole.TOOL and contents in message.content
        for message in caught.value.partial_messages
    )
    assert (tmp_path / "large.txt").read_text(encoding="utf-8") == contents


def test_resource_profile_cannot_exceed_declared_model_window(admitted, monkeypatch):
    from ai_orchestrator.models import ModelContextLimits

    _, client, _ = admitted
    catalog = load_model_catalog(CATALOG)
    gpt = next(item for item in catalog if item.backend.model == "gpt-oss:20b")
    limited = replace(
        gpt,
        backend=replace(gpt.backend, context_limits=ModelContextLimits(context_window_tokens=4096)),
    )
    monkeypatch.setattr("ai_orchestrator.load_model_catalog", lambda path: (limited,))
    wrapped = prepare_native_coding_client(
        client,
        BackendConfig(ProviderKind.OLLAMA, "gpt-oss:20b"),
        Namespace(catalog=CATALOG, ollama_profile="full"),
        None,
    )
    assert isinstance(wrapped, NativeCodingClient) and wrapped.context_tokens == 4096
