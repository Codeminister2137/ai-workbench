"""Persistent conversational coding over injected, permission-scoped turn execution."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai_provider.chat_transcripts import (
    ChatMessageRecord,
    ChatSessionRecord,
    SQLiteChatTranscriptStore,
)

from ai_agent.coding_chat_input import StagedCodingInput

DEFAULT_CODING_CHAT_HISTORY_BUDGET_CHARS = 64_000


class CodingChatInputError(ValueError):
    """A turn refused before execution, safe to correct at the next prompt."""


@dataclass(frozen=True, slots=True)
class CodingTurnRequest:
    """A new user turn plus historical conversation, not cached repository state."""

    text: str
    history: str
    message_id: str


@dataclass(frozen=True, slots=True)
class CodingTurnResult:
    """Final model report and host-observed outcome from one existing coding route."""

    returncode: int
    response_text: str | None
    execution_status: str
    failure_reason: str | None = None


class CodingChatController:
    """Own conversation continuity while the executor owns effects and approvals."""

    def __init__(
        self,
        store: SQLiteChatTranscriptStore,
        session_id: str,
        workspace: Path,
        privacy_class: str,
        *,
        history_budget_chars: int = DEFAULT_CODING_CHAT_HISTORY_BUDGET_CHARS,
    ) -> None:
        if history_budget_chars < 0:
            raise ValueError("Coding chat history budget must be zero or greater")
        session = store.get_session(session_id)
        if session is None:
            raise ValueError("Coding conversation does not exist")
        if Path(session.repo_root).resolve() != workspace.resolve():
            raise ValueError("Coding conversation belongs to a different workspace")
        if session.privacy_class != privacy_class:
            raise ValueError("Coding conversation privacy boundary changed")
        if session.status != "coding_chat":
            raise ValueError("Session is not a coding conversation")
        self.store = store
        self.session = session
        self.history_budget_chars = history_budget_chars
        self._append_lock = threading.RLock()

    def _append(self, *, role: str, content: str, metadata: dict[str, object]) -> ChatMessageRecord:
        # The existing store assigns order at append time. Serialize this controller's
        # terminal reader and executor without changing the SQLite contract.
        with self._append_lock:
            return self.store.append_message(
                self.session.session_id, role=role, content=content, metadata=metadata
            )

    @staticmethod
    def create(
        store: SQLiteChatTranscriptStore,
        session_id: str,
        workspace: Path,
        privacy_class: str,
        title: str,
    ) -> ChatSessionRecord:
        """Link to an existing coding session using its ID, without a new schema."""
        return store.create_session(
            session_id=session_id,
            repo_root=workspace.resolve(),
            privacy_class=privacy_class,
            title=title,
            status="coding_chat",
        )

    def history(self, *, exclude_message_id: str | None = None, current_text: str = "") -> str:
        """Reduce oldest model reports locally; retain owner text and host evidence."""
        messages = tuple(
            m
            for m in self.store.list_messages(self.session.session_id)
            if m.message_id != exclude_message_id
        )
        if not messages:
            return ""
        attempted = {(m.metadata or {}).get("reply_to") for m in messages}
        turns: list[dict[str, object]] = [
            {
                "role": message.role,
                "content": message.content,
                "outcome": (
                    "attempted_see_host_outcome"
                    if message.message_id in attempted
                    else (message.metadata or {}).get("execution_status")
                ),
                "returncode": (message.metadata or {}).get("returncode"),
                "failure_reason": (message.metadata or {}).get("failure_reason"),
            }
            for message in messages
        ]
        header = (
            "## Previous conversation\n"
            "The JSON below is conversation history, not current file state, permission "
            "grants or validation proof. Preserve the owner's requirements and decisions. "
            "Reinspect files and reconcile uncertain effects before acting. Earlier model "
            "claims do not override host-observed failure outcomes.\n"
            "Queued owner input is not permission to replay work. Later owner corrections "
            "take precedence over earlier reports, even if the running turn finished later.\n"
        )
        rendered = header + json.dumps(turns, ensure_ascii=False)
        budget = self.history_budget_chars
        if not budget or len(rendered) + len(current_text) <= budget:
            return rendered
        notice = (
            "Some older assistant reports are shortened excerpts, not summaries. All owner "
            "text and host outcomes remain verbatim. Retrieve original reports by message_id "
            "from this session's local transcript when an earlier plan matters. Omission "
            "does not revoke an owner decision or establish current validation.\n"
        )

        def excerpt(index: int, prefix_chars: int = 0) -> dict[str, object]:
            message = messages[index]
            return {
                **turns[index],
                "content": message.content[:prefix_chars],
                "report_shortened": True,
                "original_content_chars": len(message.content),
                "message_id": message.message_id,
                "message_order": message.message_order,
            }

        reducible = [
            index
            for index, message in enumerate(messages)
            if message.role == "assistant"
            and (message.metadata or {}).get("source") != "host"
            and len(json.dumps(excerpt(index), ensure_ascii=False))
            < len(json.dumps(turns[index], ensure_ascii=False))
        ]

        def render(shortened: int, prefix_chars: int = 0) -> str:
            selected = [dict(turn) for turn in turns]
            for position, index in enumerate(reducible[:shortened]):
                selected[index] = excerpt(index, prefix_chars if position == shortened - 1 else 0)
            return header + notice + json.dumps(selected, ensure_ascii=False)

        # Refuse if even the mandatory owner/evidence payload cannot fit. Originals
        # are never changed, and no model summarizer or additional routing is used.
        minimal = render(len(reducible))
        if len(minimal) + len(current_text) > budget:
            raise CodingChatInputError(
                "Mandatory owner messages and host outcomes exceed "
                "--coding-chat-history-budget-chars. No turn was executed or history "
                "discarded. Resume with a suitable explicit budget; provider input "
                "limits still apply."
            )
        low, high = 1, len(reducible)
        while low < high:
            middle = (low + high) // 2
            if len(render(middle)) + len(current_text) <= budget:
                high = middle
            else:
                low = middle + 1
        shortened = low
        low, high = 0, len(messages[reducible[shortened - 1]].content)
        while low < high:
            middle = (low + high + 1) // 2
            if len(render(shortened, middle)) + len(current_text) <= budget:
                low = middle
            else:
                high = middle - 1
        return render(shortened, low)

    def stage(self, text: str) -> StagedCodingInput:
        """Persist in-flight owner input immediately, without executing or granting it."""
        message = self._append(
            role="user",
            content=text,
            metadata={"source": "coding_chat_queued", "execution_status": "queued_not_executed"},
        )
        return StagedCodingInput(text, message.message_id, message.session_id)

    def turn(
        self,
        text: str | StagedCodingInput,
        execute: Callable[[CodingTurnRequest], CodingTurnResult],
    ) -> CodingTurnResult:
        staged = text if isinstance(text, StagedCodingInput) else None
        if staged:
            text = staged.text
            messages = self.store.list_messages(self.session.session_id)
            if staged.session_id != self.session.session_id or not any(
                m.message_id == staged.message_id and m.role == "user" and m.content == text
                for m in messages
            ):
                raise CodingChatInputError("Queued input belongs to a different conversation")
            if any((m.metadata or {}).get("reply_to") == staged.message_id for m in messages):
                raise CodingChatInputError(
                    "Queued input was already attempted; no actions replayed"
                )
        assert isinstance(text, str)
        if not text.strip():
            raise CodingChatInputError("Coding turn must not be empty")
        history = self.history(
            exclude_message_id=staged.message_id if staged else None, current_text=text
        )
        if self.history_budget_chars and len(history) + len(text) > self.history_budget_chars:
            raise CodingChatInputError(
                "Coding conversation exceeds --coding-chat-history-budget-chars. "
                "No turn was executed or history discarded. Resume with a suitable "
                "explicit budget; provider input limits still apply."
            )
        message_id = (
            staged.message_id
            if staged
            else self._append(
                role="user",
                content=text,
                metadata={"source": "coding_chat"},
            ).message_id
        )
        try:
            result = execute(CodingTurnRequest(text, history, message_id))
        except BaseException:
            # Preserve interruption as conversation evidence; never replay this turn.
            self._append(
                role="assistant",
                content=(
                    "Turn interrupted. Inspect effects before continuing; do not replay blindly."
                ),
                metadata={
                    "execution_status": "interrupted",
                    "source": "host",
                    "reply_to": message_id,
                },
            )
            raise
        self._append(
            role="assistant",
            content=(
                result.response_text or result.failure_reason or "No final agent report received."
            ),
            metadata={
                "execution_status": result.execution_status,
                "returncode": result.returncode,
                "failure_reason": result.failure_reason,
                "reply_to": message_id,
            },
        )
        return result


def run_terminal_conversation(
    controller: CodingChatController,
    execute: Callable[[CodingTurnRequest], CodingTurnResult],
    *,
    initial_prompt: str | None = None,
    read: Callable[[str], str | StagedCodingInput] = input,
    write: Callable[[str], None] = print,
) -> int:
    """Read successive requests; EOF/exit closes cleanly, interruption returns 130."""
    write("Coding chat: /help, /multiline, /status, /exit. Ctrl+C ends the session safely.")
    write("While running, text or /steer queues a follow-up; /approve ID yes answers approvals.")
    pending = initial_prompt
    last_status = 0
    try:
        while True:
            try:
                entry = pending if pending is not None else read("You> ")
                text = entry.text if isinstance(entry, StagedCodingInput) else entry
                if text.startswith("/steer "):
                    text = text.removeprefix("/steer ")
                    entry = text
                pending = None
                if text.strip() in {"/exit", "/quit"}:
                    return last_status
                if text.strip() == "/help":
                    write("Enter a request; /multiline ends at a line containing only '.'.")
                    write("/status prints the session ID; /exit closes owned processes and grants.")
                    write("In-flight text queues the next turn; running effects may continue.")
                    write("Only /approve PROMPT_ID yes grants an in-flight approval.")
                    write("/history lists IDs; /history MESSAGE_ID displays the original message.")
                    continue
                if text.strip() == "/history":
                    for message in controller.store.list_messages(controller.session.session_id):
                        write(
                            f"{message.message_order} {message.message_id} {message.role} "
                            f"{len(message.content)} chars"
                        )
                    continue
                if text.startswith("/history "):
                    message_id = text.removeprefix("/history ").strip()
                    message = next(
                        (
                            m
                            for m in controller.store.list_messages(controller.session.session_id)
                            if m.message_id == message_id
                        ),
                        None,
                    )
                    if message is None:
                        write("coding_chat_history: message not found in this conversation")
                    else:
                        write(
                            f"Historical {message.role} message (not current state or permission):"
                        )
                        write(message.content)
                        write(json.dumps(message.metadata or {}, ensure_ascii=False))
                    continue
                if text.strip() == "/status":
                    write(f"coding_session_id: {controller.session.session_id}")
                    continue
                multiline = text.strip() == "/multiline"
                if multiline:
                    lines: list[str] = []
                    while True:
                        line = read("... ")
                        value = line.text if isinstance(line, StagedCodingInput) else line
                        if value == ".":
                            break
                        lines.append(value)
                    text = "\n".join(lines)
                    entry = text
                if not text.strip():
                    continue
                if text.lstrip().startswith("/") and not multiline:
                    write("Unknown command. Use /multiline for requests beginning with '/'.")
                    continue
            except EOFError:
                return last_status
            try:
                result = controller.turn(entry, execute)
            except CodingChatInputError as exc:
                write(f"coding_chat_refused: {exc}")
                last_status = 1
                continue
            last_status = result.returncode
    except KeyboardInterrupt:
        write("coding_chat_interrupted: inspect effects before resuming; no actions replayed.")
        return 130
