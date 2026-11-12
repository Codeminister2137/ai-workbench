"""Execute drain runs as Mai sessions (orchestrator-routed, mirrored).

Each run hands its task to Mai's own entry point
(``repo_coding_assistant.main``) with a durable per-run coding session.
No model is forced: Mai routes through the orchestrator by criteria
(cost policy, privacy, capabilities) and the captured output tail
preserves the routing evidence. The runner callable is injectable so
tests and dry runs stay offline; only the default calls Mai.
"""

from __future__ import annotations

import contextlib
import io
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

TAIL_CHARS = 4000

_ALLOWANCE_RE = re.compile(r"allowance|denied|cost polic|budget|quota|exhaust", re.IGNORECASE)
_PROVIDER_RE = re.compile(
    r"ProviderError|provider|authenticat|timeout|timed out|connect|model|route",
    re.IGNORECASE,
)


@dataclass(slots=True)
class MaiRunOutcome:
    """Observed result of one Mai session invocation."""

    exit_code: int
    stdout_tail: str
    stderr_tail: str
    error: str | None = None


def build_mai_argv(run: dict, *, repo_root: Path | str, user_config: Path | str) -> list[str]:
    """Argv handing a run to Mai; never pins a model (orchestrator decides)."""
    run_id = str(run.get("id", "?"))
    title = run.get("title") or "(untitled)"
    body = run.get("body") or ""
    prompt = f"Run {run_id}: {title}\nWorkspace: {repo_root}\n\nTask:\n{body}"
    return [
        prompt,
        "--mode",
        "implement",
        "--execute",
        "--coding-session",
        run_id,
        "--repo-root",
        str(repo_root),
        "--user-config",
        str(user_config),
    ]


def run_mai_session(
    argv: Sequence[str], *, runner: Callable[[Sequence[str]], int] | None = None
) -> MaiRunOutcome:
    """Invoke Mai, capturing output tails; never raises."""
    call = runner
    if call is None:  # pragma: no cover - default calls Mai (live only)
        from ai_agent.repo_coding_assistant import main as mai_main

        call = mai_main
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = int(call(list(argv)))
    except Exception as exc:  # noqa: BLE001 - receipts carry failures, never raise
        return MaiRunOutcome(
            exit_code=3,
            stdout_tail=stdout.getvalue()[-TAIL_CHARS:],
            stderr_tail=stderr.getvalue()[-TAIL_CHARS:],
            error=f"{type(exc).__name__}: {exc}",
        )
    return MaiRunOutcome(
        exit_code=exit_code,
        stdout_tail=stdout.getvalue()[-TAIL_CHARS:],
        stderr_tail=stderr.getvalue()[-TAIL_CHARS:],
    )


def classify_failure(*texts: str) -> str:
    """Map failure text to the supervision cause class (narrow first)."""
    blob = "\n".join(texts)
    if _ALLOWANCE_RE.search(blob):
        return "allowance"
    if _PROVIDER_RE.search(blob):
        return "provider"
    return "unknown"


def mai_receipt(outcome: MaiRunOutcome, argv: Sequence[str]) -> dict:
    """Drain receipt for a Mai outcome; transcripts stay in the tails."""
    if outcome.error is None and outcome.exit_code == 0:
        return {
            "status": "completed",
            "stdout_tail": outcome.stdout_tail,
            "stderr_tail": outcome.stderr_tail,
            "mai_argv": list(argv),
            "source": "mai-session",
        }
    error = outcome.error or f"Mai session exited with code {outcome.exit_code}"
    return {
        "status": "failed",
        "error": error,
        "failure_class": classify_failure(error, outcome.stdout_tail, outcome.stderr_tail),
        "stdout_tail": outcome.stdout_tail,
        "stderr_tail": outcome.stderr_tail,
        "mai_argv": list(argv),
        "source": "mai-session",
    }


def build_mai_executor(
    repo_root: Path | str,
    user_config: Path | str,
    *,
    runner: Callable[[Sequence[str]], int] | None = None,
) -> Callable[[dict], dict]:
    """Build a drain ``Executor`` handing runs to Mai sessions."""

    def execute(run: dict) -> dict:
        argv = build_mai_argv(run, repo_root=repo_root, user_config=user_config)
        return mai_receipt(run_mai_session(argv, runner=runner), argv)

    return execute
