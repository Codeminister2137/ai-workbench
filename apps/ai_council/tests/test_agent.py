from __future__ import annotations

from agent import LocalAgent, to_provider_messages
from ai_provider import (
    AIMessage,
    AIRequest,
    AIResponse,
    AIStreamDelta,
    AIStreamFinal,
    BackendInfo,
    BackendLocation,
    MessageRole,
)
from domain import CouncilMember


class FakeClient:
    def __init__(self) -> None:
        self.requests: list[AIRequest] = []

    def complete(self, request: AIRequest) -> AIResponse:
        self.requests.append(request)
        return AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, "provider answer"),
            backend=BackendInfo(
                provider="ollama",
                model=request.model or "unknown",
                location=BackendLocation.LOCAL,
            ),
        )

    def stream(self, request: AIRequest):
        self.requests.append(request)
        yield AIStreamDelta("provider ")
        yield AIStreamDelta("stream")
        yield AIStreamFinal(
            AIResponse(
                message=AIMessage(MessageRole.ASSISTANT, "provider stream"),
                backend=BackendInfo(
                    provider="ollama",
                    model=request.model or "unknown",
                    location=BackendLocation.LOCAL,
                ),
            )
        )


def test_to_provider_messages_preserves_conversation_roles() -> None:
    messages = to_provider_messages(
        [
            {"role": "user", "content": "Question?"},
            {"role": "assistant", "content": "Answer.", "member_name": "Analyst"},
        ]
    )

    assert messages == [
        AIMessage(MessageRole.USER, "Question?"),
        AIMessage(MessageRole.ASSISTANT, "Analyst: Answer."),
    ]


def test_local_agent_uses_provider_completion(monkeypatch) -> None:
    client = FakeClient()
    monkeypatch.setattr("agent.create_chat_client", lambda config: client)
    member = CouncilMember(
        name="Analyst",
        model="llama3.2",
        system_prompt="Be careful.",
        temperature=0.2,
    )

    answer = LocalAgent(member, ollama_base_url="http://ollama.test").answer(
        [AIMessage(MessageRole.USER, "Question?")]
    )

    assert answer == "provider answer"
    assert client.requests[0].model == "llama3.2"
    assert client.requests[0].temperature == 0.2
    assert client.requests[0].messages == (
        AIMessage(MessageRole.SYSTEM, "Be careful."),
        AIMessage(MessageRole.USER, "Question?"),
    )


def test_local_agent_streams_provider_deltas(monkeypatch) -> None:
    client = FakeClient()
    monkeypatch.setattr("agent.create_chat_client", lambda config: client)
    member = CouncilMember(
        name="Analyst",
        model="llama3.2",
        system_prompt="Be careful.",
        temperature=0.2,
    )

    chunks = list(LocalAgent(member).stream_answer([AIMessage(MessageRole.USER, "Question?")]))

    assert chunks == ["provider ", "stream"]
    assert client.requests[0].messages[0] == AIMessage(MessageRole.SYSTEM, "Be careful.")
