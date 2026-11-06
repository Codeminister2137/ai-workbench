"""Tool-using chat turns over the read-only inspection profile.

The messenger relay lets one chat turn actually inspect the workspace
(read/list/search files, git status) instead of answering from priors.
Writes, execution, delegation, and mail stay out of reach twice over:
the registry holds only the inspection profile, and the read-only
permission policy refuses anything else.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ai_provider.contracts import PrivacyClass
from ai_provider.errors import ProviderError

from ai_agent.contracts import ToolCategory
from ai_agent.loop import AgentIterationLimitExceeded, AgentLoop, ToolExecutionEvent
from ai_agent.permissions import PermissionManager, PermissionPolicy
from ai_agent.tool_profiles import INSPECTION_PROFILE, shared_tool_registry
from ai_agent.tools.base import BaseTool, ToolContext

if TYPE_CHECKING:
    from ai_provider.contracts import ChatClient


@dataclass(frozen=True, slots=True)
class MessengerResult:
    """Answer plus host-observed receipts from one relayed chat turn."""

    answer: str
    tool_receipts: tuple[str, ...]
    iterations: int
    hit_iteration_limit: bool = False


def run_messenger_turn(
    *,
    client: ChatClient,
    workspace_root: Path,
    history_text: str,
    prompt: str,
    system_prompt: str,
    max_iterations: int = 4,
    deadline: float | None = None,
    privacy_class: PrivacyClass = PrivacyClass.LOCAL_ONLY,
    extra_tools: tuple[BaseTool, ...] | None = None,
) -> MessengerResult:
    """Run one chat turn with inspection tools; never writes or executes.

    ``extra_tools`` extends the registry for the chat channel only. Every
    extra tool must be read-only (READ/SEARCH category) with a name outside
    the inspection profile; anything else is refused before any model call.
    When no extras are given the turn is exactly the inspection relay.
    """
    extras = tuple(extra_tools or ())
    for tool in extras:
        if tool.definition.category not in {ToolCategory.READ, ToolCategory.SEARCH}:
            raise ValueError(
                f"Messenger extra tool {tool.definition.name!r} must be read-only "
                "(READ/SEARCH category)"
            )
    extra_names = [tool.definition.name for tool in extras]
    if len(set(extra_names)) != len(extra_names):
        raise ValueError("Messenger extra tools must have unique names")
    if set(extra_names) & set(INSPECTION_PROFILE.tool_names):
        raise ValueError("Messenger extra tools must not shadow the inspection profile")
    registry = shared_tool_registry("inspection")
    for tool in extras:
        registry.register(tool)
    names = {tool.name for tool in registry.list_definitions()}
    expected = set(INSPECTION_PROFILE.tool_names) | set(extra_names)
    if names != expected:
        if extras:
            raise ValueError(
                "Messenger registry must hold exactly the inspection profile "
                "plus the chat-channel tools"
            )
        raise ValueError("Messenger registry must hold exactly the inspection profile")
    receipts: list[str] = []

    def on_event(event: ToolExecutionEvent) -> None:
        if event.type == "tool_completed":
            receipts.append(event.name if not event.is_error else f"{event.name}:error")

    loop = AgentLoop(
        client,
        registry,
        ToolContext(workspace_root),
        permissions=PermissionManager(policy=PermissionPolicy.read_only()),
        max_iterations=max_iterations,
        deadline=deadline,
        on_event=on_event,
    )
    history = history_text.strip()
    full_prompt = (
        prompt
        if not history
        else (
            "Conversation history (oldest first, possibly reduced):\n"
            f"{history}\n\nNew message:\n{prompt}"
        )
    )
    try:
        result = loop.run(full_prompt, system_prompt=system_prompt, privacy_class=privacy_class)
    except ProviderError as exc:
        if not isinstance(exc.raw_error, AgentIterationLimitExceeded):
            raise
        checked = ", ".join(receipts) if receipts else "nothing yet"
        return MessengerResult(
            answer=(
                "I ran out of steps before finishing. "
                f"What I checked: {checked}. "
                "Ask me to continue or narrow the question."
            ),
            tool_receipts=tuple(receipts),
            iterations=max_iterations,
            hit_iteration_limit=True,
        )
    return MessengerResult(
        answer=result.response.message.content,
        tool_receipts=tuple(receipts),
        iterations=result.iterations,
    )
