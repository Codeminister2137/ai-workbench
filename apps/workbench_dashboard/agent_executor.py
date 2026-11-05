"""AgentLoop-backed executor for drained runs (owner-approved full tools).

``build_executor`` adapts a run record to ``AgentLoop.run``: the client
comes from the dashboard provider config, the registry carries the full
coding toolset with staged (never direct) file writes, and the result
maps to a drain receipt with staged records attached. File changes land
in ``run["staged"]`` for the existing review/approve flow; shell and
Python tools run unconfined, which the owner explicitly approved per
run-level approval (no per-command gate). Delegation stays out: drain
runs default to ``restricted`` fan-out and there is no child runner in
this context yet.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_agent.loop import AgentIterationLimitExceeded, AgentLoop, AgentResult
from ai_agent.permissions import (
    ApprovalPolicyPreset,
    PermissionManager,
    PermissionPolicy,
)
from ai_agent.staged_edits import ProjectRoots, StagedEditError
from ai_agent.supervisor_drain import Executor
from ai_agent.tools.base import ToolContext, ToolRegistry
from ai_agent.tools.filesystem import ListDirTool, ReadFileTool
from ai_agent.tools.git import GitDiffTool, GitStatusTool
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
outside the workspace; verify with tests/checks when the task involves code;
finish with a short summary of what changed and what remains."""


def build_executor_registry() -> ToolRegistry:
    """Full coding toolset with staged writes and no direct file mutation."""
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
    return staged


def build_executor(
    config: DashboardConfig,
    roots: ProjectRoots,
    repo_root: Path,
    *,
    client_factory: Callable[[BackendConfig], Any] = create_chat_client,
    loop_factory: Callable[..., Any] = AgentLoop,
    max_iterations: int = 10,
) -> Executor:
    """Build a drain ``Executor`` running each approved run through AgentLoop."""
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
    registry = build_executor_registry()
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
        receipt: dict[str, Any] = {
            "status": "completed",
            "summary": summary[:MAX_SUMMARY_CHARS],
            "iterations": result.iterations,
            "tool_calls": [item.name for item in result.tool_results],
            "staged": _collect_staged(result),
        }
        logger.info("run %s completed in %d iterations", run_id, result.iterations)
        return receipt

    return _execute
