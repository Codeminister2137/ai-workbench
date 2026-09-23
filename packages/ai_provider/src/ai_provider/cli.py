"""Stable command entry point for the repository coding assistant."""

from __future__ import annotations

from collections.abc import Sequence

from ai_provider import repo_coding_assistant


def main(argv: Sequence[str] | None = None) -> int:
    """Run the stable CLI entry point."""

    return repo_coding_assistant.main(argv)
