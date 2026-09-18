from __future__ import annotations

from domain import CouncilMember
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama


class LocalAgent:
    def __init__(self, member: CouncilMember, ollama_base_url: str | None = None):
        self.member = member
        self.llm = ChatOllama(
            model=member.model,
            base_url=ollama_base_url,
            temperature=member.temperature,
        )

    def answer(self, conversation: list[BaseMessage]) -> str:
        messages = [SystemMessage(content=self.member.system_prompt), *conversation]
        response = self.llm.invoke(messages)
        return str(response.content)

    def stream_answer(self, conversation: list[BaseMessage]):
        messages = [SystemMessage(content=self.member.system_prompt), *conversation]
        for chunk in self.llm.stream(messages):
            content = getattr(chunk, "content", "")
            if content:
                yield str(content)


def to_langchain_messages(rows: list[dict[str, str]]) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for row in rows:
        role = row["role"]
        content = row["content"]
        member_name = row.get("member_name")

        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            prefix = f"{member_name}: " if member_name else ""
            messages.append(AIMessage(content=f"{prefix}{content}"))

    return messages
