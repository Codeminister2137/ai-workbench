from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai_orchestrator import (
    AccessMethod,
    CostPolicyTier,
    DelegatedSubtaskPlan,
    ExecutionPlan,
    ModelCatalogEntry,
    TaskProfile,
    TaskType,
    load_model_catalog,
    plan_delegated_subtask,
    prepare_execution,
)
from ai_orchestrator import (
    PrivacyClass as OrchestratorPrivacyClass,
)
from ai_provider import (
    AIMessage,
    AIRequest,
    AIResponse,
    BackendConfig,
    ChatClient,
    MessageRole,
    ProviderKind,
    create_chat_client,
)
from ai_provider import (
    PrivacyClass as ProviderPrivacyClass,
)


@dataclass(frozen=True, slots=True)
class SubtaskExecutionRecord:
    """Record of a completed delegated subtask execution."""

    subtask_id: str
    description: str
    target_route: str
    provider: str
    model: str
    response: AIResponse


@dataclass(frozen=True, slots=True)
class LiveDelegationResult:
    """Result of an end-to-end multi-model delegation execution."""

    primary_plan: ExecutionPlan
    delegated_subtask_records: tuple[SubtaskExecutionRecord, ...]
    final_response: AIResponse | None = None
    composed_primary_prompt: str = ""
    dry_run: bool = False


ClientFactory = Callable[[BackendConfig], ChatClient]


def backend_config_from_target(
    target: ExecutionPlan,
    *,
    default_timeout: float = 60.0,
) -> BackendConfig:
    """Convert an orchestrator ExecutionPlan target into an ai_provider BackendConfig."""
    plan_target = target.target
    if plan_target.access_method not in {
        AccessMethod.LOCAL_RUNTIME,
        AccessMethod.PROVIDER_API,
    }:
        raise ValueError(
            f"Access method {plan_target.access_method.value!r} cannot be executed directly "
            "by ai_provider. Use a dedicated CLI runner."
        )

    return BackendConfig(
        provider=ProviderKind(plan_target.provider),
        model=plan_target.model,
        base_url=plan_target.base_url,
        timeout_seconds=plan_target.timeout_seconds or default_timeout,
    )


def execute_delegated_workflow(
    primary_prompt: str,
    raw_context: str,
    primary_profile: TaskProfile,
    catalog: tuple[ModelCatalogEntry, ...],
    *,
    client_factory: ClientFactory = create_chat_client,
    dry_run: bool = False,
    subtask_cost_tier: CostPolicyTier = CostPolicyTier.LOCAL_ONLY,
) -> LiveDelegationResult:
    """Execute a multi-stage workflow delegating context summarization locally before execution."""
    # 1. Prepare Primary Plan
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

    # 2. Plan Local Delegated Subtask for Context Extraction/Summary
    subtask_plan: DelegatedSubtaskPlan = plan_delegated_subtask(
        parent_profile=primary_profile,
        catalog=catalog,
        task_type=TaskType.SUMMARIZATION,
        subtask_id="context_summarization",
        description="Summarize large repository context into concise architectural constraints",
        cost_policy_tier=subtask_cost_tier,
    )

    if dry_run:
        return LiveDelegationResult(
            primary_plan=primary_result.execution_plan,
            delegated_subtask_records=(),
            composed_primary_prompt=primary_prompt,
            dry_run=True,
        )

    # 3. Execute Delegated Subtask Locally (e.g. Ollama)
    subtask_config = backend_config_from_target(subtask_plan.execution_plan)
    subtask_client = client_factory(subtask_config)
    subtask_prompt = (
        "Summarize the following code context into key architectural constraints and definitions "
        f"needed for the task:\n\n{raw_context}"
    )
    subtask_request = AIRequest(
        messages=(AIMessage(role=MessageRole.USER, content=subtask_prompt),),
        model=subtask_config.model,
        privacy_class=ProviderPrivacyClass(subtask_plan.profile.privacy_class.value),
    )
    subtask_response = subtask_client.complete(subtask_request)

    subtask_record = SubtaskExecutionRecord(
        subtask_id=subtask_plan.subtask_id,
        description=subtask_plan.description,
        target_route=subtask_plan.execution_plan.target.route_id,
        provider=subtask_config.provider.value,
        model=subtask_config.model,
        response=subtask_response,
    )

    # 4. Compose Primary Prompt with Locally Pre-Digested Summary
    locally_digested_summary = subtask_response.message.content.strip()
    composed_prompt = (
        f"{primary_prompt}\n\n"
        "--- Locally Extracted Context Summary ---\n"
        f"{locally_digested_summary}\n"
        "-----------------------------------------"
    )

    # 5. Execute Primary Task on Selected Backend (e.g. Google Gemini, OpenAI, or local model)
    primary_config = backend_config_from_target(primary_result.execution_plan)
    primary_client = client_factory(primary_config)
    primary_request = AIRequest(
        messages=(AIMessage(role=MessageRole.USER, content=composed_prompt),),
        model=primary_config.model,
        privacy_class=ProviderPrivacyClass(primary_profile.privacy_class.value),
    )
    final_response = primary_client.complete(primary_request)

    return LiveDelegationResult(
        primary_plan=primary_result.execution_plan,
        delegated_subtask_records=(subtask_record,),
        final_response=final_response,
        composed_primary_prompt=composed_prompt,
        dry_run=False,
    )


def default_catalog_path() -> Path:
    """Return default model catalog path."""
    return (
        Path(__file__).resolve().parents[2] / "ai_orchestrator" / "examples" / "model_catalog.toml"
    )


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser for live delegation runner."""
    parser = argparse.ArgumentParser(
        description="Execute multi-model workflow with local Ollama delegation."
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Refactor database connector to support connection pooling.",
        help="Primary task instruction",
    )
    parser.add_argument(
        "--context",
        default="class DB: def connect(self): pass\ndef execute_query(q): pass",
        help="Raw context or source code to summarize locally",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=default_catalog_path(),
        help="Path to model catalog TOML file",
    )
    parser.add_argument(
        "--privacy",
        choices=[p.value for p in OrchestratorPrivacyClass],
        default=OrchestratorPrivacyClass.EXTERNAL_ALLOWED.value,
        help="Primary task privacy class",
    )
    parser.add_argument(
        "--cost-policy",
        choices=[c.value for c in CostPolicyTier],
        default=CostPolicyTier.FREE_ONLY.value,
        help="Primary task cost policy tier (e.g. free_only, allowances_allowed, billing_allowed)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute live requests against configured provider backends (dry-run by default)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run CLI entrypoint for live delegation workflow."""
    parser = build_parser()
    args = parser.parse_args(argv)

    catalog = load_model_catalog(args.catalog)
    primary_profile = TaskProfile(
        task_type=TaskType.CODING,
        privacy_class=OrchestratorPrivacyClass(args.privacy),
        cost_policy_tier=CostPolicyTier(args.cost_policy),
    )

    result = execute_delegated_workflow(
        primary_prompt=args.prompt,
        raw_context=args.context,
        primary_profile=primary_profile,
        catalog=catalog,
        dry_run=not args.execute,
    )

    if result.dry_run:
        print("=== Planned Live Delegation Workflow (Dry-Run) ===")
        print(f"Primary Target: {result.primary_plan.target.route_id}")
        print(
            f"Provider/Model: {result.primary_plan.target.provider}/"
            f"{result.primary_plan.target.model}"
        )
        print(f"Cost Policy:    {result.primary_plan.target.cost_policy_tier.value}")
        print(f"Billing Source: {result.primary_plan.target.billing_source.value}")
        print("Pass --execute to run live Ollama summarization and primary execution.")
        return 0

    print("=== Execution Complete ===")
    for subtask in result.delegated_subtask_records:
        print(f"\n[Subtask: {subtask.subtask_id}] (Route: {subtask.target_route})")
        print(f"Response: {subtask.response.message.content.strip()}")

    if result.final_response is not None:
        print(f"\n[Primary Task Result] (Route: {result.primary_plan.target.route_id})")
        print(f"Response: {result.final_response.message.content.strip()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
