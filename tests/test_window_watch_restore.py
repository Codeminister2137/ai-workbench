"""Window-loss watchdog v2: restore guardrails stay intact.

The watchdog may only restore a fired console that is hidden AND
non-iconic with a title and a sane rect, must show it without
stealing focus (SW_SHOWNA), must verify visibility afterwards, and
must keep firing once per PID. These static checks pin the
guardrails so a refactor cannot silently widen the restore to
minimized windows or focus-stealing shows.
"""

from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "watch-window-loss.ps1"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_restore_targets_hidden_non_iconic_titled_consoles() -> None:
    text = _text()
    assert "ConsoleWindowClass" in text
    assert "-not $_.visible -and -not $_.iconic" in text
    assert "$_.title" in text


def test_restore_never_steals_focus() -> None:
    text = _text()
    assert "SW_SHOWNA" in text
    assert "ShowWindow($w.h, 8)" in text


def test_restore_verifies_and_records_outcome() -> None:
    text = _text()
    assert "IsWindowVisible($w.h)" in text
    assert "RESTORED" in text
    assert "RESTORE_FAILED" in text
    assert "NO_WINDOW" in text
    assert "$next[$k].restore" in text


def test_fire_once_per_pid_retained() -> None:
    text = _text()
    assert "if ($entry.fired) { continue }" in text


def test_fire_context_captures_forensics() -> None:
    text = _text()
    assert "fire-context.txt" in text
    assert "foreground:" in text
    assert "idle_ms:" in text
    assert "all processes" in text
    assert "display topology" in text
    assert "enumerated_top_level" in text
