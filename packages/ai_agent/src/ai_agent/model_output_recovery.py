"""In-memory progress evidence for known pre-tool output failures."""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

from ai_agent.contracts import ToolResult


class ModelOutputRecovery:
    """Keep repeated-failure counts across no-op edits and previously seen states.

    Only paths reported by completed tools inside the workspace are observed.
    Unknown effects do not count as progress. No recursive scan or durable state.
    """

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.paths: set[Path] = set()
        self.failures: Counter[tuple[tuple[str, str], ...]] = Counter()

    def observe(self, result: ToolResult) -> None:
        value = result.metadata.get("path")
        if not isinstance(value, str):
            return
        path = Path(value)
        if not path.is_absolute():
            path = self.root / path
        if path.is_symlink():
            return
        path = path.resolve()
        if path.is_relative_to(self.root):
            self.paths.add(path)

    def observed_state(self) -> tuple[tuple[str, str], ...]:
        """Fingerprint bounded observed paths without changing failure counters."""
        state = []
        for path in sorted(self.paths):
            try:
                if path.is_symlink() or not path.resolve().is_relative_to(self.root):
                    value = "unknown"
                elif not path.exists():
                    value = "absent"
                elif path.is_file():
                    if path.stat().st_size > 1048576:
                        value = "unknown"
                    else:
                        with path.open("rb") as stream:
                            data = stream.read(1048577)
                        value = (
                            hashlib.sha256(data).hexdigest() if len(data) <= 1048576 else "unknown"
                        )
                else:
                    value = "unknown"
            except OSError:
                value = "unknown"
            state.append((str(path.relative_to(self.root)), value))
        return tuple(state)

    def allow_feedback(self) -> bool:
        key = self.observed_state()
        self.failures[key] += 1
        return self.failures[key] < 2
