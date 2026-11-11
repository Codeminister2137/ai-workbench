"""Stable command entry point for the repository coding assistant."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from ai_agent import repo_coding_assistant


def main(argv: Sequence[str] | None = None) -> int:
    """Run the stable CLI entry point."""

    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["doctor"]:
        from ai_agent.doctor import main as doctor_main

        return doctor_main(args[1:])
    return repo_coding_assistant.main(argv)
