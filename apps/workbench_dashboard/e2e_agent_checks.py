"""Agent-executed E2E step checks (owner decision 492fc69a, option A).

Steps carrying an exact backticked command can run agent-side: the
owner reviews attached evidence instead of a terminal. Execution is
narrowly allowlisted (venv pytest on one path, `--help` probes),
timeout-bounded, and repo-rooted; anything else is rejected, never
guessed. The runner is injectable so tests stay offline.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

CHECK_TIMEOUT_SECONDS = 300
EVIDENCE_CHARS = 8000

_BACKTICKED = re.compile(r"`([^`]+)`")
_SHELL_CHARS = re.compile(r"[&|;$`()<>]")
_PYTEST_RE = re.compile(r"^\.venv/Scripts/python\.exe -m pytest \S+ -q$")
_HELP_RE = re.compile(r"^\S+ --help$")


def extract_command(action: str) -> str | None:
    """Return the first backticked runnable command, if it matches the allowlist."""
    for match in _BACKTICKED.finditer(action or ""):
        candidate = " ".join(match.group(1).split())
        if _SHELL_CHARS.search(candidate):
            continue
        if _PYTEST_RE.match(candidate) or _HELP_RE.match(candidate):
            return candidate
    return None


def _default_runner(argv: Sequence[str], repo_root: Path) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            list(argv),
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=CHECK_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        tail = str(exc.stdout or "") + str(exc.stderr or "")
        return 124, tail + "\n[TIMEOUT]"
    except OSError as exc:
        return 127, f"[NOT RUNNABLE HERE] {exc}"
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output or "(no output)"


def execute_check(
    action: str,
    repo_root: Path,
    runner: Callable[[Sequence[str], Path], tuple[int, str]] | None = None,
) -> dict[str, object]:
    """Run one exact-command step; raises ValueError when not runnable."""
    command = extract_command(action)
    if command is None:
        raise ValueError("step carries no exact runnable command")
    call = runner or _default_runner
    argv = shlex.split(command, posix=False)
    code, output = call(argv, repo_root)
    return {"command": command, "exit_code": code, "output": output[-EVIDENCE_CHARS:]}
