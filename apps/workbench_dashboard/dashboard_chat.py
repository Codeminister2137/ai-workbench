"""Dashboard chat sessions over coding-chat transcripts.

Maps dashboard chat sessions to ``coding_chat`` conversations so every turn
keeps a provider-neutral transcript. Turn execution in v1 is a single-shot
provider answer (no tools, no approvals); the executor is injectable so
tests stay offline and the agent loop can replace it in a later slice.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai_agent.coding_chat import CodingChatController, CodingTurnRequest, CodingTurnResult
from ai_provider import AIMessage, AIRequest, MessageRole
from ai_provider.chat_transcripts import (
    ChatMessageRecord,
    ChatSessionRecord,
    SQLiteChatTranscriptStore,
)
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import ChatClient, PrivacyClass
from ai_provider.errors import ProviderError
from ai_provider.factory import create_chat_client
from dashboard_config import DashboardConfig

SUPERVISOR_SYSTEM_PROMPT = (
    "You are the Workbench supervisor answering inside the owner's local "
    "dashboard. Be concise and concrete. This turn cannot run tools or edit "
    "files; say what you would do next instead of claiming effects."
)


@dataclass(slots=True)
class DashboardTurnOutcome:
    """Host-observed result of one dashboard chat turn."""

    response_text: str | None
    execution_status: str
    failure_reason: str | None
    provider: str | None
    model: str | None


class DashboardChat:
    """Own dashboard chat sessions; the provider owns answers, the store owns history."""

    def __init__(
        self,
        store: SQLiteChatTranscriptStore,
        config: DashboardConfig,
        workspace: Path,
        *,
        client_factory: Callable[[BackendConfig], ChatClient] = create_chat_client,
    ) -> None:
        self.store = store
        self.config = config
        self.workspace = workspace.resolve()
        self.client_factory = client_factory

    def create_session(self, *, title: str, privacy_class: str = "local_only") -> ChatSessionRecord:
        """Create one supervisor chat session bound to the dashboard workspace."""
        title = title.strip() or "Dashboard chat"
        return CodingChatController.create(
            self.store,
            f"dashboard-{uuid.uuid4().hex}",
            self.workspace,
            privacy_class,
            title,
        )

    def list_sessions(self, *, limit: int = 20) -> tuple[ChatSessionRecord, ...]:
        """List recent chat sessions newest-first."""
        return self.store.list_sessions(limit=limit)

    def list_messages(self, session_id: str) -> tuple[ChatMessageRecord, ...]:
        """List ordered transcript messages for one session."""
        session = self.store.get_session(session_id)
        if session is None:
            raise ValueError("Chat session not found")
        return tuple(self.store.list_messages(session_id))

    def rename_session(self, session_id: str, *, title: str) -> ChatSessionRecord:
        """Rename one chat session; rejects empty titles and unknown ids."""

        title = title.strip()
        if not title:
            raise ValueError("Title must not be empty")
        record = self.store.rename_session(session_id, title=title)
        if record is None:
            raise ValueError("Chat session not found")
        return record

    def delete_session(self, session_id: str) -> None:
        """Delete one chat session with its transcript; unknown ids fail."""

        if not self.store.delete_session(session_id):
            raise ValueError("Chat session not found")

    def _controller(self, session_id: str, privacy_class: str) -> CodingChatController:
        try:
            return CodingChatController(
                self.store,
                session_id,
                self.workspace,
                privacy_class,
                history_budget_chars=self.config.history_budget_chars,
            )
        except ValueError as exc:
            raise ValueError(f"Chat session unavailable: {exc}") from exc

    def _execute(self, request: CodingTurnRequest) -> CodingTurnResult:
        """Answer one turn with a single provider completion (no tools)."""
        try:
            provider = ProviderKind(self.config.provider)
        except ValueError:
            return CodingTurnResult(
                1, None, "failed", f"Unknown provider {self.config.provider!r}."
            )
        client = self.client_factory(
            BackendConfig(provider=provider, model=self.config.model, base_url=self.config.base_url)
        )
        history = request.history.strip()
        messages = [AIMessage(role=MessageRole.SYSTEM, content=SUPERVISOR_SYSTEM_PROMPT)]
        if history:
            messages.append(
                AIMessage(
                    role=MessageRole.SYSTEM,
                    content=f"Conversation history (oldest first, possibly reduced):\n{history}",
                )
            )
        messages.append(AIMessage(role=MessageRole.USER, content=request.text))
        privacy = (
            PrivacyClass.LOCAL_ONLY
            if provider is ProviderKind.OLLAMA
            else PrivacyClass.EXTERNAL_ALLOWED
        )
        try:
            response = client.complete(AIRequest(messages=tuple(messages), privacy_class=privacy))
        except ProviderError as exc:
            return CodingTurnResult(
                1,
                None,
                "failed",
                f"Provider {provider.value} failed: {exc}",
                provider=provider.value,
            )
        except Exception as exc:  # noqa: BLE001 - turn failures stay in the transcript
            return CodingTurnResult(
                1, None, "failed", f"Chat turn failed: {exc}", provider=provider.value
            )
        return CodingTurnResult(
            0,
            response.message.content,
            "completed",
            provider=provider.value,
            inference_observation={
                "latency_ms": int(response.latency_ms or 0),
            },
        )

    def send(self, session_id: str, text: str) -> DashboardTurnOutcome:
        """Append one user turn and its provider answer to the transcript."""
        session = self.store.get_session(session_id)
        if session is None:
            raise ValueError("Chat session not found")
        controller = self._controller(session_id, session.privacy_class)
        result = controller.turn(text, self._execute)
        return DashboardTurnOutcome(
            response_text=result.response_text,
            execution_status=result.execution_status,
            failure_reason=result.failure_reason,
            provider=result.provider,
            model=self.config.model,
        )
