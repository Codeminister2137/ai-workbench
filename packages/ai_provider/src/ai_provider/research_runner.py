"""Foreground supervision of one unattended research CLI process."""

from __future__ import annotations

import argparse
import math
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from uuid import UUID

from ai_provider.orchestrated_runs import DEFAULT_ORCHESTRATED_RUN_DB, SQLiteOrchestratedRunStore


def print_progress(line: str) -> None:
    """Keep unsupported terminal glyphs from aborting an unattended worker."""
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(line.encode(encoding, errors="replace").decode(encoding), flush=True)


def stop_research_process(process: subprocess.Popen[str]) -> None:
    """Stop the owned worker tree; existing independent Ollama servers are untouched."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            # Still terminate the worker if Windows tree termination fails.
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)


def record_interrupted_run(
    database: Path,
    run_id: str | None,
    *,
    reason: str,
    execution_status: str = "timeout",
) -> bool:
    """Finalize an unfinished worker without overwriting an existing terminal handoff."""
    if run_id is None or not database.is_file():
        return False
    store = SQLiteOrchestratedRunStore(database)
    run = store.get_run(run_id)
    if run is None:
        return False
    stages = store.list_stages(run_id)
    handoff = next((stage for stage in stages if stage.name == "final_handoff"), None)
    if run.status not in {"planned", "running"} and (
        handoff is None or handoff.status not in {"planned", "running"}
    ):
        return False
    for stage in stages:
        if stage.name == "final_handoff":
            continue
        if stage.status in {"running", "planned"}:
            store.complete_stage(
                run_id,
                stage.name,
                status=execution_status if stage.status == "running" else "skipped",
                details={"supervisor_stop_reason": reason},
            )
    validation = next((stage for stage in stages if stage.name == "validation"), None)
    validation_status = (
        (validation.details or {}).get("validation_status", validation.status)
        if validation
        else "not_run"
    )
    if handoff is not None and handoff.status in {"planned", "running"}:
        store.complete_stage(
            run_id,
            "final_handoff",
            details={
                "execution_status": execution_status,
                "validation_status": validation_status,
                "blockers": reason,
                "risks": (
                    "Partial report and fetch/write receipts are preserved; "
                    "completeness is unverified"
                ),
                "next_action": "Review the partial report and validation before another run",
                "supervised": True,
            },
        )
    store.update_run_status(run_id, status=execution_status, execution_status=execution_status)
    return True


def supervise_research(
    command: Sequence[str],
    *,
    root: Path,
    database: Path,
    budget_seconds: float,
    output: Callable[[str], None] = print_progress,
    log_path: Path | None = None,
) -> int:
    """Stream one worker's output and enforce elapsed time independently of its tools."""
    if not math.isfinite(budget_seconds) or budget_seconds <= 0:
        raise ValueError("Research budget must be finite and greater than zero")
    started = time.monotonic()
    environment = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    process = subprocess.Popen(
        list(command),
        cwd=root,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=os.name != "nt",
        creationflags=(
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
        if os.name == "nt"
        else 0,
    )
    lines: queue.Queue[str | None] = queue.Queue()

    def read_output() -> None:
        assert process.stdout is not None
        try:
            for line in process.stdout:
                lines.put(line.rstrip("\r\n"))
        finally:
            lines.put(None)

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    run_id = None
    stopped = False
    interruption: BaseException | None = None

    def accept(line: str | None) -> None:
        nonlocal run_id
        if line is None:
            return
        if run_id is None and line.startswith("away_run_id: "):
            try:
                run_id = str(UUID(line.removeprefix("away_run_id: ")))
            except ValueError:
                pass
        output(line)

    try:
        while True:
            returncode = process.poll()
            if returncode is not None:
                break
            if returncode is None and time.monotonic() - started >= budget_seconds:
                stopped = True
                stop_research_process(process)
                break
            try:
                accept(lines.get(timeout=0.05))
            except queue.Empty:
                pass
    except BaseException as error:
        interruption = error
        stop_research_process(process)
    finally:
        reader.join(timeout=1)
        while not lines.empty():
            try:
                accept(lines.get_nowait())
            except BaseException as error:
                # Continue parsing queued run IDs even when the output consumer
                # is broken; durable finalization must not depend on a terminal.
                if interruption is None:
                    interruption = error
        if process.stdout is not None and not reader.is_alive():
            process.stdout.close()

    def announce(line: str) -> None:
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as stream:
                stream.write("\n" + line + "\n")
        output(line)

    if interruption is not None:
        record_interrupted_run(
            database,
            run_id,
            reason="Research supervisor was interrupted",
            execution_status="failed",
        )
        try:
            announce(
                "research_supervisor_status: failed; supervisor interrupted; "
                "partial report preserved"
            )
        except BaseException:
            # Preserve the original failure after recording the run, rather
            # than replacing it with another error from the output consumer.
            pass
        raise interruption
    if stopped:
        record_interrupted_run(database, run_id, reason="Research wall-clock budget exhausted")
        announce("research_supervisor_status: timeout; partial report preserved")
        return 124
    returncode = process.returncode or 0
    unfinished = record_interrupted_run(
        database,
        run_id,
        reason=f"Research worker exited with code {returncode} before durable finalization",
        execution_status="failed",
    )
    if unfinished:
        returncode = returncode or 1
        announce("research_supervisor_status: failed; worker exited before durable finalization")
    else:
        announce(f"research_supervisor_status: {'completed' if returncode == 0 else 'failed'}")
    return returncode


def main(argv: Sequence[str] | None = None) -> int:
    """Supervise the research wrapper's original CLI arguments without shell quoting."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--away-minutes", type=float, required=True)
    parser.add_argument("--away-run-db", type=Path, default=DEFAULT_ORCHESTRATED_RUN_DB)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--log-file", type=Path)
    parser.add_argument("--tool-profile", required=True, choices=("research",))
    parser.add_argument("--approval-policy", required=True, choices=("trusted_local",))
    args, _ = parser.parse_known_args(arguments)
    if not math.isfinite(args.away_minutes) or args.away_minutes <= 0:
        parser.error("--away-minutes must be finite and greater than zero")
    root = args.repo_root.resolve()
    return supervise_research(
        [sys.executable, "-m", "ai_provider.repo_coding_assistant", *arguments],
        root=root,
        database=root / args.away_run_db,
        budget_seconds=args.away_minutes * 60,
        log_path=root / args.log_file if args.log_file else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
