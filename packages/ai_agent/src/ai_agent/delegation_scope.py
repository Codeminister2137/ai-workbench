"""Host-bound delegation authority over existing tools and permissions."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path

from ai_provider import ChatClient, ProviderError, ProviderErrorCategory

from ai_agent.contracts import PermissionAction, ToolCall, ToolCategory, ToolResult
from ai_agent.permissions import PermissionManager, PermissionPolicy
from ai_agent.tools.base import BaseTool, ToolContext, ToolRegistry


@dataclass(slots=True)
class DelegationBudget:
    """One original reply allowance shared by parent and all descendants."""

    replies_remaining: int
    deadline: float | None = None
    held_reports: int = 0
    tools_remaining: int = 128
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def __post_init__(self):
        if type(self.replies_remaining) is not int or self.replies_remaining < 1:
            raise ValueError("A positive original reply allowance is required")
        if self.deadline is not None and not math.isfinite(self.deadline):
            raise ValueError("Delegation deadline must be finite")
        if (
            type(self.tools_remaining) is not int
            or self.tools_remaining < 1
            or self.held_reports != 0
        ):
            raise ValueError("A positive original tool allowance and no initial holds are required")

    def consume(self) -> None:
        with self._lock:
            if (
                self.deadline is not None and time.perf_counter() >= self.deadline
            ) or self.replies_remaining <= self.held_reports:
                raise ProviderError(
                    "Shared delegation reply allowance expired or exhausted; "
                    "earlier effects remain.",
                    category=ProviderErrorCategory.NON_RETRYABLE,
                )
            self.replies_remaining -= 1

    def consume_tool(self) -> None:
        with self._lock:
            if self.tools_remaining <= 0:
                raise ProviderError(
                    "Shared delegation tool allowance exhausted; earlier effects remain.",
                    category=ProviderErrorCategory.NON_RETRYABLE,
                )
            self.tools_remaining -= 1

    def tighten_deadline(self, deadline: float) -> None:
        if not math.isfinite(deadline):
            raise ValueError("Delegation deadline must be finite")
        with self._lock:
            self.deadline = min(self.deadline, deadline) if self.deadline is not None else deadline

    @contextmanager
    def child(self) -> Iterator[None]:
        with self._lock:
            if self.replies_remaining <= self.held_reports + 1:
                raise ValueError("No child reply allowance after reserving the parent report")
            self.held_reports += 1
        try:
            yield
        finally:
            with self._lock:
                self.held_reports -= 1


@dataclass(frozen=True, slots=True)
class DelegationScope:
    """Only host code supplies this context; model arguments can only narrow it."""

    registry: ToolRegistry
    permissions: PermissionManager
    workspace: Path
    budget: DelegationBudget
    is_active: Callable[[], bool] = lambda: True
    depth: int = 0
    max_depth: int = 2
    profile: str = "inherit"
    tools: frozenset[str] | None = None
    paths: tuple[Path, ...] | None = None
    commands: frozenset[str] | None = None
    inherited_profiles: tuple[str, ...] = ()
    instructions: str = ""
    objective: str = ""
    backends: frozenset[tuple[str, str, str | None]] | None = None
    environment: tuple[tuple[str, str], ...] = ()
    approved_client: ChatClient | None = field(default=None, repr=False, compare=False)
    request_timeout_seconds: float | None = None

    def active(self) -> bool:
        return self.is_active() and (
            self.budget.deadline is None or time.perf_counter() < self.budget.deadline
        )

    def narrow(
        self,
        *,
        profile: str = "inherit",
        tools: tuple[str, ...] | None = None,
        paths: tuple[str, ...] | None = None,
        commands: tuple[str, ...] | None = None,
    ) -> DelegationScope:
        if not self.active() or self.depth >= self.max_depth:
            raise ValueError("Delegation scope expired or maximum depth reached")
        if profile != "inherit":
            PermissionPolicy.from_approval_preset(profile)
        selected_tools = frozenset(tools) if tools is not None else self.tools
        if self.tools is not None and selected_tools is not None:
            selected_tools &= self.tools
        selected_paths = self.paths
        if paths is not None:
            selected_paths = tuple((self.workspace / path).resolve() for path in paths)
            if any(not path.is_relative_to(self.workspace.resolve()) for path in selected_paths):
                raise ValueError("Child path exceeds parent workspace")
            if self.paths is not None and any(
                not any(path == allowed or path.is_relative_to(allowed) for allowed in self.paths)
                for path in selected_paths
            ):
                raise ValueError("Child path exceeds inherited scope")
        selected_commands = frozenset(commands) if commands is not None else self.commands
        if self.commands is not None and selected_commands is not None:
            selected_commands &= self.commands
        return replace(
            self,
            is_active=self.active,
            depth=self.depth + 1,
            profile=profile,
            tools=selected_tools,
            paths=selected_paths,
            commands=selected_commands,
            inherited_profiles=(*self.inherited_profiles, self.profile),
        )

    def child_registry(self) -> ToolRegistry:
        return ToolRegistry(
            tuple(
                _GrantedTool(tool, self)
                for item in self.registry.list_definitions()
                if item.name != "delegate_task"
                and (self.tools is None or item.name in self.tools)
                and (tool := self.registry.get(item.name)) is not None
            )
        )

    def wrap(self, tool: BaseTool) -> BaseTool:
        return _GrantedTool(tool, self)


class _GrantedTool(BaseTool):
    def __init__(self, inner: BaseTool, scope: DelegationScope):
        self.inner, self.scope = inner, scope

    @property
    def definition(self):
        return self.inner.definition

    def execute(self, arguments, context: ToolContext) -> ToolResult:
        scope = self.scope
        refused = (
            not scope.active() or context.workspace_root.resolve() != scope.workspace.resolve()
        )
        if scope.paths is not None and self.definition.name != "delegate_task":
            if self.definition.category in {ToolCategory.SHELL, ToolCategory.CUSTOM}:
                refused |= scope.commands is None or arguments.get("command") not in scope.commands
            elif self.definition.name in {
                "read_file",
                "edit_file",
                "create_file",
                "list_directory",
                "list_dir",
                "grep_search",
                "find_files",
            }:
                path = context.resolve_path(arguments.get("path", "."))
                refused |= not any(
                    path == allowed or path.is_relative_to(allowed) for allowed in scope.paths
                )
            else:
                refused = True  # Unknown path semantics must not escape a narrow grant.
        if self.definition.category is ToolCategory.SHELL and scope.commands is not None:
            refused |= arguments.get("command") not in scope.commands
        if refused:
            return ToolResult(
                self.definition.name,
                "Error: child tool/workspace/path/command scope refused.",
                is_error=True,
            )
        actions = [
            PermissionPolicy.from_approval_preset(profile).action_for_category(
                self.definition.category
            )
            for profile in (*scope.inherited_profiles, scope.profile)
            if profile != "inherit"
        ]
        ranks = {PermissionAction.ALLOW: 0, PermissionAction.ASK_USER: 1, PermissionAction.DENY: 2}
        action = max(actions, key=ranks.__getitem__, default=PermissionAction.ALLOW)
        if action is PermissionAction.DENY:
            return ToolResult(
                self.definition.name, "Error: child permission profile refused.", is_error=True
            )
        call = ToolCall(self.definition.name, arguments)
        # Parent policy/callback is live, not a copied grant. A requested permissive
        # profile therefore cannot authorize an operation the parent would deny.
        if not scope.permissions.check_and_authorize(self.inner, call):
            return ToolResult(
                self.definition.name, "Error: parent permission refused.", is_error=True
            )
        if (
            action is PermissionAction.ASK_USER
            and scope.permissions.policy.action_for_category(self.definition.category)
            is PermissionAction.ALLOW
        ):
            restricted = PermissionManager(
                PermissionPolicy.interactive(), scope.permissions.approval_callback
            )
            if not restricted.check_and_authorize(self.inner, call):
                return ToolResult(
                    self.definition.name, "Error: narrowed child approval refused.", is_error=True
                )
        if not scope.active():
            return ToolResult(
                self.definition.name, "Error: child scope expired before effect.", is_error=True
            )
        return self.inner.run(
            call, replace(context, env=dict(scope.environment), inherit_environment=False)
        )
