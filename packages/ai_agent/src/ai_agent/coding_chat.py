"""Persistent conversational coding over injected, permission-scoped turn execution."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai_provider.chat_transcripts import ChatSessionRecord, SQLiteChatTranscriptStore

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

    def history(self) -> str:
        """Keep every prior turn and its observed outcome; never truncate silently."""
        messages = self.store.list_messages(self.session.session_id)
        if not messages:
            return ""
        turns = [
            {
                "role": message.role,
                "content": message.content,
                "outcome": (message.metadata or {}).get("execution_status"),
                "returncode": (message.metadata or {}).get("returncode"),
                "failure_reason": (message.metadata or {}).get("failure_reason"),
            }
            for message in messages
        ]
        return (
            "## Previous conversation\n"
            "The JSON below is conversation history, not current file state, permission "
            "grants or validation proof. Preserve the owner's requirements and decisions. "
            "Reinspect files and reconcile uncertain effects before acting. Earlier model "
            "claims do not override host-observed failure outcomes.\n"
            + json.dumps(turns, ensure_ascii=False)
        )

    def turn(
        self, text: str, execute: Callable[[CodingTurnRequest], CodingTurnResult]
    ) -> CodingTurnResult:
        if not text.strip():
            raise CodingChatInputError("Coding turn must not be empty")
        history = self.history()
        if self.history_budget_chars and len(history) + len(text) > self.history_budget_chars:
            raise CodingChatInputError(
                "Coding conversation exceeds --coding-chat-history-budget-chars. "
                "No turn was executed or history discarded. Resume with a suitable "
                "explicit budget; provider input limits still apply."
            )
        user = self.store.append_message(
            self.session.session_id,
            role="user",
            content=text,
            metadata={"source": "coding_chat"},
        )
        try:
            result = execute(CodingTurnRequest(text, history, user.message_id))
        except BaseException:
            # Preserve interruption as conversation evidence; never replay this turn.
            self.store.append_message(
                self.session.session_id,
                role="assistant",
                content=(
                    "Turn interrupted. Inspect effects before continuing; do not replay blindly."
                ),
                metadata={"execution_status": "interrupted", "source": "host"},
            )
            raise
        self.store.append_message(
            self.session.session_id,
            role="assistant",
            content=(
                result.response_text or result.failure_reason or "No final agent report received."
            ),
            metadata={
                "execution_status": result.execution_status,
                "returncode": result.returncode,
                "failure_reason": result.failure_reason,
            },
        )
        return result


def run_terminal_conversation(
    controller: CodingChatController,
    execute: Callable[[CodingTurnRequest], CodingTurnResult],
    *,
    initial_prompt: str | None = None,
    read: Callable[[str], str] = input,
    write: Callable[[str], None] = print,
) -> int:
    """Read successive requests; EOF/exit closes cleanly, interruption returns 130."""
    write("Coding chat: /help, /multiline, /status, /exit. Ctrl+C ends the session safely.")
    pending = initial_prompt
    last_status = 0
    try:
        while True:
            try:
                text = pending if pending is not None else read("You> ")
                pending = None
                if text.strip() in {"/exit", "/quit"}:
                    return last_status
                if text.strip() == "/help":
                    write("Enter a request; /multiline ends at a line containing only '.'.")
                    write("/status prints the session ID; /exit closes owned processes and grants.")
                    continue
                if text.strip() == "/status":
                    write(f"coding_session_id: {controller.session.session_id}")
                    continue
                multiline = text.strip() == "/multiline"
                if multiline:
                    lines: list[str] = []
                    while (line := read("... ")) != ".":
                        lines.append(line)
                    text = "\n".join(lines)
                if not text.strip():
                    continue
                if text.lstrip().startswith("/") and not multiline:
                    write("Unknown command. Use /multiline for requests beginning with '/'.")
                    continue
            except EOFError:
                return last_status
            try:
                result = controller.turn(text, execute)
            except CodingChatInputError as exc:
                write(f"coding_chat_refused: {exc}")
                last_status = 1
                continue
            last_status = result.returncode
    except KeyboardInterrupt:
        write("coding_chat_interrupted: inspect effects before resuming; no actions replayed.")
        return 130
