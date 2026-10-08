"""Shared CLI settings for primary, repair, and fallback external execution."""

from __future__ import annotations

import argparse
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

from ai_orchestrator import AccessMethod, ExecutionTarget

from ai_provider.external_agents import (
    ExternalAgentConfig,
    external_agent_config_from_target,
)


@dataclass(frozen=True)
class ExternalExecutionSettings:
    """Capture CLI options once; derive each route's config without policy drift."""

    approval_policy: str
    persist_session: bool
    resume: str | None
    output_last_message: Path | None
    output_schema: Path | None
    web_search: bool
    images: tuple[Path, ...]
    mcp_tools: bool
    shared_tools: str | None
    task_id: str

    @classmethod
    def from_namespace(cls, args: argparse.Namespace) -> ExternalExecutionSettings:
        return cls(
            approval_policy=args.approval_policy,
            persist_session=args.codex_persist_session,
            resume=args.codex_resume,
            output_last_message=args.codex_output_last_message,
            output_schema=args.codex_output_schema,
            web_search=args.codex_search,
            images=tuple(args.codex_image),
            mcp_tools=args.codex_mcp_tools,
            shared_tools=getattr(args, "shared_tools", None),
            task_id=getattr(args, "shared_task_id", None) or uuid.uuid4().hex,
        )

    def build(
        self,
        target: ExecutionTarget,
        root: Path,
        *,
        timeout_seconds: float | None = None,
    ) -> ExternalAgentConfig:
        preset = "read_only" if self.shared_tools == "inspection" else self.approval_policy
        sandbox = {
            "read_only": "read-only",
            "interactive": "workspace-write",
            "workspace_write": "workspace-write",
            "trusted_local": "danger-full-access",
        }[preset]
        config = external_agent_config_from_target(
            target,
            repo_root=root,
            timeout_seconds=target.timeout_seconds if timeout_seconds is None else timeout_seconds,
            sandbox=sandbox,
            approval_policy=preset
            if target.access_method is not AccessMethod.CODEX_CLI or self.shared_tools == "coding"
            else "never",
            codex_persist_session=self.persist_session,
            codex_resume=self.resume,
            output_last_message_path=self.output_last_message,
            output_schema_path=self.output_schema,
            web_search=self.web_search,
            image_paths=self.images,
            codex_mcp_tools=self.mcp_tools,
            shared_tool_profile=self.shared_tools,
        )
        return replace(config, shared_task_id=self.task_id)
