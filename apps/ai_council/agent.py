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

    def _complete(self, messages: tuple[AIMessage, ...]) -> str:
        """Run one blocking completion with this member's model settings."""
        response = self.client.complete(
            AIRequest(
                messages=messages,
                model=self.member.model,
                temperature=self.member.temperature,
            )
        )
        return response.message.content

    def _stream(self, messages: tuple[AIMessage, ...]):
        """Stream one completion, yielding text deltas with this member's settings."""
        for event in self.client.stream(
            AIRequest(
                messages=messages,
                model=self.member.model,
                temperature=self.member.temperature,
            )
        ):
            if isinstance(event, AIStreamDelta):
                yield event.content
            elif isinstance(event, AIStreamFinal):
                continue

    def answer(self, conversation: Iterable[AIMessage]) -> str:
        return self._complete(self._messages(conversation))

    def stream_answer(self, conversation: Iterable[AIMessage]):
        yield from self._stream(self._messages(conversation))

    def react(self, conversation: Iterable[AIMessage], peer_answers: list[tuple[str, str]]) -> str:
        """React to other members' round-1 answers (round 2)."""
        return self._complete(self._reaction_messages(conversation, peer_answers))

    def stream_react(self, conversation: Iterable[AIMessage], peer_answers: list[tuple[str, str]]):
        yield from self._stream(self._reaction_messages(conversation, peer_answers))

    def synthesize(self, conversation: Iterable[AIMessage], answers: list[tuple[str, str]]) -> str:
        """Synthesize all positions as chair (round 3)."""
        return self._complete(self._synthesis_messages(conversation, answers))

    def stream_synthesize(self, conversation: Iterable[AIMessage], answers: list[tuple[str, str]]):
        yield from self._stream(self._synthesis_messages(conversation, answers))

    def _reaction_messages(
        self, conversation: Iterable[AIMessage], peer_answers: list[tuple[str, str]]
    ) -> tuple[AIMessage, ...]:
        others = "\n\n".join(f"{name} said:\n{text}" for name, text in peer_answers)
        return (
            *self._messages(conversation),
            AIMessage(
                MessageRole.USER,
                "Other council members answered as follows:\n\n"
                f"{others}\n\nReply in at most 150 words: what you agree with, "
                "what you disagree with, and what would change your answer.",
            ),
        )

    def _synthesis_messages(
        self, conversation: Iterable[AIMessage], answers: list[tuple[str, str]]
    ) -> tuple[AIMessage, ...]:
        positions = "\n\n".join(f"{name}:\n{text}" for name, text in answers)
        return (
            *self._messages(conversation),
            AIMessage(
                MessageRole.USER,
                "As chair, synthesize the council positions below. Reply in "
                "exactly this shape (headers verbatim, one bullet per line, "
                "disagreements named as 'Name: point'):\n"
                "AGREED:\n- <agreed point>\n"
                "DISAGREEMENTS:\n- <Name[, Name]: point>\n"
                "NEXT:\n- <what the asker should do next>\n"
                "CONSENSUS: <full|partial|none>\n"
                "Never invent consensus that is not there; use 'none' "
                "rather than forcing agreement.\n\n"
                f"{positions}",
            ),
        )

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
        else:
            raise ValueError(f"Unknown chat role: {role!r}")

    return messages
