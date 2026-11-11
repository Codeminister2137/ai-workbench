"""AgentLoop-backed executor for drained runs (owner-approved full tools).

``build_executor`` adapts a run record to ``AgentLoop.run``: the client
comes from the dashboard provider config, the registry carries the full
coding toolset with staged (never direct) file writes plus one-level
subagents and owner-task filing, and the result maps to a drain receipt
with staged records attached. File changes land in ``run["staged"]``
for the existing review/approve flow; human tasks land in the inbox;
shell and Python tools run unconfined, which the owner explicitly
approved per run-level approval (no per-command gate).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from ai_agent.delegation_runner import build_child_runner
from ai_agent.fanout import FanoutPolicy
from ai_agent.loop import AgentIterationLimitExceeded, AgentLoop, AgentResult
from ai_agent.permissions import (
    ApprovalPolicyPreset,
    PermissionManager,
    PermissionPolicy,
)
from ai_agent.staged_edits import ProjectRoots, StagedEditError
from ai_agent.supervisor_drain import Executor
from ai_agent.tools.base import ToolContext, ToolRegistry
from ai_agent.tools.delegation import DelegateTaskTool, unavailable_delegation
from ai_agent.tools.filesystem import ListDirTool, ReadFileTool
from ai_agent.tools.git import GitDiffTool, GitStatusTool
from ai_agent.tools.owner_tasks import OwnerTaskTool
from ai_agent.tools.python_runtime import PythonRuntimeTool
from ai_agent.tools.refactor import PythonNavigateTool, RenamePlanStore, RenamePreviewTool
from ai_agent.tools.research_search import SearchSession, SearchWebTool
from ai_agent.tools.search import FindFilesTool, GrepSearchTool
from ai_agent.tools.shell import RunCommandTool
from ai_agent.tools.staged import StageFileTool
from ai_provider import PrivacyClass, ProviderError
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.factory import create_chat_client
from dashboard_config import DashboardConfig

logger = logging.getLogger(__name__)

MAX_SUMMARY_CHARS = 2000
# Fixed Ollama window for runs: tool results accumulate over iterations, so
# size for growth, not for the small initial prompt. Model capacity is 131072.
EXECUTOR_CONTEXT_TOKENS = 32768

EXECUTOR_SYSTEM_PROMPT = """You are the workbench run agent. Complete the task below inside the
project workspace. Rules: change project files ONLY through the stage_file
tool (staged changes are reviewed by the owner after the run); never write
outside the workspace; break big work into delegate_task subagents when
allowed; file anything only the human can do via request_owner_task;
verify with tests/checks when the task involves code; finish with a
short summary of what changed and what remains."""


def build_executor_registry(*, runner=None, fanout: str = "restricted") -> ToolRegistry:
    """Full coding toolset: staged writes, subagents, owner tasks.

    ``runner`` backs delegate_task (unavailable by default: attempts fail
    honestly); ``fanout`` gates child spawns per run.
    """
    plans = RenamePlanStore()
    return ToolRegistry(
        tools=(
            ReadFileTool(),
            ListDirTool(),
            FindFilesTool(),
            GrepSearchTool(),
            GitStatusTool(),
            GitDiffTool(),
            RunCommandTool(),
            PythonRuntimeTool(),
            PythonNavigateTool(),
            RenamePreviewTool(plans),
            StageFileTool(),
            OwnerTaskTool(),
            SearchWebTool(SearchSession.from_environment(lambda _event, _receipt: None)),
            DelegateTaskTool(
                runner=runner or unavailable_delegation,
                fanout=FanoutPolicy.coerce(fanout),
            ),
        )
    )


def _run_prompt(run: dict, workspace: Path) -> str:
    title = run.get("title") or "(untitled)"
    body = run.get("body") or ""
    return f"Run {run.get('id', '?')}: {title}\nWorkspace: {workspace}\n\nTask:\n{body}"


def _collect_staged(result: AgentResult) -> list[dict]:
    staged: list[dict] = []
    for tool_result in result.tool_results:
        record = tool_result.metadata.get("staged")
        if isinstance(record, dict) and record.get("relpath"):
            staged.append(record)
        for child in tool_result.metadata.get("child_staged") or []:
            if isinstance(child, dict) and child.get("relpath"):
                staged.append(child)
    return staged


def _collect_owner_tasks(result: AgentResult) -> list[dict]:
    tasks: list[dict] = []
    for tool_result in result.tool_results:
        task = tool_result.metadata.get("owner_task")
        if isinstance(task, dict) and task.get("title") and task.get("body"):
            tasks.append(task)
    return tasks


def _resolve_backend(
    config: DashboardConfig, repo_root: Path, run_title: str
) -> tuple[BackendConfig | None, PrivacyClass, str]:
    """Resolve the model backend for one run.

    ``configured`` (default) uses the dashboard provider/model exactly as
    before. ``auto`` routes through the orchestrator (local posture, free and
    allowance tiers plus owner exemptions, outcome demotions) and falls back
    to the configured backend when routing is unavailable.
    """
    try:
        provider = ProviderKind(config.provider)
    except ValueError:
        provider = None
    privacy = (
        PrivacyClass.LOCAL_ONLY
        if provider is ProviderKind.OLLAMA
        else PrivacyClass.EXTERNAL_ALLOWED
    )
    configured = (
        BackendConfig(provider=provider, model=config.model, base_url=config.base_url)
        if provider is not None
        else None
    )
    configured_id = f"{config.provider}/{config.model}" if provider is not None else "unknown"
    if config.route_policy != "auto":
        return configured, privacy, configured_id
    try:
        from ai_orchestrator import CostPolicyTier, load_model_catalog, prepare_execution
        from ai_orchestrator.models import PrivacyClass as OrchestratorPrivacy
        from ai_orchestrator.route_outcomes import (
            OUTCOMES_FILENAME,
            load_quality_adjustments,
        )
        from ai_provider.coding_assist import coding_task_profile
        from ai_provider.user_config import active_cost_exemptions, load_user_config

        catalog_path = (
            Path(config.catalog_path)
            if config.catalog_path
            else repo_root / "packages/ai_orchestrator/examples/model_catalog.toml"
        )
        catalog = load_model_catalog(catalog_path)
        user_config = load_user_config(repo_root / "user-config.toml")
        profile = coding_task_profile(
            privacy_class=(
                OrchestratorPrivacy.LOCAL_ONLY
                if privacy is PrivacyClass.LOCAL_ONLY
                else OrchestratorPrivacy.EXTERNAL_ALLOWED
            ),
            cost_policy_tier=CostPolicyTier.ALLOWANCES_ALLOWED,
        )
        result = prepare_execution(
            run_title,
            profile,
            catalog,
            review_prompt=False,
            cost_exemptions=active_cost_exemptions(user_config),
            quality_adjustments=load_quality_adjustments(
                repo_root / "artifacts" / OUTCOMES_FILENAME
            ),
        )
        if result.execution_plan is None:
            raise ValueError(result.failure_reason or "no execution plan")
        target = result.execution_plan.target
        backend = BackendConfig(provider=ProviderKind(target.provider), model=target.model)
        return backend, privacy, target.route_id
    except Exception as exc:  # noqa: BLE001 - routing must never break a run
        logger.warning("auto routing unavailable, using configured backend: %s", exc)
        return configured, privacy, configured_id


def build_executor(
    config: DashboardConfig,
    roots: ProjectRoots,
    repo_root: Path,
    *,
    client_factory: Callable[[BackendConfig], Any] = create_chat_client,
    loop_factory: Callable[..., Any] = AgentLoop,
    inbox_create: Callable[..., dict] | None = None,
    max_iterations: int | None = None,
    restrictions: Mapping[str, bool] | None = None,
) -> Executor:
    """Build a drain ``Executor`` running each approved run through AgentLoop.

    ``inbox_create`` files owner tasks (dashboard inbox); without it, a run
    that files human tasks fails closed instead of dropping them.
    ``restrictions`` carries owner toggles (auto_routing, shell_tools,
    sandbox, delegation); missing keys fall back to safe defaults.
    """
    budget = config.max_iterations if max_iterations is None else max_iterations
    try:
        runner_provider = ProviderKind(config.provider)
    except ValueError:
        runner_provider = None
    runner_privacy = (
        PrivacyClass.LOCAL_ONLY
        if runner_provider is ProviderKind.OLLAMA
        else PrivacyClass.EXTERNAL_ALLOWED
    )
    runner = build_child_runner(
        max_iterations=min(budget, 15),
        privacy_class=runner_privacy,
        loop_factory=loop_factory,
    )
    toggles: dict[str, bool] = {
        "auto_routing": False,
        "shell_tools": True,
        "sandbox": False,
        "delegation": False,
    }
    if restrictions:
        for key in toggles:
            if isinstance(restrictions.get(key), bool):
                toggles[key] = restrictions[key]
    base_policy = PermissionPolicy.from_approval_preset(ApprovalPolicyPreset.TRUSTED_LOCAL)
    if not toggles["shell_tools"]:
        from ai_agent.contracts import PermissionAction

        base_policy = replace(
            base_policy,
            tool_rules=(
                *base_policy.tool_rules,
                ("run_command", PermissionAction.DENY),
                ("python_runtime", PermissionAction.DENY),
            ),
        )
    permissions = PermissionManager(base_policy)
    effective_config = replace(config, route_policy="auto") if toggles["auto_routing"] else config

    def _execute(run: dict) -> dict[str, Any]:
        run_id = str(run.get("id", "?"))
        backend, privacy, route_id = _resolve_backend(
            effective_config, repo_root, str(run.get("title") or "(untitled)")
        )
        if backend is None:
            return {"status": "failed", "error": f"Unknown provider {config.provider!r}."}
        client = client_factory(backend)
        project_id = run.get("project_id")
        try:
            if isinstance(project_id, str) and project_id:
                workspace = roots.select(project_id)
            else:
                workspace = Path(repo_root)
        except StagedEditError as exc:
            return {"status": "failed", "error": f"Project scope refused: {exc}"}
        fanout = (
            run.get("fanout_effective")
            or run.get("fanout_policy")
            or ("allowed" if toggles["delegation"] else "restricted")
        )
        context = ToolContext(workspace_root=workspace, sandbox=toggles["sandbox"])
        try:
            registry = build_executor_registry(runner=runner, fanout=str(fanout))
            loop = loop_factory(
                client,
                registry,
                context,
                permissions=permissions,
                max_iterations=budget,
                loop_context_budget_chars=config.loop_context_budget_chars or None,
                require_grounded_reports=config.require_grounded_reports,
                fanout_policy=fanout,
                request_metadata={"ollama_context_length": EXECUTOR_CONTEXT_TOKENS},
            )
        except ValueError as exc:
            return {"status": "failed", "error": str(exc)}
        try:
            result = loop.run(
                _run_prompt(run, workspace),
                system_prompt=EXECUTOR_SYSTEM_PROMPT,
                privacy_class=privacy,
            )
        except AgentIterationLimitExceeded as exc:
            return {"status": "failed", "error": f"Iteration limit reached: {exc}"}
        except ProviderError as exc:
            return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
        summary = result.response.message.content or ""
        owner_tasks = _collect_owner_tasks(result)
        filed: list[str] = []
        if owner_tasks:
            if inbox_create is None:
                return {
                    "status": "failed",
                    "error": "Run filed owner tasks but no inbox is wired; refusing to drop them.",
                }
            for task in owner_tasks:
                try:
                    item = inbox_create(
                        title=task["title"],
                        body=task["body"],
                        task_type="task",
                        task_id=run_id,
                        context_refs=[f"run:{run_id}"],
                    )
                except Exception as exc:
                    return {"status": "failed", "error": f"Owner-task filing failed: {exc}"}
                filed.append(str(item.get("id", "?")))
        # Collect receipt data before fallback so fallback can reference it.
        iterations = result.iterations
        tool_calls = [item.name for item in result.tool_results]
        staged = _collect_staged(result)
        if not summary.strip():
            logger.info("run %s blank summary; fallback from receipts", run_id)
            tools_str = ", ".join(tool_calls) if tool_calls else "none"
            staged_str = ", ".join(r["relpath"] for r in staged) if staged else "none"
            summary = (
                f"Run {run_id} completed in {iterations} iterations without a model summary. "
                f"Tools used: {tools_str}. "
                f"Staged files: {staged_str}. "
                f"Owner tasks filed: {len(filed)}."
            )
        receipt: dict[str, Any] = {
            "status": "completed",
            "summary": summary[:MAX_SUMMARY_CHARS],
            "route_id": route_id,
            "iterations": iterations,
            "tool_calls": tool_calls,
            "staged": staged,
            "owner_tasks": filed,
            "compactions": getattr(result, "compactions", 0),
        }
        logger.info("run %s completed in %d iterations", run_id, result.iterations)
        return receipt

    return _execute
