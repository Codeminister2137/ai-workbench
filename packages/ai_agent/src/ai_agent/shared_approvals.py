"""Per-call shared permissions; terminal input is separate from MCP transport."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from ai_agent.contracts import ToolCall, ToolCategory, ToolDefinition, ToolResult
from ai_agent.delegation_scope import DelegationBudget, DelegationScope, FanoutPolicy
from ai_agent.permissions import PermissionManager
from ai_agent.tools.base import BaseTool, ToolContext, ToolRegistry

ApprovalOutcome = Literal["approved", "denied", "expired", "evidence_changed"]


class TerminalApproval:
    """Ask once for this exact operation; never read model-controlled stdio.

    With ``timeout_seconds`` the prompt carries an expiry window: a "yes"
    arriving after the window is refused as ``expired``. With
    ``evidence_reader`` the approval is bound to freshly inspected evidence:
    the fingerprint is snapshotted before prompting and re-verified at
    approve time, and any change fails closed as ``evidence_changed``.
    :meth:`revalidate` opens one fresh window after either outcome.
    """

    def __init__(
        self,
        task_id: str,
        run_id: str,
        workspace: Path,
        is_active: Callable[[], bool] | None = None,
        approval_reader: Callable[[str, Callable[[], bool]], str] | None = None,
        *,
        timeout_seconds: float | None = None,
        evidence_reader: Callable[[ToolCall], str] | None = None,
    ):
        if timeout_seconds is not None and (
            isinstance(timeout_seconds, bool)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("Approval timeout must be finite positive seconds")
        self.task_id, self.run_id, self.workspace = task_id, run_id, workspace.resolve()
        self.is_active = is_active
        self.approval_reader = approval_reader
        self.timeout_seconds = timeout_seconds
        self.evidence_reader = evidence_reader
        self.last_outcome: ApprovalOutcome | None = None

    def __call__(self, call: ToolCall, category: ToolCategory) -> bool:
        operation = json.dumps({"tool": call.name, "arguments": call.arguments}, ensure_ascii=True)
        if len(operation) > 64000:
            self.last_outcome = "denied"
            return False  # Never shorten the operation the human is being asked to approve.
        snapshot: str | None = None
        if self.evidence_reader is not None:
            try:
                snapshot = self.evidence_reader(call)
            except Exception:  # noqa: BLE001 - evidence failure fails closed
                self.last_outcome = "evidence_changed"
                return False
            if not isinstance(snapshot, str):
                self.last_outcome = "evidence_changed"
                return False
        start = time.monotonic()
        deadline = None if self.timeout_seconds is None else start + self.timeout_seconds
        if not self._ask_once(call, category, operation, deadline):
            self.last_outcome = "denied"
            return False
        if deadline is not None and time.monotonic() >= deadline:
            self.last_outcome = "expired"
            return False
        if self.evidence_reader is not None:
            try:
                current = self.evidence_reader(call)
            except Exception:  # noqa: BLE001 - evidence failure fails closed
                self.last_outcome = "evidence_changed"
                return False
            if (
                snapshot is None
                or not isinstance(current, str)
                or not hmac.compare_digest(snapshot.encode("utf-8"), current.encode("utf-8"))
            ):
                self.last_outcome = "evidence_changed"
                return False
        self.last_outcome = "approved"
        return True

    def revalidate(self, call: ToolCall, category: ToolCategory) -> bool:
        """Open one fresh approval window after expiry or an evidence change.

        Re-snapshots evidence and re-prompts once under a new window. The
        permission manager calls ``__call__`` once per tool call; the host
        invokes this only to recover an ``expired`` or ``evidence_changed``
        outcome instead of failing the run.
        """
        return self(call, category)

    def _ask_once(
        self, call: ToolCall, category: ToolCategory, operation: str, deadline: float | None
    ) -> bool:
        if self.approval_reader is not None:
            prompt = (
                json.dumps(
                    {
                        "task": self.task_id,
                        "run": self.run_id,
                        "workspace": str(self.workspace),
                        "category": category.value,
                    }
                )
                + "\n"
                + operation
                + "\nApprove this operation once?"
            )
            return self.approval_reader(prompt, self.is_active or (lambda: True)) == "yes"
        reader_name, writer_name = (
            ("CONIN$", "CONOUT$") if os.name == "nt" else ("/dev/tty", "/dev/tty")
        )
        try:
            with (
                open(reader_name, encoding="utf-8") as reader,
                open(writer_name, "w", encoding="utf-8") as writer,
            ):
                if not reader.isatty() or not writer.isatty():
                    return False
                if self.is_active is not None:
                    self._discard_pending_input(reader)
                writer.write(
                    json.dumps(
                        {
                            "task": self.task_id,
                            "run": self.run_id,
                            "workspace": str(self.workspace),
                            "category": category.value,
                        }
                    )
                    + "\n"
                    + operation
                    + "\nApprove this operation once? [yes/NO] "
                )
                writer.flush()
                if self.is_active is None:
                    return reader.readline().strip().lower() == "yes"
                return self._scoped_answer(reader, writer, deadline)
        except (OSError, EOFError, KeyboardInterrupt):
            return False

    def _scoped_answer(self, reader, writer, deadline: float | None = None) -> bool:
        """Poll the controlling terminal so revoked HTTP scopes can shut down."""
        answer = ""
        while self.is_active and self.is_active():
            if deadline is not None and time.monotonic() >= deadline:
                return False
            if os.name == "nt":
                import msvcrt

                if not msvcrt.kbhit():
                    time.sleep(0.05)
                    continue
                character = msvcrt.getwch()
                if character in {"\0", "\xe0"}:
                    msvcrt.getwch()
                    continue
                if character in {"\r", "\n"}:
                    writer.write("\n")
                    writer.flush()
                    return answer.strip().lower() == "yes"
                if character == "\x03":
                    return False
                if character == "\b":
                    if answer:
                        answer = answer[:-1]
                        writer.write("\b \b")
                elif character.isprintable() and len(answer) < 16:
                    answer += character
                    writer.write(character)
                writer.flush()
            else:
                import select

                if select.select([reader], [], [], 0.05)[0]:
                    return reader.readline().strip().lower() == "yes"
        return False

    @staticmethod
    def _discard_pending_input(reader) -> None:
        """A queued answer from an expired prompt cannot approve the next operation."""
        if os.name == "nt":
            import msvcrt

            while msvcrt.kbhit():
                msvcrt.getwch()
        else:
            import termios

            termios.tcflush(reader.fileno(), termios.TCIFLUSH)


class ScopedTool(BaseTool):
    """Retain the original tool boundary, with operation-scoped observed receipts."""

    def __init__(
        self,
        tool: BaseTool,
        permissions: PermissionManager,
        workspace: Path,
        task_id: str,
        run_id: str,
        is_active: Callable[[], bool] | None = None,
        delegation: DelegationScope | None = None,
    ):
        self.tool, self.permissions = tool, permissions
        self.workspace, self.task_id, self.run_id = workspace.resolve(), task_id, run_id
        self.is_active = is_active or (lambda: True)
        self.delegation = delegation

    @property
    def definition(self) -> ToolDefinition:
        return self.tool.definition

    def approval_call(self, call: ToolCall) -> ToolCall | None:
        return self.tool.approval_call(call)

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        if context.workspace_root.resolve() != self.workspace:
            raise ValueError("Shared approval workspace changed")
        call = ToolCall(self.definition.name, arguments)
        if (
            self.definition.name == "delegate_task"
            and context.delegation is None
            and self.delegation is not None
        ):
            context = replace(context, delegation=self.delegation)
        authorized = self.is_active() and self.permissions.check_and_authorize(self.tool, call)
        # The owner may exit while the human is considering the request.
        authorized = authorized and self.is_active()
        result = (
            self.tool.run(call, context)
            if authorized
            else ToolResult(
                self.definition.name,
                "Permission denied: no scoped approval for this operation",
                is_error=True,
            )
        )
        receipt = {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "workspace": str(self.workspace),
            "operation": self.definition.name,
            "category": self.definition.category.value,
            "authorized": authorized,
            "is_error": result.is_error,
            "arguments_sha256": hashlib.sha256(
                json.dumps(arguments, sort_keys=True).encode()
            ).hexdigest(),
            "output_sha256": hashlib.sha256(result.output.encode()).hexdigest(),
            "observed_at_utc": datetime.now(UTC).isoformat(),
        }
        return replace(result, metadata={**result.metadata, "shared_receipt": receipt})


def scoped_registry(
    registry: ToolRegistry,
    permissions: PermissionManager,
    workspace: Path,
    task_id: str,
    run_id: str,
    is_active: Callable[[], bool] | None = None,
    *,
    delegation_budget: DelegationBudget | None = None,
    delegation_deadline: float | None = None,
    fanout: FanoutPolicy | str = FanoutPolicy.ALLOWED,
) -> ToolRegistry:
    if not task_id or not run_id:
        raise ValueError("Shared coding requires task and run identity")
    if delegation_budget is not None and delegation_deadline is not None:
        delegation_budget.tighten_deadline(delegation_deadline)
    delegation = DelegationScope(
        registry,
        permissions,
        workspace.resolve(),
        delegation_budget or DelegationBudget(8, delegation_deadline),
        is_active or (lambda: True),
        fanout=FanoutPolicy.coerce(fanout),
    )
    return ToolRegistry(
        tuple(
            ScopedTool(tool, permissions, workspace, task_id, run_id, is_active, delegation)
            for definition in registry.list_definitions()
            if (tool := registry.get(definition.name))
        )
    )
