"""CLI-owned shared process control and invocation-scoped MCP access."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from ai_agent.http_host import ForegroundMcpHost
from ai_agent.permissions import PermissionManager, PermissionPolicy
from ai_agent.processes import ProcessSupervisor, ProcessTool
from ai_agent.shared_approvals import TerminalApproval, scoped_registry
from ai_agent.tool_profiles import shared_tool_registry

if TYPE_CHECKING:
    from ai_provider.coding_sessions import CodingSession
    from ai_provider.external_agents import ExternalAgentConfig

ACTIVE_FOREGROUND: ContextVar[ForegroundTools | None] = ContextVar("foreground_tools", default=None)


class ForegroundTools:
    """Runtime ownership survives routes, but never the CLI's lifetime."""

    def __init__(self, workspace: Path, session: CodingSession | None = None):
        self.workspace = workspace.resolve()
        self.session = session
        self.supervisor = session.supervisor if session else ProcessSupervisor(workspace)
        self.host: ForegroundMcpHost | None = None
        self.task_id: str | None = session.session_id if session else None

    def registry(self):
        registry = shared_tool_registry("coding", self.workspace)
        for operation in ("start", "status", "stop"):
            registry.register(ProcessTool(self.supervisor, operation))
        return registry

    @contextmanager
    def invocation(
        self, config: ExternalAgentConfig, *, deadline: float | None = None
    ) -> Iterator[ExternalAgentConfig]:
        if config.cwd.resolve() != self.workspace:
            raise ValueError("Foreground MCP workspace changed")
        if self.task_id is None:
            self.task_id = config.shared_task_id
        if config.shared_task_id != self.task_id:
            raise ValueError("Foreground MCP task changed")
        if self.host is None:
            self.host = ForegroundMcpHost(self.workspace)
        host = self.host
        token = ""
        manager = PermissionManager(
            PermissionPolicy.from_approval_preset(config.approval_policy),
            TerminalApproval(
                config.shared_task_id,
                config.shared_run_id,
                self.workspace,
                lambda: host.active(token),
            )
            if config.shared_terminal_approvals
            else None,
        )
        registry = scoped_registry(
            self.registry(),
            manager,
            self.workspace,
            config.shared_task_id,
            config.shared_run_id,
            lambda: host.active(token),
        )
        if self.session:
            registry = self.session.observe_registry(
                registry,
                operation_prefix=f"shared:{config.shared_task_id}:{config.shared_run_id}:",
            )
        token = host.grant(registry, deadline=deadline)
        environment_name = "AI_PROJECTS_MCP_" + uuid.uuid4().hex.upper()
        try:
            yield replace(
                config,
                shared_host_url=host.url,
                shared_token_env=environment_name,
                shared_child_env={**os.environ, environment_name: token},
                shared_available_tools=tuple(d.name for d in registry.list_definitions()),
            )
        finally:
            host.revoke(token)

    def close(self) -> None:
        try:
            if self.host:
                self.host.close()
        finally:
            self.supervisor.close()
