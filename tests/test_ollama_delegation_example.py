from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from ai_orchestrator import (
    AccessMethod,
    CostPolicyTier,
    PrivacyClass,
    TaskProfile,
    TaskType,
    load_model_catalog,
)

_EXAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "packages"
    / "ai_orchestrator"
    / "examples"
    / "ollama_delegation.py"
)
_SPEC = importlib.util.spec_from_file_location("ollama_delegation_example", _EXAMPLE_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_EXAMPLE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _EXAMPLE
_SPEC.loader.exec_module(_EXAMPLE)

build_parser = _EXAMPLE.build_parser
default_catalog_path = _EXAMPLE.default_catalog_path
main = _EXAMPLE.main
plan_delegated_workflow = _EXAMPLE.plan_delegated_workflow


def test_ollama_delegation_example_parser_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args([])

    assert args.catalog == default_catalog_path()
    assert args.privacy == PrivacyClass.EXTERNAL_ALLOWED.value
    assert args.cost_policy == CostPolicyTier.ALLOWANCES_ALLOWED.value
    assert args.subtask_cost_policy == CostPolicyTier.LOCAL_ONLY.value


def test_plan_delegated_workflow_creates_primary_and_subtask_plans() -> None:
    catalog = load_model_catalog(default_catalog_path())
    primary_profile = TaskProfile(
        task_type=TaskType.CODING,
        privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        cost_policy_tier=CostPolicyTier.ALLOWANCES_ALLOWED,
    )

    workflow = plan_delegated_workflow(
        primary_prompt="Implement the new feature",
        primary_profile=primary_profile,
        catalog=catalog,
    )

    assert workflow.primary_plan.target.cost_policy_tier in {
        CostPolicyTier.LOCAL_ONLY,
        CostPolicyTier.ALLOWANCES_ALLOWED,
    }

    assert len(workflow.delegated_subtasks) == 2
    for subtask in workflow.delegated_subtasks:
        assert subtask.profile.cost_policy_tier is CostPolicyTier.LOCAL_ONLY
        assert subtask.profile.privacy_class is PrivacyClass.EXTERNAL_ALLOWED
        assert subtask.execution_plan.target.provider == "ollama"
        assert subtask.execution_plan.target.access_method is AccessMethod.LOCAL_RUNTIME


def test_ollama_delegation_cli_main_output(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["Implement error handling", "--privacy", "external_allowed"])

    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "=== Primary Task Plan ===" in captured
    assert "=== Delegated Subtasks ===" in captured
    assert "Subtask:         [context_summary]" in captured
    assert "Subtask:         [prompt_refinement]" in captured
