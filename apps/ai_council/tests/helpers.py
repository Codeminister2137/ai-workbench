from __future__ import annotations

import json
from pathlib import Path


def write_config(path: Path, model: str = "llama3.2") -> None:
    path.write_text(
        json.dumps(
            {
                "ollama_base_url": None,
                "default_conversation": "test-conversation",
                "members": [
                    {
                        "name": "Analyst",
                        "model": model,
                        "temperature": 0.2,
                        "system_prompt": "Answer carefully.",
                    },
                    {
                        "name": "Skeptic",
                        "model": model,
                        "temperature": 0.4,
                        "system_prompt": "Find weak assumptions.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
