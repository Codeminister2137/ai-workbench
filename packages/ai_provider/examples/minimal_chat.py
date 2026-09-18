from __future__ import annotations

from ai_provider import AIMessage, AIRequest, MessageRole
from ai_provider.config import BackendConfig
from ai_provider.factory import create_chat_client


def main() -> None:
    client = create_chat_client(BackendConfig.from_env())
    response = client.complete(
        AIRequest(messages=(AIMessage(MessageRole.USER, "Say hello in one short sentence."),))
    )
    print(response.message.content)
    print(f"backend={response.backend.provider} model={response.backend.model}")


if __name__ == "__main__":
    main()
