"""Compatibility import for the agent-owned CLI entry point."""

import sys
from typing import Any

from ai_agent import cli as _implementation


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


sys.modules[__name__] = _implementation
