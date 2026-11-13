from __future__ import annotations

from agent import LocalAgent, to_provider_messages
from config import CouncilConfig
from storage import ConversationStore


def _estimate_tokens(texts: list[str]) -> int:
    """Rough token estimate (chars/4); documented, not a tokenizer."""
    return sum(len(text) for text in texts) // 4


class LocalCouncil:
    def __init__(self, config: CouncilConfig, store: ConversationStore):
        self.config = config
        self.store = store

    def _rounds(self, rounds: int) -> int:
        return max(1, min(rounds, self.config.max_rounds, 3))

    def _chair(self) -> str:
        return self.config.chair or self.config.members[0].name

    def _capped(self, peers: list[tuple[str, str]]) -> list[tuple[str, str]]:
        cap = self.config.reaction_cap_chars
        return [(name, text[:cap]) for name, text in peers]

    def ask(
        self,
        prompt: str,
        conversation_name: str | None = None,
        *,
        rounds: int = 1,
    ) -> list[dict[str, str]]:
        name = conversation_name or self.config.default_conversation
        conversation_id = self.store.get_or_create_conversation(name)
        self.store.add_message(conversation_id, role="user", content=prompt)

        history = to_provider_messages(self.store.list_messages(conversation_id))
        answers: list[dict[str, str]] = []
        spent = _estimate_tokens([prompt])

        for member in self.config.members:
            try:
                agent = LocalAgent(member, ollama_base_url=self.config.ollama_base_url)
                answer = agent.answer(history)
                self.store.add_message(
                    conversation_id,
                    role="assistant",
                    content=answer,
                    member_name=member.name,
                    model=member.model,
                    round=1,
                )
                answers.append(
                    {
                        "member": member.name,
                        "model": member.model,
                        "answer": answer,
                    }
                )
                spent += _estimate_tokens([answer])
            except Exception as exc:
                answers.append(
                    {"member": member.name, "model": member.model, "answer": "", "error": str(exc)}
                )

        wanted = self._rounds(rounds)
        if wanted >= 2:
            self._react_round(conversation_id, history, answers)
        if wanted >= 3 and not self._over_cap(spent):
            self._synthesize_round(conversation_id, history, answers)
        elif wanted >= 3:
            answers.append(
                {
                    "member": self._chair() + ":synthesis",
                    "model": "",
                    "answer": "",
                    "partial": "token cap reached",
                }
            )

        return answers

    def _over_cap(self, spent: int) -> bool:
        cap = self.config.max_tokens_per_question
        return cap > 0 and spent >= cap

    def _member_model(self, name: str) -> str:
        for member in self.config.members:
            if member.name == name:
                return member.model
        return ""

    def _react_round(self, conversation_id: int, history, answers: list[dict[str, str]]) -> None:
        by_member = {
            item["member"]: item.get("answer", "") for item in answers if not item.get("error")
        }
        for member in self.config.members:
            peers = self._capped(
                [(name, text) for name, text in by_member.items() if name != member.name]
            )
            if not peers:
                continue
            try:
                agent = LocalAgent(member, ollama_base_url=self.config.ollama_base_url)
                reaction = agent.react(history, peers)
                self.store.add_message(
                    conversation_id,
                    role="assistant",
                    content=reaction,
                    member_name=member.name,
                    model=member.model,
                    round=2,
                )
                answers.append(
                    {
                        "member": member.name,
                        "model": member.model,
                        "answer": reaction,
                        "round": "2",
                    }
                )
            except Exception as exc:
                answers.append(
                    {
                        "member": member.name,
                        "model": member.model,
                        "answer": "",
                        "round": "2",
                        "error": str(exc),
                    }
                )

    def _synthesize_round(
        self, conversation_id: int, history, answers: list[dict[str, str]]
    ) -> None:
        chair = self._chair()
        member = next(item for item in self.config.members if item.name == chair)
        positions = self._capped(
            [(item["member"], item.get("answer", "")) for item in answers if not item.get("error")]
        )
        try:
            agent = LocalAgent(member, ollama_base_url=self.config.ollama_base_url)
            synthesis = agent.synthesize(history, positions)
            self.store.add_message(
                conversation_id,
                role="assistant",
                content=synthesis,
                member_name=chair + ":synthesis",
                model=member.model,
                round=3,
            )
            answers.append(
                {
                    "member": chair + ":synthesis",
                    "model": member.model,
                    "answer": synthesis,
                    "round": "3",
                }
            )
        except Exception as exc:
            answers.append(
                {
                    "member": chair + ":synthesis",
                    "model": member.model,
                    "answer": "",
                    "round": "3",
                    "error": str(exc),
                }
            )

    def ask_events(self, prompt: str, conversation_name: str | None = None, *, rounds: int = 1):
        name = conversation_name or self.config.default_conversation
        conversation_id = self.store.get_or_create_conversation(name)
        self.store.add_message(conversation_id, role="user", content=prompt)

        history = to_provider_messages(self.store.list_messages(conversation_id))

        yield {
            "type": "council_started",
            "conversation": name,
            "members": [
                {"name": member.name, "model": member.model} for member in self.config.members
            ],
        }

        answers: list[dict[str, str]] = []
        for member in self.config.members:
            yield {
                "type": "member_started",
                "member": member.name,
                "model": member.model,
            }

            answer_parts: list[str] = []
            try:
                agent = LocalAgent(member, ollama_base_url=self.config.ollama_base_url)
                for chunk in agent.stream_answer(history):
                    answer_parts.append(chunk)
                    yield {
                        "type": "member_delta",
                        "member": member.name,
                        "delta": chunk,
                    }

                answer = "".join(answer_parts)
                self.store.add_message(
                    conversation_id,
                    role="assistant",
                    content=answer,
                    member_name=member.name,
                    model=member.model,
                    round=1,
                )
                answers.append({"member": member.name, "answer": answer})
                yield {
                    "type": "member_finished",
                    "member": member.name,
                    "answer": answer,
                }
            except Exception as exc:
                yield {
                    "type": "member_error",
                    "member": member.name,
                    "error": str(exc),
                }

        wanted = self._rounds(rounds)
        if wanted >= 2:
            yield {"type": "round_started", "round": 2}
            by_member = {item["member"]: item["answer"] for item in answers}
            for member in self.config.members:
                peers = self._capped(
                    [(who, text) for who, text in by_member.items() if who != member.name]
                )
                if not peers:
                    continue
                parts: list[str] = []
                try:
                    agent = LocalAgent(member, ollama_base_url=self.config.ollama_base_url)
                    for chunk in agent.stream_react(history, peers):
                        parts.append(chunk)
                        yield {"type": "reaction_delta", "member": member.name, "delta": chunk}
                    reaction = "".join(parts)
                    self.store.add_message(
                        conversation_id,
                        role="assistant",
                        content=reaction,
                        member_name=member.name,
                        model=member.model,
                        round=2,
                    )
                    yield {"type": "reaction_finished", "member": member.name, "answer": reaction}
                except Exception as exc:
                    yield {"type": "member_error", "member": member.name, "error": str(exc)}

        if wanted >= 3:
            chair = self._chair()
            member = next(item for item in self.config.members if item.name == chair)
            positions = self._capped([(item["member"], item["answer"]) for item in answers])
            yield {"type": "round_started", "round": 3}
            parts = []
            try:
                agent = LocalAgent(member, ollama_base_url=self.config.ollama_base_url)
                for chunk in agent.stream_synthesize(history, positions):
                    parts.append(chunk)
                    yield {"type": "synthesis_delta", "delta": chunk}
                synthesis = "".join(parts)
                self.store.add_message(
                    conversation_id,
                    role="assistant",
                    content=synthesis,
                    member_name=chair + ":synthesis",
                    model=member.model,
                    round=3,
                )
                yield {"type": "synthesis_finished", "answer": synthesis, "partial": False}
            except Exception as exc:
                yield {"type": "member_error", "member": chair, "error": str(exc)}

        yield {"type": "council_finished", "conversation": name}
