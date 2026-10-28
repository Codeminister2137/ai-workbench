"""Bridge Workbench terminal approvals to the Remote AI Operator task API.

The bridge carries only digests and a human-readable description; actual source,
diffs and commands stay inside the Workbench. The operator phone/web UI shows the
description and records the owner's approve/reject/cancel decision, then the
Workbench applies the already-prepared tool effect only after receiving approval.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from ai_agent.contracts import ToolCall, ToolCategory


class OperatorBridgeError(Exception):
    """The operator bridge could not complete an approval round trip."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _summarize_arguments(arguments: dict, max_length: int = 400) -> str:
    """Return a compact, phone-friendly summary of tool arguments.

    Long string values are truncated so the description stays readable and does
    not expose large diffs or file contents through the operator.
    """

    summary: dict[str, object] = {}
    for key, value in arguments.items():
        if isinstance(value, str) and len(value) > max_length:
            value = value[:max_length] + "…"
        summary[key] = value
    return json.dumps(summary, ensure_ascii=True, sort_keys=True)


def _describe(approval_call: ToolCall, category: ToolCategory, workspace: Path) -> str:
    args_summary = _summarize_arguments(approval_call.arguments)
    return (
        f"[{category.value}] {approval_call.name}\n"
        f"workspace: {workspace}\n"
        f"arguments: {args_summary}"
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
        client_factory: Callable[..., httpx.Client] = httpx.Client,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        self.workspace = Path(workspace).resolve()
        self.poll_interval = poll_interval_seconds
        self.timeout = timeout_seconds
        self._client_factory = client_factory

    def __call__(self, approval_call: ToolCall, category: ToolCategory) -> bool:
        description = _describe(approval_call, category, self.workspace)
        operation_json = json.dumps(
            {"tool": approval_call.name, "arguments": approval_call.arguments},
            ensure_ascii=True,
            sort_keys=True,
        )
        candidate_digest = _sha256(operation_json)
        base_digest = _sha256(str(self.workspace))
        evidence_digest = _sha256(f"{category.value}:{approval_call.name}")

        try:
            with self._client_factory(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/api/external-actions",
                    headers=self.headers,
                    json={
                        "description": description,
                        "candidate_digest": candidate_digest,
                        "base_digest": base_digest,
                        "evidence_digest": evidence_digest,
                    },
                )
                response.raise_for_status()
                action = response.json()
        except httpx.HTTPError as exc:
            raise OperatorBridgeError(f"Failed to submit external action: {exc}") from exc

        return self._wait_for_resolution(client, action["id"])

    def _wait_for_resolution(self, client: httpx.Client, action_id: str) -> bool:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                response = client.get(
                    f"{self.base_url}/api/external-actions/{action_id}",
                    headers=self.headers,
                )
                response.raise_for_status()
                status = response.json()["status"]
            except httpx.HTTPError as exc:
                raise OperatorBridgeError(f"Failed to poll external action: {exc}") from exc

            if status == "approved":
                return True
            if status in {"rejected", "cancelled", "expired"}:
                return False
            if status != "submitted":
                raise OperatorBridgeError(f"Unexpected external action status: {status}")
            time.sleep(self.poll_interval)

        try:
            client.post(
                f"{self.base_url}/api/external-actions/{action_id}/cancel",
                headers=self.headers,
            )
        except httpx.HTTPError:
            pass
        raise OperatorBridgeError("External action approval timed out")
