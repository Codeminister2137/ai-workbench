"""UTF-8 transport for agent-owned Windows PowerShell commands."""

from __future__ import annotations


def powershell_command(command: str) -> list[str]:
    """Avoid PowerShell 5.1's lossy ASCII pipe into native programs.

    Console output and Python's redirected streams must agree with the UTF-8
    capture reader too. File cmdlets still require explicit ``-Encoding utf8``;
    this does not change the owner's profile or machine configuration.
    """
    prefix = (
        "$OutputEncoding = [Console]::InputEncoding = [Console]::OutputEncoding = "
        "[System.Text.UTF8Encoding]::new($false); "
        "$env:PYTHONIOENCODING = 'utf-8'; "
    )
    return ["powershell", "-NoProfile", "-Command", prefix + command]
