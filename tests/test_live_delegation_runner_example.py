from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
from ai_orchestrator import (
    CostPolicyTier,
    TaskProfile,
    TaskType,
    load_model_catalog,
)
from ai_orchestrator import (
    PrivacyClass as OrchestratorPrivacyClass,
)
from ai_provider import (
    AIMessage,
    AIRequest,
    AIResponse,
    BackendConfig,
    BackendInfo,
    BackendLocation,
    ChatClient,
    FinishReason,
    MessageRole,
    ModelCapabilities,
    ProviderKind,
    UsageMetadata,
    UsageSource,
)

_EXAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "packages"
    / "ai_provider"
    / "examples"
    / "live_delegation_runner.py"
)
_SPEC = importlib.util.spec_from_file_location("live_delegation_runner_example", _EXAMPLE_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_EXAMPLE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _EXAMPLE
_SPEC.loader.exec_module(_EXAMPLE)

backend_config_from_target = _EXAMPLE.backend_config_from_target
build_parser = _EXAMPLE.build_parser
default_catalog_path = _EXAMPLE.default_catalog_path
execute_delegated_workflow = _EXAMPLE.execute_delegated_workflow
main = _EXAMPLE.main


class _MockChatClient(ChatClient):
    def __init__(self, config: BackendConfig, response_text: str) -> None:
        self._config = config
        self._response_text = response_text
        self.recorded_requests: list[AIRequest] = []

    @property
    def backend(self) -> BackendInfo:
        return BackendInfo(
            provider=self._config.provider.value,
            model=self._config.model,
            location=BackendLocation.LOCAL
            if self._config.provider is ProviderKind.OLLAMA
            else BackendLocation.EXTERNAL,
            capabilities=ModelCapabilities(chat=True),
        )

    def complete(self, request: AIRequest) -> AIResponse:
        self.recorded_requests.append(request)
        return AIResponse(
            message=AIMessage(role=MessageRole.ASSISTANT, content=self._response_text),
            backend=self.backend,
            finish_reason=FinishReason.STOP,
            usage=UsageMetadata(
                source=UsageSource.PROVIDER_REPORTED,
                input_tokens=10,
                output_tokens=20,
                total_tokens=30,
            ),
            latency_ms=42.0,
        )

    def stream(self, request: AIRequest) -> Any:
        raise NotImplementedError()


def test_live_delegation_runner_parser_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args([])

    assert args.catalog == default_catalog_path()
    assert args.privacy == OrchestratorPrivacyClass.EXTERNAL_ALLOWED.value
    assert args.cost_policy == CostPolicyTier.FREE_ONLY.value
    assert args.execute is False


def test_execute_delegated_workflow_dry_run() -> None:
    catalog = load_model_catalog(default_catalog_path())
    primary_profile = TaskProfile(
        task_type=TaskType.CODING,
        privacy_class=OrchestratorPrivacyClass.EXTERNAL_ALLOWED,
        cost_policy_tier=CostPolicyTier.FREE_ONLY,
    )

    result = execute_delegated_workflow(
        primary_prompt="Refactor connection pool",
        raw_context="def connect(): pass",
        primary_profile=primary_profile,
        catalog=catalog,
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.primary_plan.target.provider == "google"
    assert result.final_response is None
    assert len(result.delegated_subtask_records) == 0


def test_execute_delegated_workflow_with_mock_clients() -> None:
    catalog = load_model_catalog(default_catalog_path())
    primary_profile = TaskProfile(
        task_type=TaskType.CODING,
        privacy_class=OrchestratorPrivacyClass.EXTERNAL_ALLOWED,
        cost_policy_tier=CostPolicyTier.FREE_ONLY,
    )

    created_clients: dict[str, _MockChatClient] = {}

    def mock_factory(config: BackendConfig) -> ChatClient:
        if config.provider is ProviderKind.OLLAMA:
            client = _MockChatClient(
                config,
                "Summary: DB module defines connection functions and requires pooled reuse.",
            )
        else:
            client = _MockChatClient(
                config,
                "Primary Solution: Connection pool implemented with acquire and release methods.",
            )
        created_clients[f"{config.provider.value}-{config.model}"] = client
        return client

    result = execute_delegated_workflow(
        primary_prompt="Refactor database connector to support pooling",
        raw_context="class DB: def connect(self): pass\ndef execute_query(q): pass",
        primary_profile=primary_profile,
        catalog=catalog,
        client_factory=mock_factory,
        dry_run=False,
    )

    assert result.dry_run is False
    assert len(result.delegated_subtask_records) == 1
    subtask_record = result.delegated_subtask_records[0]
    assert subtask_record.provider == "ollama"
    assert "Summary: DB module" in subtask_record.response.message.content

    assert result.final_response is not None
    assert "Primary Solution: Connection pool" in result.final_response.message.content
    assert "--- Locally Extracted Context Summary ---" in result.composed_primary_prompt
    assert "Summary: DB module" in result.composed_primary_prompt


def test_live_delegation_runner_cli_dry_run_output(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["Refactor database", "--privacy", "external_allowed"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "=== Planned Live Delegation Workflow (Dry-Run) ===" in out
    assert "Primary Target:" in out
