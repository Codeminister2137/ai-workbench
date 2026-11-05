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
from collections.abc import Callable
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
from ai_agent.tools.search import FindFilesTool, GrepSearchTool
from ai_agent.tools.shell import RunCommandTool
from ai_agent.tools.staged import StageFileTool
from ai_provider import PrivacyClass, ProviderError
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.factory import create_chat_client
from dashboard_config import DashboardConfig

logger = logging.getLogger(__name__)

MAX_SUMMARY_CHARS = 2000

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


def build_executor(
    config: DashboardConfig,
    roots: ProjectRoots,
    repo_root: Path,
    *,
    client_factory: Callable[[BackendConfig], Any] = create_chat_client,
    loop_factory: Callable[..., Any] = AgentLoop,
    inbox_create: Callable[..., dict] | None = None,
    max_iterations: int = 10,
) -> Executor:
    """Build a drain ``Executor`` running each approved run through AgentLoop.

    ``inbox_create`` files owner tasks (dashboard inbox); without it, a run
    that files human tasks fails closed instead of dropping them.
    """
    try:
        provider = ProviderKind(config.provider)
    except ValueError:
        provider = None
    client = (
        client_factory(
            BackendConfig(provider=provider, model=config.model, base_url=config.base_url)
        )
        if provider is not None
        else None
    )
    privacy = (
        PrivacyClass.LOCAL_ONLY
        if provider is ProviderKind.OLLAMA
        else PrivacyClass.EXTERNAL_ALLOWED
    )
    runner = build_child_runner(
        max_iterations=max_iterations, privacy_class=privacy, loop_factory=loop_factory
    )
    permissions = PermissionManager(
        PermissionPolicy.from_approval_preset(ApprovalPolicyPreset.TRUSTED_LOCAL)
    )

    def _execute(run: dict) -> dict[str, Any]:
        run_id = str(run.get("id", "?"))
        if client is None:
            return {"status": "failed", "error": f"Unknown provider {config.provider!r}."}
        project_id = run.get("project_id")
        try:
            if isinstance(project_id, str) and project_id:
                workspace = roots.select(project_id)
            else:
                workspace = Path(repo_root)
        except StagedEditError as exc:
            return {"status": "failed", "error": f"Project scope refused: {exc}"}
        fanout = run.get("fanout_effective") or run.get("fanout_policy") or "restricted"
        context = ToolContext(workspace_root=workspace)
        try:
            registry = build_executor_registry(runner=runner, fanout=str(fanout))
            loop = loop_factory(
                client,
                registry,
                context,
                permissions=permissions,
                max_iterations=max_iterations,
                fanout_policy=fanout,
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
        receipt: dict[str, Any] = {
            "status": "completed",
            "summary": summary[:MAX_SUMMARY_CHARS],
            "iterations": result.iterations,
            "tool_calls": [item.name for item in result.tool_results],
            "staged": _collect_staged(result),
            "owner_tasks": filed,
        }
        logger.info("run %s completed in %d iterations", run_id, result.iterations)
        return receipt

    return _execute
