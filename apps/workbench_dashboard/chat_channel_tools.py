"""Read-only lookup tools for the dashboard CHAT channel only.

Short chat exchanges use these for run status, inbox queue, and document
lookups instead of escalating to supervisor runs. Every tool is
``ToolCategory.READ`` (allowed under the messenger's read-only policy),
performs bounded local reads only (no network, no subprocess, no writes),
and fails closed: unknown ids, refusals, and unexpected errors become
error ``ToolResult``s that surface as ``<name>:error`` receipts in chat.

These tools register on the chat relay path (``DashboardChat`` passes them
as ``extra_tools`` to ``run_messenger_turn``) and never on the
write-capable run executor (``build_executor_registry``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_agent.contracts import ToolCategory, ToolDefinition, ToolParameter, ToolResult
from ai_agent.tools.base import BaseTool, ToolContext
from ai_agent.tools.credential_paths import is_credential_path
from dashboard_stores import MAX_OPEN_TASKS, DashboardStores, StoreError
from document_library import DocumentLibrary

CHAT_CHANNEL_TOOL_NAMES = ("get_run_status", "list_pending_inbox", "read_dashboard_doc")

INBOX_DEFAULT_LIMIT = 10
INBOX_MAX_LIMIT = 20
INBOX_TITLE_CHARS = 120
RUN_BODY_EXCERPT_CHARS = 300
DOC_BODY_CHARS = 4000


def _truncate(text: str, limit: int) -> str:
    """Cap text at limit characters with an ellipsis marker."""
    return text if len(text) <= limit else text[:limit] + "…"


class GetRunStatusTool(BaseTool):
    """Look up one agent run's status by id (read-only)."""

    def __init__(self, stores: DashboardStores) -> None:
        self._stores = stores

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_run_status",
            description=(
                "Look up one agent run by id: title, status, fan-out policy, "
                "linked inbox task, and a short body excerpt. Read-only."
            ),
            category=ToolCategory.READ,
            parameters=(
                ToolParameter(
                    name="run_id",
                    type_name="string",
                    description="Agent run id.",
                    required=True,
                ),
            ),
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        del context
        run_id = arguments.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            return ToolResult(
                name="get_run_status",
                output="Error: 'run_id' parameter is required.",
                is_error=True,
            )
        try:
            record = self._stores.runs.get(run_id.strip())
        except StoreError as exc:
            return ToolResult(
                name="get_run_status",
                output=f"Error: invalid run id: {exc}",
                is_error=True,
            )
        if record is None:
            return ToolResult(
                name="get_run_status",
                output=f"Error: unknown run id {run_id.strip()!r}.",
                is_error=True,
            )
        title = record.get("title") or "(untitled)"
        status = record.get("status") or "unknown"
        fanout = record.get("fanout_effective") or record.get("fanout_policy") or "unknown"
        inbox = record.get("inbox_id") or "-"
        plan = record.get("plan_id") or "-"
        updated = record.get("updated_at_utc") or record.get("created_at_utc") or "?"
        body = record.get("body")
        excerpt = _truncate(str(body).strip(), RUN_BODY_EXCERPT_CHARS) if body else "-"
        return ToolResult(
            name="get_run_status",
            output=(
                f"run {record.get('id', run_id.strip())}: {title}\n"
                f"status: {status}\n"
                f"fanout: {fanout}\n"
                f"inbox: {inbox}\n"
                f"plan: {plan}\n"
                f"updated: {updated}\n"
                f"excerpt: {excerpt}"
            ),
            metadata={"run_id": record.get("id", run_id.strip()), "status": status},
        )


class ListPendingInboxTool(BaseTool):
    """List open inbox items as id + summary lines (read-only, no bodies)."""

    def __init__(self, stores: DashboardStores) -> None:
        self._stores = stores

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="list_pending_inbox",
            description=(
                "List open inbox items awaiting the owner: id, type, and title "
                "only (bodies and answers stay out so no secrets leak). Read-only."
            ),
            category=ToolCategory.READ,
            parameters=(
                ToolParameter(
                    name="limit",
                    type_name="integer",
                    description="Max items to list (default 10, at most 20).",
                    required=False,
                    default=INBOX_DEFAULT_LIMIT,
                ),
            ),
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        del context
        limit = arguments.get("limit", INBOX_DEFAULT_LIMIT)
        if not isinstance(limit, int) or isinstance(limit, bool):
            return ToolResult(
                name="list_pending_inbox",
                output="Error: 'limit' must be an integer.",
                is_error=True,
            )
        limit = min(max(limit, 1), INBOX_MAX_LIMIT)
        try:
            items, _total = self._stores.inbox.list(limit=MAX_OPEN_TASKS + 1)
        except StoreError as exc:
            return ToolResult(
                name="list_pending_inbox",
                output=f"Error: inbox unavailable: {exc}",
                is_error=True,
            )
        pending = [item for item in items if item.get("status") == "open"]
        lines = [f"{len(pending)} open inbox items (showing {min(len(pending), limit)}):"]
        for item in pending[:limit]:
            item_id = item.get("id", "?")
            item_type = item.get("type", "?")
            title = _truncate(str(item.get("title") or "(untitled)"), INBOX_TITLE_CHARS)
            lines.append(f"- {item_id} [{item_type}] {title}")
        return ToolResult(
            name="list_pending_inbox",
            output="\n".join(lines),
            metadata={"open_count": len(pending)},
        )


class ReadDashboardDocTool(BaseTool):
    """Read one dashboard library document with a chat-sized cap (read-only)."""

    def __init__(self, library: DocumentLibrary) -> None:
        self._library = library

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_dashboard_doc",
            description=(
                "Read one dashboard library document by id ('{root}/{path}') or "
                "unique filename. Output is capped for chat; credential files "
                "and non-renderable files are refused. Read-only."
            ),
            category=ToolCategory.READ,
            parameters=(
                ToolParameter(
                    name="name",
                    type_name="string",
                    description="Document id or unique filename.",
                    required=True,
                ),
            ),
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        del context
        name = arguments.get("name")
        if not isinstance(name, str) or not name.strip():
            return ToolResult(
                name="read_dashboard_doc",
                output="Error: 'name' parameter is required.",
                is_error=True,
            )
        name = name.strip()
        if is_credential_path(Path(name)):
            return ToolResult(
                name="read_dashboard_doc",
                output="Credential-file read refused; document content was not read.",
                is_error=True,
            )
        doc_id = self._resolve(name)
        if isinstance(doc_id, ToolResult):
            return doc_id
        try:
            body, _truncated = self._library.read_text(doc_id)
        except ValueError as exc:
            return ToolResult(
                name="read_dashboard_doc",
                output=f"Error: cannot read document: {exc}",
                is_error=True,
            )
        except OSError as exc:
            return ToolResult(
                name="read_dashboard_doc",
                output=f"Error: cannot read document {doc_id!r}: {exc}",
                is_error=True,
            )
        if len(body) > DOC_BODY_CHARS:
            body = body[:DOC_BODY_CHARS] + f"\n…(truncated to {DOC_BODY_CHARS} chars)"
        return ToolResult(
            name="read_dashboard_doc",
            output=f"doc {doc_id}:\n{body}",
            metadata={"doc_id": doc_id},
        )

    def _resolve(self, name: str) -> str | ToolResult:
        """Resolve an id or unique filename; failures are error results."""
        try:
            entry = self._library.get(name)
        except (KeyError, ValueError):
            entry = None
        if entry is not None:
            if is_credential_path(Path(entry.relpath)):
                return ToolResult(
                    name="read_dashboard_doc",
                    output="Credential-file read refused; document content was not read.",
                    is_error=True,
                )
            return entry.id
        if "/" in name or "\\" in name:
            return ToolResult(
                name="read_dashboard_doc",
                output=f"Error: unknown document {name!r}.",
                is_error=True,
            )
        matches = [
            item["id"]
            for item in self._library.list_documents()
            if Path(item["relpath"]).name == name or item["relpath"] == name
        ]
        if len(matches) == 1:
            if is_credential_path(Path(matches[0])):
                return ToolResult(
                    name="read_dashboard_doc",
                    output="Credential-file read refused; document content was not read.",
                    is_error=True,
                )
            return matches[0]
        if not matches:
            return ToolResult(
                name="read_dashboard_doc",
                output=f"Error: unknown document {name!r}.",
                is_error=True,
            )
        shown = ", ".join(sorted(matches)[:5])
        return ToolResult(
            name="read_dashboard_doc",
            output=f"Error: {name!r} matches several documents; be specific: {shown}.",
            is_error=True,
        )


def build_chat_channel_tools(
    stores: DashboardStores, library: DocumentLibrary
) -> tuple[BaseTool, ...]:
    """Build the chat-channel lookup tools (read-only, bounded).

    The caller owns ``stores``/``library`` lifetimes; tools only read through
    them. Register the result on the chat relay path only, never on the
    write-capable run executor.
    """
    tools: tuple[BaseTool, ...] = (
        GetRunStatusTool(stores),
        ListPendingInboxTool(stores),
        ReadDashboardDocTool(library),
    )
    assert tuple(tool.definition.name for tool in tools) == CHAT_CHANNEL_TOOL_NAMES
    return tools
