from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from ai_orchestrator import (
    BackendLocation,
    ExecutionTarget,
    ModelBackend,
    ModelCatalogEntry,
    OrchestrationStatus,
    TaskProfile,
)
from ai_provider import ProviderKind

_EXAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "packages"
    / "ai_provider"
    / "examples"
    / "orchestrator_execution_target.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "orchestrator_execution_target_example", _EXAMPLE_PATH
)
assert _SPEC is not None
assert _SPEC.loader is not None
_EXAMPLE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_EXAMPLE)
backend_config_from_execution_target = _EXAMPLE.backend_config_from_execution_target
prepare_backend_config = _EXAMPLE.prepare_backend_config


def _candidate(
    provider: str = "ollama",
    model: str = "llama3.2",
    location: BackendLocation = BackendLocation.LOCAL,
) -> ModelCatalogEntry:
    return ModelCatalogEntry(
        backend=ModelBackend(
            provider=provider,
            model=model,
            location=location,
            base_url="http://localhost:11434" if provider == "ollama" else None,
        )
    )


def test_orchestrator_execution_target_can_be_adapted_to_provider_config() -> None:
    target = ExecutionTarget(
        provider="ollama",
        model="llama3.2",
        base_url="http://localhost:11434",
        timeout_seconds=15,
    )

    config = backend_config_from_execution_target(target)

    assert config.provider is ProviderKind.OLLAMA
    assert config.model == "llama3.2"
    assert config.base_url == "http://localhost:11434"
    assert config.timeout_seconds == 15


def test_orchestrator_target_adapter_rejects_unknown_provider() -> None:
    target = ExecutionTarget(provider="custom", model="model")

    with pytest.raises(ValueError, match="not supported by ai_provider"):
        backend_config_from_execution_target(target)


def test_prepare_backend_config_adapts_ready_orchestration_result() -> None:
    result, config = prepare_backend_config(
        "Explain how to run the provider tests as a numbered list with short commands.",
        TaskProfile(),
        (_candidate(),),
        timeout_seconds=15,
    )

    assert result.status is OrchestrationStatus.READY
    assert config is not None
    assert config.provider is ProviderKind.OLLAMA
    assert config.model == "llama3.2"
    assert config.base_url == "http://localhost:11434"
    assert config.timeout_seconds == 15


def test_prepare_backend_config_returns_no_config_when_prompt_needs_review() -> None:
    result, config = prepare_backend_config("Fix this", TaskProfile(), (_candidate(),))

    assert result.status is OrchestrationStatus.NEEDS_PROMPT_REVIEW
    assert config is None


def test_prepare_backend_config_returns_no_config_when_model_selection_fails() -> None:
    result, config = prepare_backend_config(
        "Explain how to run the provider tests as a numbered list with short commands.",
        TaskProfile(),
        (),
    )

    assert result.status is OrchestrationStatus.MODEL_SELECTION_FAILED
    assert config is None
