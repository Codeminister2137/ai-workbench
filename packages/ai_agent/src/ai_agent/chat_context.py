"""Chat transcript context assembly with preserved instructions and latest turns."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ai_provider import (
    AIMessage,
    AIRequest,
    BackendConfig,
    ChatClient,
    MessageRole,
    PrivacyClass,
    ProviderError,
    ProviderErrorCategory,
)
from ai_provider.chat_transcripts import (
    ChatMessageRecord,
    ChatRollingSummaryRecord,
    ChatSessionRecord,
    SQLiteChatTranscriptStore,
    messages_to_ai_messages,
)


@dataclass(frozen=True, slots=True)
class ChatContextAssembly:
    """Bounded provider request context for one persisted chat turn."""

    messages: tuple[AIMessage, ...]
    mode: str
    summary_used: bool
    summary_updated: bool
    raw_message_count: int
    omitted_message_count: int
    total_chars: int


def assemble_chat_context(
    *,
    store: SQLiteChatTranscriptStore,
    session: ChatSessionRecord,
    messages: tuple[ChatMessageRecord, ...],
    client: ChatClient,
    config: BackendConfig,
    privacy_class: PrivacyClass,
    mode: str,
    budget_chars: int,
    recent_message_count: int,
) -> ChatContextAssembly:
    """Build bounded request messages for chat mode."""

    if budget_chars <= 0 or mode == "full_history":
        request_messages = messages_to_ai_messages(messages)
        return ChatContextAssembly(
            messages=request_messages,
            mode=mode,
            summary_used=False,
            summary_updated=False,
            raw_message_count=len(messages),
            omitted_message_count=0,
            total_chars=messages_total_chars(request_messages),
        )

    full_messages = messages_to_ai_messages(messages)
    full_chars = messages_total_chars(full_messages)
    if full_chars <= budget_chars:
        return ChatContextAssembly(
            messages=full_messages,
            mode=mode,
            summary_used=False,
            summary_updated=False,
            raw_message_count=len(messages),
            omitted_message_count=0,
            total_chars=full_chars,
        )

    if mode == "hard_fail":
        raise ProviderError(
            "chat history exceeds --chat-history-budget-chars and --chat-context-mode is hard_fail",
            category=ProviderErrorCategory.NON_RETRYABLE,
            provider=config.provider.value,
        )

    system_messages = tuple(
        message for message in messages if message.role == MessageRole.SYSTEM.value
    )
    conversation_messages = tuple(
        message for message in messages if message.role != MessageRole.SYSTEM.value
    )
    # Instructions and the latest turn are mandatory; never summarize merely to
    # discover that these alone cannot fit the caller's request budget.
    minimum_messages = (
        *messages_to_ai_messages(system_messages),
        *messages_to_ai_messages(conversation_messages[-1:]),
    )
    if not conversation_messages or messages_total_chars(minimum_messages) > budget_chars:
        raise ProviderError(
            "chat instructions plus latest message exceed --chat-history-budget-chars",
            category=ProviderErrorCategory.NON_RETRYABLE,
            provider=config.provider.value,
        )
    recent_count = max(1, recent_message_count)
    recent_messages = conversation_messages[-recent_count:]
    older_messages = conversation_messages[:-recent_count]
    summary = store.get_rolling_summary(session.session_id)
    summary_updated = False
    unsummarized_older_messages = tuple(
        message
        for message in older_messages
        if summary is None or message.message_order > summary.covered_message_order
    )
    if unsummarized_older_messages:
        summary = update_chat_rolling_summary(
            store=store,
            session=session,
            prior_summary=summary.summary if summary is not None else "",
            older_messages=unsummarized_older_messages,
            client=client,
            config=config,
            privacy_class=privacy_class,
        )
        summary_updated = True
    if summary is None:
        raise ProviderError(
            "chat history exceeds --chat-history-budget-chars but there are no older "
            "messages available for rolling summarization",
            category=ProviderErrorCategory.NON_RETRYABLE,
            provider=config.provider.value,
        )

    included_records = [*system_messages]
    summary_message = AIMessage(
        MessageRole.SYSTEM,
        "Rolling summary of earlier chat turns. Use this as compressed context; "
        "the following messages are the recent raw transcript tail.\n\n"
        f"{summary.summary}",
    )
    request_messages = (*messages_to_ai_messages(system_messages), summary_message)
    recent_records = list(recent_messages)
    while recent_records:
        recent_request_messages = messages_to_ai_messages(tuple(recent_records))
        candidate = (*request_messages, *recent_request_messages)
        if messages_total_chars(candidate) <= budget_chars:
            request_messages = candidate
            included_records.extend(recent_records)
            break
        recent_records = recent_records[1:]
    else:
        latest_record = recent_messages[-1]
        request_messages = (*request_messages, *messages_to_ai_messages((latest_record,)))
        included_records.append(latest_record)

    total_chars = messages_total_chars(request_messages)
    if total_chars > budget_chars:
        raise ProviderError(
            "chat rolling summary plus latest message exceeds --chat-history-budget-chars",
            category=ProviderErrorCategory.NON_RETRYABLE,
            provider=config.provider.value,
        )
    included_orders = {record.message_order for record in included_records}
    omitted_message_count = len(messages) - len(included_orders)
    return ChatContextAssembly(
        messages=request_messages,
        mode=mode,
        summary_used=True,
        summary_updated=summary_updated,
        raw_message_count=len(included_orders),
        omitted_message_count=max(0, omitted_message_count),
        total_chars=total_chars,
    )


def update_chat_rolling_summary(
    *,
    store: SQLiteChatTranscriptStore,
    session: ChatSessionRecord,
    prior_summary: str,
    older_messages: tuple[ChatMessageRecord, ...],
    client: ChatClient,
    config: BackendConfig,
    privacy_class: PrivacyClass,
) -> ChatRollingSummaryRecord:
    highest_order = max(message.message_order for message in older_messages)
    response = client.complete(
        AIRequest(
            messages=(
                AIMessage(
                    MessageRole.SYSTEM,
                    "Update a rolling chat summary for a coding assistant. Preserve "
                    "requirements, user decisions, unresolved questions, file paths, "
                    "commands, validation outcomes, and constraints. Do not invent facts. "
                    "Return only the updated summary.",
                ),
                AIMessage(
                    MessageRole.USER,
                    build_chat_summary_prompt(prior_summary, older_messages),
                ),
            ),
            model=config.model,
            privacy_class=privacy_class,
            metadata={
                "task_type": "chat_rolling_summary",
                "chat_session_id": session.session_id,
                "covered_message_order": highest_order,
            },
        )
    )
    summary_text = response.message.content.strip()
    if not summary_text:
        raise ProviderError(
            "chat rolling summarizer returned an empty summary",
            category=ProviderErrorCategory.NON_RETRYABLE,
            provider=response.backend.provider,
        )
    return store.upsert_rolling_summary(
        session.session_id,
        summary=summary_text,
        covered_message_order=highest_order,
        provider=response.backend.provider,
        model=response.backend.model,
        metadata={
            "finish_reason": response.finish_reason.value,
            "usage_source": response.usage.source.value,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.total_tokens,
            "latency_ms": response.latency_ms,
        },
    )


def build_chat_summary_prompt(prior_summary: str, messages: tuple[ChatMessageRecord, ...]) -> str:
    rendered_messages = "\n\n".join(
        f"[{message.message_order}] {message.role}:\n{message.content}" for message in messages
    )
    return (
        "# Existing rolling summary\n"
        f"{prior_summary or '(none)'}\n\n"
        "# New raw messages to fold into the summary\n"
        f"{rendered_messages}"
    )


def messages_total_chars(messages: Sequence[AIMessage]) -> int:
    return sum(len(message.role.value) + len(message.content) for message in messages)
