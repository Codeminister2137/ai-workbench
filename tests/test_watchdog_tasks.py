"""Watchdog scheduled tasks must never show a console window.

Every-5-minute visible PowerShell consoles steal window focus and break the
owner's typing (inbox: Pop-up windows). Both the task settings (Hidden) and
the launched powershell (WindowStyle Hidden) carry the fix: either alone
leaves a flash on some Windows builds.
"""

from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "register-watchdog-tasks.ps1"


def test_watchdog_registration_hides_consoles() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "New-ScheduledTaskSettingsSet" in text
    assert "-Hidden" in text, "task settings must hide the console"
    assert "-WindowStyle Hidden" in text, "launched powershell must stay hidden"
