"""Chat context preserves mandatory turns and fails without fabricating summaries."""

import pytest
from ai_agent.chat_context import assemble_chat_context, messages_total_chars
from ai_provider import (
    AIMessage,
    AIRequest,
    AIResponse,
    BackendConfig,
    BackendInfo,
    BackendLocation,
    MessageRole,
    PrivacyClass,
    ProviderError,
    ProviderErrorCategory,
    ProviderKind,
)
from ai_provider.chat_transcripts import SQLiteChatTranscriptStore


class Summarizer:
    backend = BackendInfo("ollama", "synthetic", BackendLocation.LOCAL)

    def __init__(self, summary="Retain the original constraints."):
        self.summary = summary
        self.requests: list[AIRequest] = []

    def complete(self, request):
        self.requests.append(request)
        return AIResponse(AIMessage(MessageRole.ASSISTANT, self.summary), self.backend)

    def stream(self, request):
        raise NotImplementedError("Context tests use non-streaming summary requests")


@pytest.fixture
def chat(tmp_path):
    store = SQLiteChatTranscriptStore(tmp_path / "chat.sqlite3")
    session = store.create_session(
        repo_root=tmp_path, title="Synthetic", privacy_class="local_only"
    )
    for role, content in (
        (MessageRole.SYSTEM, "Preserve this rule."),
        (MessageRole.USER, "old request " + "x" * 500),
        (MessageRole.ASSISTANT, "old answer " + "y" * 500),
        (MessageRole.USER, "Latest question: żółć"),
    ):
        store.append_message(session.session_id, role=role, content=content)
    return store, session, Summarizer()


def assemble(chat, *, budget=350, mode="rolling_summary", recent=1):
    store, session, client = chat
    return assemble_chat_context(
        store=store,
        session=session,
        messages=store.list_messages(session.session_id),
        client=client,
        config=BackendConfig(ProviderKind.OLLAMA, "synthetic"),
        privacy_class=PrivacyClass.LOCAL_ONLY,
        mode=mode,
        budget_chars=budget,
        recent_message_count=recent,
    )


@pytest.mark.parametrize(
    "mode,budget",
    [("rolling_summary", 2000), ("hard_fail", 2000), ("full_history", 1), ("rolling_summary", 0)],
)
def test_history_is_unchanged_when_no_compression_is_needed(chat, mode, budget):
    store, session, client = chat
    records = store.list_messages(session.session_id)
    context = assemble(chat, mode=mode, budget=budget)
    assert [message.content for message in context.messages] == [
        record.content for record in records
    ]
    assert not client.requests
    assert not context.summary_used and not context.summary_updated
    assert context.omitted_message_count == 0
    assert context.raw_message_count == len(records)


def test_hard_failure_has_no_summary_effects(chat):
    store, session, client = chat
    with pytest.raises(ProviderError) as error:
        assemble(chat, mode="hard_fail")
    assert error.value.category is ProviderErrorCategory.NON_RETRYABLE
    assert not client.requests
    assert store.get_rolling_summary(session.session_id) is None


def test_summary_preserves_rules_latest_turn_privacy_and_transcript(chat):
    store, session, client = chat
    original = store.list_messages(session.session_id)
    context = assemble(chat)
    assert context.summary_used and context.summary_updated
    assert context.messages[0].content == original[0].content
    assert context.messages[-1].content == original[-1].content
    assert context.raw_message_count == 2
    assert context.omitted_message_count == 2
    assert context.total_chars == messages_total_chars(context.messages) <= 350
    assert store.list_messages(session.session_id) == original
    request = client.requests[0]
    assert request.privacy_class is PrivacyClass.LOCAL_ONLY
    assert request.model == "synthetic"
    assert original[-1].content not in request.messages[-1].content
    summary = store.get_rolling_summary(session.session_id)
    assert summary is not None
    assert summary.covered_message_order == original[-2].message_order


def test_cached_summary_does_not_repeat_provider_call(chat):
    store, session, client = chat
    first = assemble(chat)
    second = assemble(chat)
    assert len(client.requests) == 1
    assert first.messages == second.messages
    assert second.summary_used and not second.summary_updated
    assert store.get_rolling_summary(session.session_id) is not None


def test_incremental_summary_folds_only_new_older_turns(chat):
    store, session, client = chat
    original = store.list_messages(session.session_id)
    assemble(chat)
    store.append_message(
        session.session_id, role=MessageRole.ASSISTANT, content="new answer " + "z" * 500
    )
    latest = store.append_message(
        session.session_id, role=MessageRole.USER, content="Next question"
    )
    second = assemble(chat)
    assert len(client.requests) == 2
    prompt = client.requests[-1].messages[-1].content
    assert client.summary in prompt
    assert original[-1].content in prompt
    assert original[1].content not in prompt
    assert latest.content not in prompt
    assert second.messages[-1].content == latest.content
    summary = store.get_rolling_summary(session.session_id)
    assert summary is not None and summary.covered_message_order == latest.message_order - 1


@pytest.mark.parametrize("summary", ["", "   \n"])
def test_empty_summary_never_advances_saved_coverage(chat, summary):
    store, session, client = chat
    client.summary = summary
    with pytest.raises(ProviderError, match="empty summary"):
        assemble(chat)
    assert store.get_rolling_summary(session.session_id) is None


def test_impossible_latest_turn_budget_is_refused_before_summarizing(chat):
    store, session, client = chat
    with pytest.raises(ProviderError, match="instructions plus latest"):
        assemble(chat, budget=10)
    assert not client.requests
    assert store.get_rolling_summary(session.session_id) is None


def test_oversized_system_only_context_refuses_without_index_error(chat):
    store, _, client = chat
    session = store.create_session(
        repo_root=store.path.parent, title="Rules only", privacy_class="local_only"
    )
    store.append_message(
        session.session_id, role=MessageRole.SYSTEM, content="required rule " * 100
    )
    store.upsert_rolling_summary(
        session.session_id, summary="Existing summary", covered_message_order=1
    )
    with pytest.raises(ProviderError, match="instructions plus latest"):
        assemble((store, session, client), budget=10)
    assert not client.requests


def test_oversized_cached_summary_does_not_drop_latest_message(chat):
    store, session, client = chat
    store.upsert_rolling_summary(
        session.session_id, summary="large " * 100, covered_message_order=3
    )
    with pytest.raises(ProviderError, match="rolling summary plus latest"):
        assemble(chat)
    assert not client.requests
