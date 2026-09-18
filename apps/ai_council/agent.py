from __future__ import annotations

from collections.abc import Iterable

from ai_provider import (
    AIMessage,
    AIRequest,
    AIStreamDelta,
    AIStreamFinal,
    MessageRole,
)
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.factory import create_chat_client
from domain import CouncilMember


class LocalAgent:
    def __init__(self, member: CouncilMember, ollama_base_url: str | None = None):
        self.member = member
        self.client = create_chat_client(
            BackendConfig(
                provider=ProviderKind.OLLAMA,
                base_url=ollama_base_url,
                model=member.model,
                timeout_seconds=120.0,
            )
        )

    def answer(self, conversation: Iterable[AIMessage]) -> str:
        response = self.client.complete(
            AIRequest(
                messages=self._messages(conversation),
                model=self.member.model,
                temperature=self.member.temperature,
            )
        )
        return response.message.content

    def stream_answer(self, conversation: Iterable[AIMessage]):
        for event in self.client.stream(
            AIRequest(
                messages=self._messages(conversation),
                model=self.member.model,
                temperature=self.member.temperature,
            )
        ):
            if isinstance(event, AIStreamDelta):
                yield event.content
            elif isinstance(event, AIStreamFinal):
                continue

    def _messages(self, conversation: Iterable[AIMessage]) -> tuple[AIMessage, ...]:
        return (
            AIMessage(MessageRole.SYSTEM, self.member.system_prompt),
            *tuple(conversation),
        )


def to_provider_messages(rows: list[dict[str, str]]) -> list[AIMessage]:
    messages: list[AIMessage] = []
    for row in rows:
        role = row["role"]
        content = row["content"]
        member_name = row.get("member_name")

        if role == "user":
            messages.append(AIMessage(MessageRole.USER, content))
        elif role == "assistant":
            prefix = f"{member_name}: " if member_name else ""
            messages.append(AIMessage(MessageRole.ASSISTANT, f"{prefix}{content}"))

    return messages
