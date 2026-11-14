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
import os
import re
import sys
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
    facts: dict[str, str] | None = None  # parsed from full stdout (session id, route)


def build_mai_argv(
    run: dict,
    *,
    repo_root: Path | str,
    user_config: Path | str,
    catalog: Path | str | None = None,
    coding_session: str | None = None,
) -> list[str]:
    """Argv handing a run to Mai; never pins a model (orchestrator decides).

    Each attempt opens a fresh coding session (``new``) unless
    ``coding_session`` names one to resume (chat turns reuse their bound
    session); the assigned session id and effective route are parsed
    back from Mai's stdout. The catalog defaults to the repo catalog
    (Mai's own default is CWD-relative, which breaks under the
    dashboard's working directory).
    """
    run_id = str(run.get("id", "?"))
    title = run.get("title") or "(untitled)"
    body = run.get("body") or ""
    prompt = f"Run {run_id}: {title}\nWorkspace: {repo_root}\n\nTask:\n{body}"
    catalog_path = (
        Path(catalog)
        if catalog
        else Path(repo_root) / "packages/ai_orchestrator/examples/model_catalog.toml"
    )
    return [
        prompt,
        "--mode",
        "implement",
        "--execute",
        "--coding-session",
        coding_session or "new",
        "--repo-root",
        str(repo_root),
        "--user-config",
        str(user_config),
        "--catalog",
        str(catalog_path),
        # Run-level approval was granted at drain time; per-command
        # interactive prompts would hang forever without a TTY.
        "--approval-policy",
        "trusted_local",
    ]


def parse_mai_facts(stdout: str) -> dict[str, str]:
    """Pull Mai-printed facts (session id, effective route) from stdout."""
    facts: dict[str, str] = {}
    for line in stdout.splitlines():
        for key in ("coding_session_id", "effective_route_id"):
            if line.startswith(f"{key}:"):
                facts[key] = line.split(":", 1)[1].strip()
    return facts


def run_mai_session(
    argv: Sequence[str], *, runner: Callable[[Sequence[str]], int] | None = None
) -> MaiRunOutcome:
    """Invoke Mai, capturing output tails; never raises.

    Stdin is an empty stream for the call: any residual interactive
    prompt hits EOF immediately instead of hanging the drain thread.
    """
    call = runner
    if call is None:  # pragma: no cover - default calls Mai (live only)
        from ai_agent.repo_coding_assistant import main as mai_main

        call = mai_main

    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            old_stdin, sys.stdin = sys.stdin, io.StringIO("")
            try:
                exit_code = int(call(list(argv)))
            finally:
                sys.stdin = old_stdin
    except Exception as exc:  # noqa: BLE001 - receipts carry failures, never raise
        return MaiRunOutcome(
            exit_code=3,
            stdout_tail=stdout.getvalue()[-TAIL_CHARS:],
            stderr_tail=stderr.getvalue()[-TAIL_CHARS:],
            error=f"{type(exc).__name__}: {exc}",
            facts=parse_mai_facts(stdout.getvalue()),
        )
    return MaiRunOutcome(
        exit_code=exit_code,
        stdout_tail=stdout.getvalue()[-TAIL_CHARS:],
        stderr_tail=stderr.getvalue()[-TAIL_CHARS:],
        facts=parse_mai_facts(stdout.getvalue()),
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
    facts = outcome.facts or parse_mai_facts(outcome.stdout_tail)
    if outcome.error is None and outcome.exit_code == 0:
        if not outcome.stdout_tail.strip() and not outcome.stderr_tail.strip():
            return {
                "status": "failed",
                "error": "Mai session exited 0 with empty output (no usable content)",
                "failure_class": "provider",
                "stdout_tail": outcome.stdout_tail,
                "stderr_tail": outcome.stderr_tail,
                "mai_argv": list(argv),
                "mai_session_id": facts.get("coding_session_id"),
                "route_id": facts.get("effective_route_id"),
                "source": "mai-session",
            }
        return {
            "status": "completed",
            "stdout_tail": outcome.stdout_tail,
            "stderr_tail": outcome.stderr_tail,
            "mai_argv": list(argv),
            "mai_session_id": facts.get("coding_session_id"),
            "route_id": facts.get("effective_route_id"),
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
        "mai_session_id": facts.get("coding_session_id"),
        "route_id": facts.get("effective_route_id"),
        "source": "mai-session",
    }


SUBPROCESS_TIMEOUT_SECONDS = 1800.0


def _mai_console_script() -> list[str]:
    """Console entry for out-of-process Mai (editable installs provide it)."""
    name = "ai-assistant.exe" if os.name == "nt" else "ai-assistant"
    return [str(Path(sys.executable).parent / name)]


def run_mai_subprocess(
    argv: Sequence[str],
    *,
    cmd_prefix: list[str] | None = None,
    timeout_seconds: float = SUBPROCESS_TIMEOUT_SECONDS,
    cwd: Path | str | None = None,
) -> MaiRunOutcome:
    """Invoke Mai as a supervised subprocess; kill on timeout; never raises."""
    import subprocess

    try:
        proc = subprocess.Popen(
            [*(cmd_prefix or _mai_console_script()), *argv],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            cwd=str(cwd) if cwd is not None else None,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        return MaiRunOutcome(
            exit_code=3, stdout_tail="", stderr_tail="", error=f"spawn failed: {exc}"
        )
    try:
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            stdout, stderr = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", ""
        return MaiRunOutcome(
            exit_code=3,
            stdout_tail=(stdout or "")[-TAIL_CHARS:],
            stderr_tail=(stderr or "")[-TAIL_CHARS:],
            error=f"Mai session timed out after {timeout_seconds:.0f}s (killed)",
            facts=parse_mai_facts(stdout or ""),
        )
    return MaiRunOutcome(
        exit_code=int(proc.returncode or 0),
        stdout_tail=(stdout or "")[-TAIL_CHARS:],
        stderr_tail=(stderr or "")[-TAIL_CHARS:],
        facts=parse_mai_facts(stdout or ""),
    )


def build_mai_executor(
    repo_root: Path | str,
    user_config: Path | str,
    *,
    catalog: Path | str | None = None,
    runner: Callable[[Sequence[str]], int] | None = None,
    backend: str = "subprocess",
    subprocess_timeout_seconds: float = SUBPROCESS_TIMEOUT_SECONDS,
    mai_cmd_prefix: list[str] | None = None,
    isolate: bool = False,
    coding_session: str | None = None,
) -> Callable[[dict], dict]:
    """Build a drain ``Executor`` handing runs to Mai sessions.

    ``backend="subprocess"`` (default) isolates Mai in a supervised child
    process with timeout recovery; ``backend="in-process"`` runs inline
    with no timeout (tests and fully trusted setups only). ``isolate``
    runs Mai in a per-run scratch worktree (``run/<id>``) instead of the
    shared checkout; setup failures fail the run instead of falling back.
    ``coding_session`` resumes a bound Mai session (chat turns); runs
    always start fresh.
    """

    def execute(run: dict) -> dict:
        root = Path(repo_root)
        isolated = None
        if isolate:
            from run_isolation import IsolationError, create_run_worktree

            try:
                isolated = create_run_worktree(root, str(run.get("id", "?")))
            except IsolationError as exc:
                return {
                    "status": "failed",
                    "error": f"run isolation failed: {exc}",
                    "failure_class": "unknown",
                    "source": "mai-session",
                }
            root = isolated.path
        argv = build_mai_argv(
            run,
            repo_root=root,
            user_config=(root / "user-config.toml" if isolated else user_config),
            catalog=catalog,
            coding_session=coding_session,
        )
        if backend == "subprocess":
            outcome = run_mai_subprocess(
                argv,
                cmd_prefix=mai_cmd_prefix,
                timeout_seconds=subprocess_timeout_seconds,
                cwd=root,
            )
        else:
            outcome = run_mai_session(argv, runner=runner)
        receipt = mai_receipt(outcome, argv)
        if isolated is not None:
            receipt["worktree"] = str(isolated.path)
            receipt["branch"] = isolated.branch
        return receipt

    return execute
