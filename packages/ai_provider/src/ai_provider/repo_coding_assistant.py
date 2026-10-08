"""Compatibility import and module entry point for the agent-owned assistant."""

import sys
from typing import Any

from ai_agent import repo_coding_assistant as _implementation


def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)


if __name__ == "__main__":
    raise SystemExit(_implementation.main())
else:
    # Keep legacy imports on the same module, including attribute assignments.
    sys.modules[__name__] = _implementation
