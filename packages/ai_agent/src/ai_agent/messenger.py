"""Tool-using chat turns over the read-only inspection profile.

The messenger relay lets one chat turn actually inspect the workspace
(read/list/search files, git status) instead of answering from priors.
Writes, execution, delegation, and mail stay out of reach twice over:
the registry holds only the inspection profile, and the read-only
permission policy refuses anything else.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ai_provider.contracts import AIMessage, MessageRole, PrivacyClass
from ai_provider.errors import ProviderError

from ai_agent.contracts import ToolCategory, ToolResult
from ai_agent.loop import AgentIterationLimitExceeded, AgentLoop, ToolExecutionEvent
from ai_agent.permissions import PermissionManager, PermissionPolicy
from ai_agent.tool_profiles import INSPECTION_PROFILE, shared_tool_registry
from ai_agent.tools.base import BaseTool, ToolContext, ToolRegistry

if TYPE_CHECKING:
    from ai_provider.contracts import ChatClient


logger = logging.getLogger(__name__)

_SALVAGE_TURNS = 2
_SALVAGE_PROMPT = (
    "Write the final answer now using ONLY the tool observations above. "
    "Do not call more tools. If the evidence is insufficient, say exactly "
    "what is missing."
)


def _append_receipt(receipts: list[str], event: ToolExecutionEvent) -> None:
    if event.type == "tool_completed":
        receipts.append(event.name if not event.is_error else f"{event.name}:error")


def _salvage_composition(
    *,
    client: ChatClient,
    registry: ToolRegistry,
    workspace_root: Path,
    privacy_class: PrivacyClass,
    messages: tuple[AIMessage, ...],
    tool_results: tuple[ToolResult, ...],
    prior_iterations: int,
    receipts: list[str],
) -> tuple[str | None, int]:
    """One bounded resume asking for a composed answer; (text|None, turns used).

    Used when the main turn gathered evidence but ended without an answer
    (iteration limit or empty content). Never raises: failure returns None
    and the caller falls back to the honest receipts-only text. Salvage
    receipts join the main list only on success, so a failed salvage never
    rewrites what the main turn checked.
    """
    salvage_receipts: list[str] = []
    salvage_loop = AgentLoop(
        client,
        registry,
        ToolContext(workspace_root),
        permissions=PermissionManager(policy=PermissionPolicy.read_only()),
        max_iterations=_SALVAGE_TURNS,
        on_event=lambda event: _append_receipt(salvage_receipts, event),
    )
    try:
        resumed = salvage_loop.run(
            "",
            resume_messages=(*messages, AIMessage(MessageRole.USER, _SALVAGE_PROMPT)),
            privacy_class=privacy_class,
            prior_iterations=prior_iterations,
            prior_tool_results=tool_results,
        )
    except (ProviderError, AgentIterationLimitExceeded):
        return None, _SALVAGE_TURNS
    text = (resumed.response.message.content or "").strip()
    if text:
        receipts.extend(salvage_receipts)
        return text, resumed.iterations - prior_iterations
    return None, resumed.iterations - prior_iterations


# Adaptive Ollama context tiers (prompt chars -> num_ctx). Ollama's server
# default (4096) silently truncates long chat prompts, which confabulates
# the model; size the window to the prompt instead. Model capacity here is
# 131072, so even the top tier has wide headroom.
CHAT_CONTEXT_TIERS: tuple[tuple[int, int], ...] = (
    (8_000, 8_192),
    (32_000, 16_384),
    (128_000, 32_768),
)


def chat_context_tokens(prompt_chars: int) -> int:
    """Return the Ollama num_ctx tier covering ``prompt_chars``."""
    for limit, tokens in CHAT_CONTEXT_TIERS:
        if prompt_chars <= limit:
            return tokens
    return CHAT_CONTEXT_TIERS[-1][1]


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
    max_iterations: int = 25,
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
        _append_receipt(receipts, event)

    prompt_chars = len(history_text) + len(prompt) + len(system_prompt) + 200
    loop = AgentLoop(
        client,
        registry,
        ToolContext(workspace_root),
        permissions=PermissionManager(policy=PermissionPolicy.read_only()),
        max_iterations=max_iterations,
        deadline=deadline,
        on_event=on_event,
        request_metadata={"ollama_context_length": chat_context_tokens(prompt_chars)},
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
        if receipts and exc.partial_messages:
            salvaged, extra = _salvage_composition(
                client=client,
                registry=registry,
                workspace_root=workspace_root,
                privacy_class=privacy_class,
                messages=exc.partial_messages,
                tool_results=exc.tool_results,
                prior_iterations=max_iterations,
                receipts=receipts,
            )
            if salvaged:
                return MessengerResult(
                    answer=salvaged,
                    tool_receipts=tuple(receipts),
                    iterations=max_iterations + extra,
                    hit_iteration_limit=True,
                )
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
    content = result.response.message.content or ""
    iterations = result.iterations
    if not content.strip() and receipts:
        salvaged, extra = _salvage_composition(
            client=client,
            registry=registry,
            workspace_root=workspace_root,
            privacy_class=privacy_class,
            messages=result.messages,
            tool_results=result.tool_results,
            prior_iterations=result.iterations,
            receipts=receipts,
        )
        iterations += extra
        if salvaged:
            content = salvaged
    if not content.strip():
        checked = ", ".join(receipts) if receipts else "nothing"
        logger.info(
            "messenger empty final content; receipts=%s iterations=%d",
            checked,
            result.iterations,
        )
        if receipts:
            content = (
                f"I checked {checked} but couldn't compose a final answer. "
                "Ask me to continue or narrow the question."
            )
        else:
            content = (
                "I couldn't produce an answer for that turn. "
                "Please rephrase or narrow the question."
            )
    return MessengerResult(
        answer=content,
        tool_receipts=tuple(receipts),
        iterations=iterations,
    )
