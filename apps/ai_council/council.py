from __future__ import annotations

from agent import LocalAgent, to_langchain_messages
from config import CouncilConfig
from storage import ConversationStore


class LocalCouncil:
    def __init__(self, config: CouncilConfig, store: ConversationStore):
        self.config = config
        self.store = store

    def ask(self, prompt: str, conversation_name: str | None = None) -> list[dict[str, str]]:
        name = conversation_name or self.config.default_conversation
        conversation_id = self.store.get_or_create_conversation(name)
        self.store.add_message(conversation_id, role="user", content=prompt)

        history = to_langchain_messages(self.store.list_messages(conversation_id))
        answers: list[dict[str, str]] = []

        for member in self.config.members:
            agent = LocalAgent(member, ollama_base_url=self.config.ollama_base_url)
            answer = agent.answer(history)
            self.store.add_message(
                conversation_id,
                role="assistant",
                content=answer,
                member_name=member.name,
                model=member.model,
            )
            answers.append(
                {
                    "member": member.name,
                    "model": member.model,
                    "answer": answer,
                }
            )

        return answers

    def ask_events(self, prompt: str, conversation_name: str | None = None):
        name = conversation_name or self.config.default_conversation
        conversation_id = self.store.get_or_create_conversation(name)
        self.store.add_message(conversation_id, role="user", content=prompt)

        history = to_langchain_messages(self.store.list_messages(conversation_id))

        yield {
            "type": "council_started",
            "conversation": name,
            "members": [
                {"name": member.name, "model": member.model}
                for member in self.config.members
            ],
        }

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
                )
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

        yield {"type": "council_finished", "conversation": name}
