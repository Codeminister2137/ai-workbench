from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from ai_orchestrator import (
    CostPolicyTier,
    DelegatedSubtaskPlan,
    ExecutionPlan,
    ModelCatalogEntry,
    PrivacyClass,
    TaskProfile,
    TaskType,
    load_model_catalog,
    plan_delegated_subtask,
    prepare_execution,
)


@dataclass(frozen=True, slots=True)
class DelegatedTaskWorkflow:
    """A primary task execution plan along with its planned local subtasks."""

    primary_plan: ExecutionPlan
    delegated_subtasks: tuple[DelegatedSubtaskPlan, ...]


def plan_delegated_workflow(
    primary_prompt: str,
    primary_profile: TaskProfile,
    catalog: tuple[ModelCatalogEntry, ...],
    subtasks: tuple[tuple[str, str, TaskType], ...] = (
        ("context_summary", "Summarize repository context locally", TaskType.SUMMARIZATION),
        ("prompt_refinement", "Refine and check prompt constraints locally", TaskType.GENERAL),
    ),
    *,
    subtask_cost_tier: CostPolicyTier = CostPolicyTier.LOCAL_ONLY,
    subtask_privacy: PrivacyClass | None = None,
) -> DelegatedTaskWorkflow:
    """Plan a primary task and delegate preparatory subtasks to local compute."""
    primary_result = prepare_execution(
        primary_prompt,
        primary_profile,
        catalog,
        review_prompt=False,
    )
    if not primary_result.is_ready or primary_result.execution_plan is None:
        raise ValueError(
            f"Primary task planning failed: status={primary_result.status.value}, "
            f"failure_reason={primary_result.failure_reason}"
        )

    planned_subtasks: list[DelegatedSubtaskPlan] = []
    for subtask_id, description, task_type in subtasks:
        delegated = plan_delegated_subtask(
            parent_profile=primary_profile,
            catalog=catalog,
            task_type=task_type,
            subtask_id=subtask_id,
            description=description,
            cost_policy_tier=subtask_cost_tier,
            privacy_class=subtask_privacy,
        )
        planned_subtasks.append(delegated)

    return DelegatedTaskWorkflow(
        primary_plan=primary_result.execution_plan,
        delegated_subtasks=tuple(planned_subtasks),
    )


def default_catalog_path() -> Path:
    """Return default model catalog path."""
    return Path(__file__).resolve().parent / "model_catalog.toml"


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for the Ollama delegation example."""
    parser = argparse.ArgumentParser(
        description="Demonstrate multi-phase planning delegating subtasks to local Ollama."
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Refactor module to improve error handling and telemetry.",
        help="Primary task prompt",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=default_catalog_path(),
        help="Path to model catalog TOML file",
    )
    parser.add_argument(
        "--privacy",
        choices=[p.value for p in PrivacyClass],
        default=PrivacyClass.EXTERNAL_ALLOWED.value,
        help="Primary task privacy class",
    )
    parser.add_argument(
        "--cost-policy",
        choices=[c.value for c in CostPolicyTier],
        default=CostPolicyTier.ALLOWANCES_ALLOWED.value,
        help="Primary task cost policy tier",
    )
    parser.add_argument(
        "--subtask-cost-policy",
        choices=[c.value for c in CostPolicyTier],
        default=CostPolicyTier.LOCAL_ONLY.value,
        help="Cost policy tier for delegated subtasks (default: local_only)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run CLI entrypoint for Ollama delegation example."""
    parser = build_parser()
    args = parser.parse_args(argv)

    catalog = load_model_catalog(args.catalog)
    primary_profile = TaskProfile(
        task_type=TaskType.CODING,
        privacy_class=PrivacyClass(args.privacy),
        cost_policy_tier=CostPolicyTier(args.cost_policy),
    )

    workflow = plan_delegated_workflow(
        primary_prompt=args.prompt,
        primary_profile=primary_profile,
        catalog=catalog,
        subtask_cost_tier=CostPolicyTier(args.subtask_cost_policy),
    )

    print("=== Primary Task Plan ===")
    print(f"Target Route:    {workflow.primary_plan.target.route_id}")
    print(
        f"Provider/Model:  {workflow.primary_plan.target.provider}/"
        f"{workflow.primary_plan.target.model}"
    )
    print(f"Access Method:   {workflow.primary_plan.target.access_method.value}")
    print(f"Cost Policy:     {workflow.primary_plan.target.cost_policy_tier.value}")
    print(f"Billing Source:  {workflow.primary_plan.target.billing_source.value}")
    print("Reasons:")
    for reason in workflow.primary_plan.reasons:
        print(f"  - {reason}")

    print("\n=== Delegated Subtasks ===")
    for subtask in workflow.delegated_subtasks:
        target = subtask.execution_plan.target
        print(f"\nSubtask:         [{subtask.subtask_id}] {subtask.description}")
        print(f"  Privacy Class: {subtask.profile.privacy_class.value}")
        print(f"  Cost Policy:   {subtask.profile.cost_policy_tier.value}")
        print(f"  Target Route:  {target.route_id} ({target.provider}/{target.model})")
        print(f"  Access Method: {target.access_method.value}")
        print(f"  Billing:       {target.billing_source.value}")
        print("  Reasons:")
        for reason in subtask.execution_plan.reasons:
            print(f"    - {reason}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
