from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from day_cycle import GitState, close_verdict


def test_close_verdict_clean_trees() -> None:
    states = [
        GitState("/repo/ai-workbench", "develop", True, 0, 0, "abc123"),
        GitState("/repo/remote-ai-operator", "main", True, 0, 0, "def456"),
    ]
    ok, blockers = close_verdict(states)
    assert ok is True
    assert blockers == []


def test_close_verdict_reports_every_blocker() -> None:
    states = [
        GitState("/repo/ai-workbench", "develop", False, 2, 1, "abc123"),
        GitState("/repo/remote-ai-operator", "?", False, 0, 0, "?"),
    ]
    ok, blockers = close_verdict(states)
    assert ok is False
    assert len(blockers) == 4
    assert any("uncommitted" in blocker for blocker in blockers)
    assert any("unpushed" in blocker for blocker in blockers)
    assert any("behind origin" in blocker for blocker in blockers)
    assert any("unreadable" in blocker for blocker in blockers)
