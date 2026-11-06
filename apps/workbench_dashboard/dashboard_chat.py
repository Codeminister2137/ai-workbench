"""Dashboard chat sessions over coding-chat transcripts.

Maps dashboard chat sessions to ``coding_chat`` conversations so every turn
keeps a provider-neutral transcript. Turn execution runs through the
inspection relay (read-only workspace tools plus optional chat-channel
lookups); the relay runner is injectable so tests stay offline.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ai_agent.coding_chat import CodingChatController, CodingTurnRequest, CodingTurnResult
from ai_agent.fanout import FanoutPolicy
from ai_agent.messenger import MessengerResult, run_messenger_turn
from ai_agent.tools.base import BaseTool
from ai_provider.chat_transcripts import (
    ChatMessageRecord,
    ChatSessionRecord,
    SQLiteChatTranscriptStore,
)
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import ChatClient, PrivacyClass
from ai_provider.errors import ProviderError
from ai_provider.factory import create_chat_client
from ai_provider.translation import Translator, normalize_input
from dashboard_config import DashboardConfig
from dashboard_stores import DashboardStores

SUPERVISOR_SYSTEM_PROMPT = (
    "You are the Workbench supervisor answering inside the owner's local "
    "dashboard on their Windows 11 PC. Be concise and concrete. "
    "You can inspect the workspace (read, list, and search files; git status) "
    "but you cannot edit files, execute commands, restart services, or send "
    "mail. Mail delivery is not configured, so "
    "never claim an email was or will be sent; say mail is unavailable "
    "until the owner configures SMTP credentials. "
    "You have no live view of services (Ollama, dashboard, scheduled "
    "tasks); never assert their state. Send the owner to the dashboard "
    "Home status view, or quote only the last error already in this "
    "transcript. "
    "Development work happens only through agent runs the owner queues "
    "with the Request-run button and approves in the inbox; describe the "
    "next step instead of claiming effects. "
    "This PC runs Windows: never mention Linux paths, daemons, or commands."
)


def _truncate(text: str, limit: int) -> str:
    """Cap text at limit characters with an ellipsis marker."""
    return text if len(text) <= limit else text[:limit] + "…"


def _transcript_digest(
    store, session_id: str, *, max_turns: int = 30, per_turn: int = 500
) -> tuple[int, str]:
    """Deterministic capped digest of user/assistant turns for run context."""
    turns = [
        message
        for message in store.list_messages(session_id)
        if message.role in ("user", "assistant") and message.content.strip()
    ]
    digest = "\n".join(
        f"- **{message.role}**: {_truncate(message.content.strip(), per_turn)}"
        for message in turns[:max_turns]
    )
    return len(turns), digest


@dataclass(slots=True)
class DashboardTurnOutcome:
    """Host-observed result of one dashboard chat turn."""

    response_text: str | None
    execution_status: str
    failure_reason: str | None
    provider: str | None
    model: str | None


@dataclass(slots=True)
class RunRequestReceipt:
    """Host-observed receipt for one chat-triggered agent run request."""

    run_id: str
    inbox_id: str
    status: str
    fanout_effective: str


def _default_relay_runner(**kwargs) -> MessengerResult:
    """Run one chat turn through the inspection relay (read-only tools)."""
    return run_messenger_turn(**kwargs)


class DashboardChat:
    """Own dashboard chat sessions; the provider owns answers, the store owns history."""

    def __init__(
        self,
        store: SQLiteChatTranscriptStore,
        config: DashboardConfig,
        workspace: Path,
        *,
        client_factory: Callable[[BackendConfig], ChatClient] = create_chat_client,
        relay_runner: Callable[..., MessengerResult] | None = None,
        chat_tools: tuple[BaseTool, ...] | None = None,
    ) -> None:
        self.store = store
        self.config = config
        self.workspace = workspace.resolve()
        self.client_factory = client_factory
        self.relay_runner = relay_runner or _default_relay_runner
        self.chat_tools = tuple(chat_tools or ())

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
        """Answer one turn through the inspection relay (read-only tools)."""
        try:
            provider = ProviderKind(self.config.provider)
        except ValueError:
            return CodingTurnResult(
                1, None, "failed", f"Unknown provider {self.config.provider!r}."
            )
        client = self.client_factory(
            BackendConfig(provider=provider, model=self.config.model, base_url=self.config.base_url)
        )
        privacy = (
            PrivacyClass.LOCAL_ONLY
            if provider is ProviderKind.OLLAMA
            else PrivacyClass.EXTERNAL_ALLOWED
        )
        try:
            extra_kwargs: dict[str, object] = (
                {"extra_tools": self.chat_tools} if self.chat_tools else {}
            )
            result = self.relay_runner(
                client=client,
                workspace_root=self.workspace,
                history_text=request.history,
                prompt=request.text,
                system_prompt=SUPERVISOR_SYSTEM_PROMPT,
                privacy_class=privacy,
                **extra_kwargs,
            )
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
        text = result.answer
        if result.tool_receipts:
            text += f"\n\n_Checked with tools: {', '.join(result.tool_receipts)}._"
        return CodingTurnResult(
            0,
            text,
            "completed",
            provider=provider.value,
            inference_observation={
                "relay_iterations": result.iterations,
                "relay_tools_used": len(result.tool_receipts),
            },
        )

    def send(
        self,
        session_id: str,
        text: str,
        *,
        language: str = "en",
        translator: Translator | None = None,
    ) -> DashboardTurnOutcome:
        """Translate at ingestion, then append one turn plus its answer.

        Non-English input without a translator fails closed (nothing stored);
        translated turns keep the verbatim source in message metadata.
        """
        session = self.store.get_session(session_id)
        if session is None:
            raise ValueError("Chat session not found")
        normalized, _receipt = normalize_input(translator, text, language)
        metadata = (
            {
                "source_text": normalized.source,
                "source_lang": normalized.lang,
                "translated": True,
                "translator": normalized.translator_id,
            }
            if normalized.translated
            else None
        )
        controller = self._controller(session_id, session.privacy_class)
        result = controller.turn(normalized.working, self._execute, user_metadata=metadata)
        return DashboardTurnOutcome(
            response_text=result.response_text,
            execution_status=result.execution_status,
            failure_reason=result.failure_reason,
            provider=result.provider,
            model=self.config.model,
        )

    def draft_plan(
        self, session_id: str, *, stores: DashboardStores, title: str | None = None
    ) -> dict:
        """Draft a proposed plan deterministically from a chat transcript.

        Pure code, no model call: goal from the first user turn, full turn
        digest, and open sections for the owner/supervisor to refine.
        Raises ValueError for unknown sessions and empty transcripts.
        """
        session = self.store.get_session(session_id)
        if session is None:
            raise ValueError("Chat session not found")
        turns = [
            message
            for message in self.store.list_messages(session_id)
            if message.role in ("user", "assistant") and message.content.strip()
        ]
        if not turns:
            raise ValueError("Chat session has no turns to draft from")
        if title is not None and (not isinstance(title, str) or not title.strip()):
            raise ValueError("Title must be a non-empty string")
        plan_title = title.strip() if title else f"{session.title} (draft plan)"
        goal = next(
            (message.content.strip() for message in turns if message.role == "user"),
            "(no user turns)",
        )
        _count, digest = _transcript_digest(self.store, session_id, max_turns=50, per_turn=1000)
        body = (
            f"# Draft plan: {plan_title}\n\n"
            f"Source: chat session {session_id} ({len(turns)} turns) — "
            "deterministic digest, refine before approving.\n\n"
            f"## Goal (first user message)\n\n> {_truncate(goal, 500)}\n\n"
            f"## Discussion\n\n{digest}\n\n"
            "## Open sections\n\n"
            "- Scope: what is in and out.\n"
            "- Steps: ordered implementation phases.\n"
            "- Acceptance: how done is verified.\n"
        )
        plan_id = uuid.uuid4().hex
        record = {
            "id": plan_id,
            "title": plan_title[:200],
            "status": "proposed",
            "body": body,
            "source": f"chat:{session_id}",
            "updated_at_utc": datetime.now(UTC).isoformat(),
        }
        stores.plans.put(plan_id, record)
        return record

    def request_run(
        self,
        session_id: str,
        text: str,
        *,
        stores: DashboardStores,
        title: str | None = None,
        project: str | None = None,
        plan: str | None = None,
    ) -> RunRequestReceipt:
        """Queue one agent run from a chat turn; the owner approves it in the inbox.

        Most-restrictive by default: the run inherits ``chat_fanout_policy``
        (default ``restricted`` — no child spawns) and nothing executes until
        the linked inbox decision is approved and a run worker drains the
        queue. The approval is written before the run so a full inbox refuses
        the request without leaving a queued run behind.

        ``project`` is an already-validated work-root path stored as
        ``project_id`` on the run; runs and inbox stay global (no
        per-project data-dir splitting in this slice). ``plan`` is an
        existing plan id linked onto the run (fail-closed on unknown).
        """
        session = self.store.get_session(session_id)
        if session is None:
            raise ValueError("Chat session not found")
        text = text.strip()
        if not text:
            raise ValueError("Run request text is required")
        if project is not None and (not isinstance(project, str) or not project.strip()):
            raise ValueError("Project ref must be a non-empty string")
        if plan is not None and (not isinstance(plan, str) or not plan.strip()):
            raise ValueError("Plan ref must be a non-empty string")
        if plan is not None and stores.plans.get(plan) is None:
            raise ValueError("Unknown plan ref")
        try:
            policy = FanoutPolicy.coerce(self.config.chat_fanout_policy)
        except ValueError as exc:
            raise ValueError(f"Invalid chat fan-out policy: {exc}") from exc
        run_id = uuid.uuid4().hex
        run_title = (title or "").strip() or text[:60]
        now = datetime.now(UTC).isoformat()
        turn_count, digest = _transcript_digest(self.store, session_id)
        context_block = (
            f"\n\n--- Session transcript ({session_id}, {turn_count} turns) ---\n{digest}"
            if digest
            else ""
        )
        approval = stores.create_inbox_task(
            title=f"Approve agent run: {run_title}",
            body=(
                f"Chat requested an agent run (fan-out: {policy.value}).\n\n"
                f"Request:\n{text}\n"
                f"{context_block}\n"
                "Approve to let a run worker execute it; "
                "Reject leaves it parked (never executed)."
            ),
            task_type="decision",
            task_id=run_id,
            plan_id=plan,
            context_refs=[f"run:{run_id}", f"chat:{session_id}"]
            + ([f"plan:{plan}"] if plan else []),
            options=["Approve", "Reject"],
        )
        stores.runs.put(
            run_id,
            {
                "id": run_id,
                "title": run_title,
                "status": "queued",
                "body": text + context_block,
                "origin": "chat",
                "session_id": session_id,
                "fanout_policy": policy.value,
                "fanout_effective": policy.value,
                "inbox_id": approval["id"],
                "project_id": project,
                "plan_id": plan,
                "created_at_utc": now,
                "updated_at_utc": now,
            },
        )
        project_note = f" Project: {project}." if project else ""
        self.store.append_message(
            session_id,
            role="system",
            content=(
                f"Run requested: {run_title} (id {run_id}, "
                f"fan-out {policy.value}).{project_note} Queued for owner approval "
                f"in inbox task {approval['id']}."
            ),
        )
        return RunRequestReceipt(
            run_id=run_id,
            inbox_id=approval["id"],
            status="queued",
            fanout_effective=policy.value,
        )
