"""Owner-task tool: let the agent file human tasks to the owner inbox.

``OwnerTaskTool`` carries a human task (title + instructions) back in the
tool result metadata; it never touches the inbox store itself. The
dashboard executor collects these records and files them as ``task``
inbox items, so provider-layer code stays free of dashboard stores.
The run completes with its tasks filed; the owner answers in the inbox
and a follow-up run continues (pause/resume with answers is a later
integration).
"""

from __future__ import annotations

from typing import Any

from ai_agent.contracts import ToolCategory, ToolDefinition, ToolParameter, ToolResult
from ai_agent.tools.base import BaseTool, ToolContext

MAX_TITLE_CHARS = 200
MAX_BODY_CHARS = 8000


class OwnerTaskTool(BaseTool):
    """File a human task for the owner (manual test, secret, decision)."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="request_owner_task",
            description=(
                "Ask the human owner to do something only they can do: a "
                "manual test with steps, providing a secret/key, an access "
                "grant, or a decision. NEVER ask for secrets IN the task "
                "text — tell them where to put the secret (.env, User env). "
                "The run completes with the task filed; the owner answers "
                "in the inbox."
            ),
            category=ToolCategory.CUSTOM,
            parameters=(
                ToolParameter(
                    name="title",
                    type_name="string",
                    description="Short task title for the owner.",
                    required=True,
                ),
                ToolParameter(
                    name="body",
                    type_name="string",
                    description="Full instructions: what, how, and what done looks like.",
                    required=True,
                ),
            ),
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        title = arguments.get("title")
        body = arguments.get("body")
        if not isinstance(title, str) or not title.strip() or len(title) > MAX_TITLE_CHARS:
            return ToolResult(
                name="request_owner_task",
                output="Error: 'title' requires 1-200 characters.",
                is_error=True,
            )
        if not isinstance(body, str) or not body.strip() or len(body) > MAX_BODY_CHARS:
            return ToolResult(
                name="request_owner_task",
                output="Error: 'body' requires 1-8000 characters.",
                is_error=True,
            )
        return ToolResult(
            name="request_owner_task",
            output=f"Owner task filed: {title.strip()}",
            metadata={"owner_task": {"title": title.strip(), "body": body.strip()}},
        )
