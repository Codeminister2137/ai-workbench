"""Compatibility import for agent-owned external execution settings."""

import sys
from typing import Any

from ai_agent import external_execution as _implementation


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


sys.modules[__name__] = _implementation
