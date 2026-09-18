from __future__ import annotations

import argparse
from pathlib import Path

from config import DEFAULT_CONFIG_PATH, load_config
from storage import DEFAULT_DB_PATH, ConversationStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ask a private local AI council backed by Ollama and SQLite."
    )
    parser.add_argument("prompt", nargs="*", help="Prompt to send to the council.")
    parser.add_argument(
        "--conversation",
        "-c",
        help="Conversation name. Defaults to the value in council.json.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to council config JSON.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to local SQLite database.",
    )
    parser.add_argument(
        "--list-conversations",
        action="store_true",
        help="List locally stored conversations.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    store = ConversationStore(args.db)
    try:
        if args.list_conversations:
            for item in store.list_conversations():
                print(
                    f"{item['name']} | {item['message_count']} messages | "
                    f"created {item['created_at']}"
                )
            return

        prompt = " ".join(args.prompt).strip()
        if not prompt:
            parser.error("Provide a prompt, or use --list-conversations.")

        config = load_config(args.config)
        from council import LocalCouncil

        council = LocalCouncil(config, store)
        answers = council.ask(prompt, conversation_name=args.conversation)

        for answer in answers:
            print(f"\n## {answer['member']} ({answer['model']})\n")
            print(answer["answer"])
    finally:
        store.close()


if __name__ == "__main__":
    main()
