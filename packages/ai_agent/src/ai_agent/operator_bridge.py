"""Bridge Workbench terminal approvals to the Remote AI Operator task API.

The bridge sends action digests and metadata: tool/category, a workspace
fingerprint, and argument types/sizes. Descriptions omit argument names/values
and the workspace path. The operator UI records approve/reject/cancel; Workbench
applies the prepared tool effect only after approval. Metadata does not let the
owner inspect the exact command or diff; review those through an authorized
channel before approving the digest-bound action.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from ai_agent.approval_file_state import capture_file_state
from ai_agent.contracts import ToolCall, ToolCategory


class OperatorBridgeError(Exception):
    """The operator bridge could not complete an approval round trip."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _summarize_arguments(arguments: dict) -> str:
    """Describe top-level JSON types/sizes without names or nested values."""
    items: list[dict[str, object]] = []
    for value in arguments.values():
        if value is None:
            item: dict[str, object] = {"type": "null"}
        elif isinstance(value, bool):
            item = {"type": "boolean"}
        elif isinstance(value, (int, float)):
            item = {"type": "number"}
        elif isinstance(value, str):
            item = {"type": "string", "characters": len(value)}
        elif isinstance(value, (list, tuple)):
            item = {"type": "array", "items": len(value)}
        elif isinstance(value, dict):
            item = {"type": "object", "members": len(value)}
        else:
            item = {"type": "unsupported"}
        items.append(item)
    return json.dumps({"count": len(items), "items": items}, sort_keys=True)


def _describe(approval_call: ToolCall, category: ToolCategory, workspace: Path) -> str:
    args_summary = _summarize_arguments(approval_call.arguments)
    return (
        f"[{category.value}] {approval_call.name}\n"
        f"workspace_sha256: {_sha256(str(workspace.resolve()))}\n"
        f"arguments_metadata: {args_summary}"
    )


class OperatorApprovalBridge:
    """PermissionManager callback that blocks on operator-mediated approval."""

    def __init__(
        self,
        base_url: str,
        access_token: str,
        workspace: Path,
        *,
        poll_interval_seconds: float = 1.0,
        timeout_seconds: float = 300.0,
        deadline: float | None = None,
        client_factory: Callable[..., Any] = httpx.Client,
    ) -> None:
        if any(
            isinstance(value, bool) or not math.isfinite(value) or value <= 0
            for value in (poll_interval_seconds, timeout_seconds)
        ):
            raise ValueError("Approval polling and timeout must be finite positive seconds")
        if deadline is not None and (isinstance(deadline, bool) or not math.isfinite(deadline)):
            raise ValueError("Approval deadline must be finite")
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        self.workspace = Path(workspace).resolve()
        self.poll_interval = poll_interval_seconds
        self.timeout = timeout_seconds
        self.deadline = deadline
        self._client_factory = client_factory

    def __call__(self, approval_call: ToolCall, category: ToolCategory) -> bool:
        deadline = time.perf_counter() + self.timeout
        if self.deadline is not None:
            deadline = min(deadline, self.deadline)

        def remaining() -> float:
            seconds = deadline - time.perf_counter()
            if seconds <= 0:
                raise OperatorBridgeError("External action approval timed out")
            return seconds

        remaining()
        approval_paths = approval_call.approval_paths

        def file_state() -> str:
            if approval_paths is None:
                raise OperatorBridgeError("Write tool has not declared file approval targets")
            try:
                return capture_file_state(self.workspace, approval_paths, remaining)
            except (OSError, ValueError) as exc:
                raise OperatorBridgeError("File approval state unavailable or unsafe") from exc

        description = _describe(approval_call, category, self.workspace)
        operation_json = json.dumps(
            {"tool": approval_call.name, "arguments": approval_call.arguments},
            ensure_ascii=True,
            sort_keys=True,
        )
        candidate_digest = _sha256(operation_json)
        base_digest = (
            file_state() if category is ToolCategory.WRITE else _sha256(str(self.workspace))
        )
        evidence_digest = _sha256(f"{category.value}:{approval_call.name}")
        binding = {
            "candidate_digest": candidate_digest,
            "base_digest": base_digest,
            "evidence_digest": evidence_digest,
        }

        try:
            with self._client_factory(timeout=remaining()) as client:
                response = client.post(
                    f"{self.base_url}/api/external-actions",
                    headers=self.headers,
                    json={
                        "description": description,
                        **binding,
                    },
                    timeout=remaining(),
                )
                response.raise_for_status()
                action = response.json()
                if not isinstance(action, dict):
                    raise OperatorBridgeError("Invalid external action response")
                action_id = action.get("id")
                if (
                    not isinstance(action_id, str)
                    or len(action_id) != 32
                    or any(character not in "0123456789abcdef" for character in action_id)
                ):
                    raise OperatorBridgeError("Invalid external action identifier")
                # The public submission acknowledgement omits digests. Verify
                # any echoed fields; every subsequent full action must match.
                self._verify_binding(
                    action, {name: value for name, value in binding.items() if name in action}
                )
                try:
                    remaining()
                    approved = self._wait_for_resolution(
                        client, {"id": action_id, **binding}, remaining
                    )
                    if (
                        approved
                        and _sha256(
                            json.dumps(
                                {"tool": approval_call.name, "arguments": approval_call.arguments},
                                ensure_ascii=True,
                                sort_keys=True,
                            )
                        )
                        != candidate_digest
                    ):
                        raise OperatorBridgeError(
                            "Pending tool action changed while awaiting approval"
                        )
                    if approved and category is ToolCategory.WRITE and file_state() != base_digest:
                        raise OperatorBridgeError(
                            "File state changed while awaiting approval; fresh approval required"
                        )
                    remaining()
                    return approved
                except OperatorBridgeError:
                    if time.perf_counter() >= deadline:
                        # Cleanup cannot authorize the action. Preserve the existing
                        # best-effort cancellation with a separate one-second cap.
                        try:
                            client.post(
                                f"{self.base_url}/api/external-actions/{action_id}/cancel",
                                headers=self.headers,
                                timeout=min(1.0, self.timeout),
                            )
                        except httpx.HTTPError:
                            pass
                    raise
        except httpx.HTTPError as exc:
            raise OperatorBridgeError(f"Failed to submit external action: {exc}") from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise OperatorBridgeError("Invalid external action response") from exc

    @staticmethod
    def _verify_binding(action: dict, binding: dict) -> None:
        if any(action.get(name) != value for name, value in binding.items()):
            raise OperatorBridgeError("External action response does not match the pending action")

    def _wait_for_resolution(
        self, client: Any, binding: dict, remaining: Callable[[], float]
    ) -> bool:
        action_id = binding["id"]
        while True:
            try:
                response = client.get(
                    f"{self.base_url}/api/external-actions/{action_id}",
                    headers=self.headers,
                    timeout=remaining(),
                )
                response.raise_for_status()
                remaining()
                action = response.json()
                if not isinstance(action, dict):
                    raise OperatorBridgeError("Invalid external action response")
                self._verify_binding(action, binding)
                status = action["status"]
            except httpx.HTTPError as exc:
                raise OperatorBridgeError(f"Failed to poll external action: {exc}") from exc

            if status == "approved":
                return True
            if status in {"rejected", "cancelled", "expired"}:
                return False
            if status != "submitted":
                raise OperatorBridgeError(f"Unexpected external action status: {status}")
            time.sleep(min(self.poll_interval, remaining()))
