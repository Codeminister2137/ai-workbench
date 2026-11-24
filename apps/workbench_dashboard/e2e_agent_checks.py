"""Agent-executed E2E step checks (owner decision 492fc69a, option A).

Steps carrying an exact backticked command can run agent-side: the
owner reviews attached evidence instead of a terminal. Execution is
narrowly allowlisted (venv pytest on one path, `--help` probes,
script `--dry-run` rehearsals, served-dashboard GET checks),
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
_DRYRUN_RE = re.compile(r"^\.venv/Scripts/python\.exe scripts/\S+\.py --dry-run$")
_HTTP_GET_RE = re.compile(r"^\.venv/Scripts/python\.exe scripts/e2e-http-get\.py /\S* \d+$")
_RUN_TESTS_RE = re.compile(
    r"^\.venv/Scripts/python\.exe scripts/run-tests\.py "
    r"(provider|orchestrator|agent|cli|research|council|dashboard|job-search)$"
)


def extract_command(action: str) -> str | None:
    """Return the first backticked runnable command, if it matches the allowlist."""
    for match in _BACKTICKED.finditer(action or ""):
        candidate = " ".join(match.group(1).split())
        if _SHELL_CHARS.search(candidate):
            continue
        if (
            _PYTEST_RE.match(candidate)
            or _HELP_RE.match(candidate)
            or _DRYRUN_RE.match(candidate)
            or _HTTP_GET_RE.match(candidate)
            or _RUN_TESTS_RE.match(candidate)
        ):
            return candidate
    return None


def _default_runner(
    argv: Sequence[str], repo_root: Path, timeout_seconds: float = CHECK_TIMEOUT_SECONDS
) -> tuple[int, str]:
    argv = list(argv)
    if argv and not Path(argv[0]).is_absolute() and ("/" in argv[0] or "\\" in argv[0]):
        # Windows resolves a relative program path against the CALLER's
        # cwd, not the child's `cwd` param: the serve process lives
        # elsewhere, so anchor relative paths at the repo root (observed:
        # every serve-side check 127'd while shell runs passed). Bare
        # command names keep PATH lookup.
        argv[0] = str(Path(repo_root).resolve() / argv[0])
    try:
        proc = subprocess.run(
            argv,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        tail = str(exc.stdout or "") + str(exc.stderr or "")
        return 124, tail + "\n[TIMEOUT]"
    except OSError as exc:
        return 127, f"[NOT RUNNABLE HERE] {exc}"
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output or "(no output)"


def format_evidence(command: str, exit_code: int, output: str) -> str:
    """Self-describing evidence: what ran and how it ended, then raw output."""
    return f"$ {command}\n(exit {exit_code})\n\n{output}"


def summarize_evidence(output: object, exit_code: object) -> str:
    """One glanceable line: exit plus the last meaningful output line.

    Owners read the verdict without expanding kilobytes of pytest dots;
    the full output stays one click away in the evidence detail.
    """
    code = exit_code if isinstance(exit_code, int) else "?"
    text = output if isinstance(output, str) else ""
    tail = ""
    for line in text.splitlines():
        stripped = " ".join(line.split())
        if stripped and not set(stripped) <= {"."}:
            tail = stripped
    if not tail:
        return f"exit {code}: no output captured"
    if len(tail) > 200:
        tail = tail[:197] + "..."
    return f"exit {code}: {tail}"


def execute_check(
    action: str,
    repo_root: Path,
    runner: Callable[[Sequence[str], Path], tuple[int, str]] | None = None,
    timeout_seconds: float = CHECK_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """Run one exact-command step; raises ValueError when not runnable.

    ``timeout_seconds`` bounds the default runner only; injected runners
    manage their own timeouts.
    """
    command = extract_command(action)
    if command is None:
        raise ValueError("step carries no exact runnable command")
    argv = shlex.split(command, posix=False)
    if runner is not None:
        code, output = runner(argv, repo_root)
    else:
        code, output = _default_runner(argv, repo_root, timeout_seconds)
    return {"command": command, "exit_code": code, "output": output[-EVIDENCE_CHARS:]}
