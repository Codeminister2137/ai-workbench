"""Child-agent runner backing the delegate_task tool.

``build_child_runner`` adapts a narrowed ``DelegationScope`` to a fresh
``AgentLoop``: the child inherits the scope's narrowed registry (as
granted wrappers), permissions, workspace, fan-out, and the shared
reply/tool budget, and runs the subtask to a result. Children never
re-delegate (``child_registry`` drops the delegate tool), so delegation
is exactly one level deep. Budget exhaustion, iteration limits, and
provider failures return error results instead of raising, so the
parent can adapt; a missing host scope refuses outright.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ai_provider import PrivacyClass, ProviderError

from ai_agent.contracts import ToolResult
from ai_agent.loop import AgentIterationLimitExceeded, AgentLoop
from ai_agent.tools.base import ToolContext
from ai_agent.tools.delegation import DelegatedTaskRunner

logger = logging.getLogger(__name__)

CHILD_SYSTEM_PROMPT = """You are a workbench subagent. Complete ONLY the subtask below inside
the workspace. Change project files ONLY through the stage_file tool;
verify with tests/checks when the task involves code; finish with a
short report of what you did, what you staged, and what remains."""


def build_child_runner(
    *,
    max_iterations: int = 10,
    privacy_class: PrivacyClass = PrivacyClass.LOCAL_ONLY,
    model: str | None = None,
    system_prompt: str = CHILD_SYSTEM_PROMPT,
    loop_factory: Callable[..., Any] = AgentLoop,
) -> DelegatedTaskRunner:
    """Build a ``DelegatedTaskRunner`` spawning one-level child loops."""
    if max_iterations < 1:
        raise ValueError("max_iterations must be at least 1")

    def _run(task: str, context: ToolContext) -> ToolResult:
        scope = context.delegation
        if scope is None:
            return ToolResult(
                name="delegate_task",
                output="Error: no host delegation scope for this execution.",
                is_error=True,
            )
        client = scope.approved_client
        if client is None:
            return ToolResult(
                name="delegate_task",
                output="Error: no approved client for child execution.",
                is_error=True,
            )
        try:
            loop = loop_factory(
                client,
                scope.child_registry(),
                context,
                permissions=scope.permissions,
                max_iterations=max_iterations,
                fanout_policy=scope.fanout,
            )
            result = loop.run(
                task, system_prompt=system_prompt, model=model, privacy_class=privacy_class
            )
        except AgentIterationLimitExceeded as exc:
            return ToolResult(
                name="delegate_task",
                output=f"Error: child iteration limit reached: {exc}",
                is_error=True,
            )
        except ProviderError as exc:
            return ToolResult(
                name="delegate_task",
                output=f"Error: child execution failed: {exc}",
                is_error=True,
            )
        summary = result.response.message.content or ""
        child_staged = [
            record
            for item in result.tool_results
            if isinstance((record := item.metadata.get("staged")), dict) and record.get("relpath")
        ]
        logger.info(
            "child task finished in %d iterations (%d tool calls, %d staged)",
            result.iterations,
            len(result.tool_results),
            len(child_staged),
        )
        return ToolResult(
            name="delegate_task",
            output=summary,
            metadata={
                "iterations": result.iterations,
                "tool_calls": [item.name for item in result.tool_results],
                "child_staged": child_staged,
            },
        )

    return _run
