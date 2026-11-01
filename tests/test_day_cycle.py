"""Day-cycle verdict logic; service checks are never executed here."""

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/day_cycle.py"
_spec = importlib.util.spec_from_file_location("day_cycle", SCRIPT)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)

GitState = _module.GitState
close_verdict = _module.close_verdict


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
