"""Background shell jobs: start, poll, stop without blocking the turn.

Jobs run as child processes with file-backed records under the machine
temp dir (never inside the workspace, so listings stay clean). Each poll
returns only output since the previous poll; cursors persist in the job
record, so polling survives host restarts (the exit code then reads as
unknown). Runaway output kills the job past a hard cap instead of
filling the disk.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_agent.contracts import ToolCategory, ToolDefinition, ToolParameter, ToolResult
from ai_agent.tools.base import BaseTool, ToolContext

STREAM_HARD_CAP_BYTES = 8 * 1024 * 1024
POLL_CHUNK_BYTES = 64 * 1024
MAX_KEPT_JOBS = 50


def jobs_root(workspace_root: Path) -> Path:
    """Machine-temp job dir, namespaced per resolved workspace root."""
    slug = hashlib.sha256(str(workspace_root.resolve()).encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()).resolve() / "ai-workbench-jobs" / slug


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class JobRecord:
    id: str
    pid: int
    command: str
    cwd: str
    started_at: str
    status: str = "running"
    exit_code: int | None = None
    stdout_read: int = 0
    stderr_read: int = 0
    stdout_capped: bool = False
    stderr_capped: bool = False


class JobManager:
    """Owns background processes plus their persisted records."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._lock = threading.RLock()
        self._live: dict[str, subprocess.Popen[bytes]] = {}
        self._live_jobs: dict[str, Any] = {}

    def start(self, command: str, cwd: Path, env: dict[str, str]) -> JobRecord:
        with self._lock:
            job_id = uuid.uuid4().hex[:12]
            job_dir = self._root / job_id
            job_dir.mkdir(parents=True, exist_ok=False)
            stdout_path = job_dir / "stdout.log"
            stderr_path = job_dir / "stderr.log"
            stdout_handle = open(stdout_path, "wb")
            stderr_handle = open(stderr_path, "wb")
            try:
                if sys.platform == "win32":
                    shell_cmd = ["powershell", "-NoProfile", "-Command", command]
                else:
                    shell_cmd = ["/bin/sh", "-c", command]
                process = subprocess.Popen(
                    shell_cmd,
                    cwd=cwd,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    env=env,
                    # Never flash a console window; start suspended on Windows
                    # so the whole tree lands in our job object before it runs
                    # (mirrors run_validation_process).
                    creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0) | 0x4)
                    if os.name == "nt"
                    else 0,
                    start_new_session=os.name != "nt",
                )
            except Exception:
                stdout_handle.close()
                stderr_handle.close()
                raise
            # Parent-side descriptors can close; the child keeps its own.
            stdout_handle.close()
            stderr_handle.close()
            try:
                job = self._own_tree(process)
            except Exception:
                shutil.rmtree(job_dir, ignore_errors=True)
                raise
            record = JobRecord(
                id=job_id,
                pid=process.pid,
                command=command,
                cwd=str(cwd),
                started_at=_utc_now(),
            )
            self._live[job_id] = process
            if job is not None:
                self._live_jobs[job_id] = job
            self._write_meta(record)
            self._evict_old()
            return record

    @staticmethod
    def _resume(process: subprocess.Popen[bytes]) -> bool:
        import ctypes
        from ctypes import wintypes
        from typing import cast

        try:
            native = ctypes.WinDLL("ntdll")
            native.NtResumeProcess.argtypes = [wintypes.HANDLE]
            native.NtResumeProcess.restype = ctypes.c_long
            return native.NtResumeProcess(cast(Any, process)._handle) == 0
        except Exception:  # noqa: BLE001 - resume failure handled by caller
            return False

    @classmethod
    def _own_tree(cls, process: subprocess.Popen[bytes]) -> Any | None:
        """Assign the suspended tree to a job object, then resume it.

        Returns None when ownership is unavailable (nested-job refusal,
        non-Windows): the bare-handle path still supervises the root.
        A process that cannot resume is killed and reported, never wedged.
        """
        if os.name != "nt":
            return None
        job = None
        try:
            from ai_provider.process_ownership import WindowsJob

            job = WindowsJob(process)
        except Exception:  # noqa: BLE001 - ownership is best-effort
            job = None
        if cls._resume(process):
            return job
        try:
            process.kill()
        except OSError:
            pass
        raise OSError("Unable to resume owned background process")

    def poll(self, job_id: str) -> dict[str, Any]:
        """Refresh state and return new output since the previous poll."""
        with self._lock:
            record = self._read_meta(job_id)
            if record is None:
                raise KeyError(f"Unknown background job: {job_id}")
            self._refresh_state(record)
            job_dir = self._root / job_id
            stdout_new, stdout_consumed, stdout_pending = self._read_new(
                job_dir / "stdout.log", record.stdout_read
            )
            stderr_new, stderr_consumed, stderr_pending = self._read_new(
                job_dir / "stderr.log", record.stderr_read
            )
            record.stdout_read += stdout_consumed
            record.stderr_read += stderr_consumed
            self._write_meta(record)
            return {
                "id": record.id,
                "status": record.status,
                "exit_code": record.exit_code,
                "stdout": stdout_new,
                "stderr": stderr_new,
                "stdout_pending_bytes": stdout_pending,
                "stderr_pending_bytes": stderr_pending,
                "stdout_capped": record.stdout_capped,
                "stderr_capped": record.stderr_capped,
            }

    def stop(self, job_id: str) -> dict[str, Any]:
        """Terminate a running job and return its final state."""
        with self._lock:
            record = self._read_meta(job_id)
            if record is None:
                raise KeyError(f"Unknown background job: {job_id}")
            note = ""
            if record.status == "running":
                ended, code = self._terminate_tree(record)
                if ended:
                    record.exit_code = code
                    record.status = "stopped"
                    self._write_meta(record)
                else:
                    note = (
                        " Stop refused: no live handle for this job"
                        " (host restarted?) and its pid may be reused;"
                        " left running."
                    )
            return {
                "id": record.id,
                "status": record.status,
                "exit_code": record.exit_code,
                "note": note,
            }

    def _terminate_tree(self, record: JobRecord) -> tuple[bool, int | None]:
        """Kill the job's whole tree; (ended, exit code or None)."""
        job = self._live_jobs.pop(record.id, None)
        if job is not None:
            try:
                if job.stop(5.0):
                    process = self._live.pop(record.id, None)
                    if process is not None:
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            pass
                        return True, process.returncode
                    return True, 1
            except OSError:
                pass
        process = self._live.get(record.id)
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self._live.pop(record.id, None)
                        return False, None
            self._live.pop(record.id, None)
            return True, process.returncode
        if _pid_alive(record.pid):
            # No live handle: only the pid file is left. Refuse to signal a
            # bare pid — reuse could hit an unrelated process.
            return False, None
        return True, None

    def list_jobs(self) -> list[dict[str, Any]]:
        """Newest-first summaries; refreshes liveness without consuming output."""
        with self._lock:
            if not self._root.is_dir():
                return []
            records = []
            for meta_path in sorted(
                self._root.glob("*/meta.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            ):
                try:
                    record = self._read_meta(meta_path.parent.name)
                except (OSError, ValueError):
                    continue
                if record is None:
                    continue
                self._refresh_state(record)
                self._write_meta(record)
                records.append(
                    {
                        "id": record.id,
                        "status": record.status,
                        "exit_code": record.exit_code,
                        "command": record.command[:200],
                        "started_at": record.started_at,
                    }
                )
            return records

    def _refresh_state(self, record: JobRecord) -> None:
        if record.status != "running":
            return
        process = self._live.get(record.id)
        if process is not None:
            code = process.poll()
            if code is not None:
                record.status = "done"
                record.exit_code = code
                self._live.pop(record.id, None)
                return
        elif not _pid_alive(record.pid):
            record.status = "orphaned"
            record.exit_code = None
            self._write_meta(record)
            return
        job_dir = self._root / record.id
        for stream in ("stdout", "stderr"):
            path = job_dir / f"{stream}.log"
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > STREAM_HARD_CAP_BYTES:
                setattr(record, f"{stream}_capped", True)
                self._kill_for_cap(record, process)
                return

    def _kill_for_cap(self, record: JobRecord, process: subprocess.Popen[bytes] | None) -> None:
        if process is None:
            process = self._live.get(record.id)
        if process is not None and process.poll() is None:
            ended, code = self._terminate_tree(record)
            record.exit_code = code
            if not ended:
                # Unkillable without a verifiable handle; stop counting it
                # as running so it cannot wedge the manager.
                record.status = "orphaned"
                self._write_meta(record)
                return
        elif not _pid_alive(record.pid):
            record.exit_code = None
        record.status = "killed"
        self._write_meta(record)

    def _read_new(self, path: Path, offset: int) -> tuple[str, int, int]:
        """Return (text, bytes consumed, bytes still pending)."""
        try:
            with open(path, "rb") as handle:
                handle.seek(offset)
                chunk = handle.read(POLL_CHUNK_BYTES + 1)
        except OSError:
            return "", 0, 0
        taken, rest = chunk[:POLL_CHUNK_BYTES], chunk[POLL_CHUNK_BYTES:]
        text = taken.decode("utf-8", errors="replace")
        # Pending counts unread bytes; the +1 probe byte stays for next poll.
        pending = len(rest)
        if pending:
            pending += self._remaining_bytes(path, offset + len(taken) + len(rest))
        return text.replace("\r\n", "\n").replace("\r", "\n"), len(taken), pending

    @staticmethod
    def _remaining_bytes(path: Path, offset: int) -> int:
        try:
            return max(0, path.stat().st_size - offset)
        except OSError:
            return 0

    def _read_meta(self, job_id: str) -> JobRecord | None:
        path = self._root / job_id / "meta.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        try:
            return JobRecord(
                id=str(data["id"]),
                pid=int(data["pid"]),
                command=str(data["command"]),
                cwd=str(data.get("cwd", "")),
                started_at=str(data.get("started_at", "")),
                status=str(data.get("status", "running")),
                exit_code=data.get("exit_code"),
                stdout_read=int(data.get("stdout_read", 0)),
                stderr_read=int(data.get("stderr_read", 0)),
                stdout_capped=bool(data.get("stdout_capped", False)),
                stderr_capped=bool(data.get("stderr_capped", False)),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def _write_meta(self, record: JobRecord) -> None:
        path = self._root / record.id / "meta.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(
                {
                    "id": record.id,
                    "pid": record.pid,
                    "command": record.command,
                    "cwd": record.cwd,
                    "started_at": record.started_at,
                    "status": record.status,
                    "exit_code": record.exit_code,
                    "stdout_read": record.stdout_read,
                    "stderr_read": record.stderr_read,
                    "stdout_capped": record.stdout_capped,
                    "stderr_capped": record.stderr_capped,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        tmp.replace(path)

    def _evict_old(self) -> None:
        metas = sorted(self._root.glob("*/meta.json"), key=lambda path: path.stat().st_mtime)
        overflow = len(metas) - MAX_KEPT_JOBS
        if overflow <= 0:
            return
        for meta_path in metas:
            if overflow <= 0:
                return
            record = self._read_meta(meta_path.parent.name)
            if record is None or record.status == "running":
                continue
            shutil.rmtree(meta_path.parent, ignore_errors=True)
            overflow -= 1


_MANAGERS: dict[Path, JobManager] = {}
_MANAGERS_LOCK = threading.Lock()


def _manager(context: ToolContext) -> JobManager:
    """One manager per host process and job root, so tool calls share live handles.

    Without sharing, every poll would run without the process handle and could
    never report done/exit codes — only running/orphaned.
    """
    root = jobs_root(context.workspace_root)
    root.mkdir(parents=True, exist_ok=True)
    with _MANAGERS_LOCK:
        manager = _MANAGERS.get(root)
        if manager is None:
            manager = JobManager(root)
            _MANAGERS[root] = manager
        return manager


def _resolve_cwd(raw_cwd: object, context: ToolContext) -> Path:
    if getattr(context, "sandbox", False):
        raw_cwd = "."
    if not isinstance(raw_cwd, str):
        raise ValueError("Working directory must be a string.")
    target = context.resolve_path(raw_cwd)
    if not context.is_within_workspace(target):
        raise ValueError(f"Working directory {raw_cwd!r} is outside workspace boundary.")
    return target


@dataclass(frozen=True, slots=True)
class RunCommandBackgroundTool(BaseTool):
    """Start a shell command that keeps running after the call returns."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="run_command_background",
            description=(
                "Start a shell command in the background and return a job id "
                "immediately. Poll with poll_command until status is done, then "
                "read the final output. Prefer this for commands over ~30s."
            ),
            category=ToolCategory.SHELL,
            parameters=(
                ToolParameter(
                    name="command",
                    type_name="string",
                    description="The command line string to execute.",
                    required=True,
                ),
                ToolParameter(
                    name="cwd",
                    type_name="string",
                    description="Working directory (default: workspace root).",
                    required=False,
                    default=".",
                ),
            ),
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        command = arguments.get("command")
        if not isinstance(command, str) or not command.strip():
            return ToolResult(
                name=self.definition.name,
                output="Error: 'command' parameter is required.",
                is_error=True,
            )
        try:
            target_cwd = _resolve_cwd(arguments.get("cwd", "."), context)
        except ValueError as error:
            return ToolResult(name=self.definition.name, output=f"Error: {error}", is_error=True)
        try:
            record = _manager(context).start(
                command.strip(), target_cwd, context.command_environment()
            )
        except Exception as exc:  # noqa: BLE001 - report, don't crash the turn
            return ToolResult(
                name=self.definition.name,
                output=f"Error starting background command ({type(exc).__name__}).",
                is_error=True,
                metadata={"command": command},
            )
        return ToolResult(
            name=self.definition.name,
            output=f"Started background job {record.id} (pid {record.pid}).",
            is_error=False,
            metadata={"job_id": record.id, "pid": record.pid, "command": command},
        )


@dataclass(frozen=True, slots=True)
class PollCommandTool(BaseTool):
    """Report a background job's status plus output since the last poll."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="poll_command",
            description=(
                "Poll a background job: status (running/done/stopped/killed/"
                "orphaned), exit code when finished, and output since the "
                "previous poll. Poll again while running or while bytes remain."
            ),
            category=ToolCategory.SHELL,
            parameters=(
                ToolParameter(
                    name="job_id",
                    type_name="string",
                    description="Job id from run_command_background.",
                    required=True,
                ),
            ),
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        job_id = arguments.get("job_id")
        if not isinstance(job_id, str) or not job_id.strip():
            return ToolResult(
                name=self.definition.name,
                output="Error: 'job_id' parameter is required.",
                is_error=True,
            )
        try:
            state = _manager(context).poll(job_id.strip())
        except KeyError:
            return ToolResult(
                name=self.definition.name,
                output=f"Error: unknown background job {job_id!r}.",
                is_error=True,
            )
        lines = [f"Job {state['id']}: {state['status']}"]
        if state["exit_code"] is not None:
            lines.append(f"Exit code: {state['exit_code']}")
        if state["stdout"]:
            lines.append(state["stdout"])
        if state["stderr"]:
            lines.append(f"[STDERR]\n{state['stderr']}")
        for stream in ("stdout", "stderr"):
            pending = state[f"{stream}_pending_bytes"]
            if pending:
                lines.append(f"({pending} more {stream} bytes pending; poll again.)")
            if state[f"{stream}_capped"]:
                lines.append(f"({stream} hit the output cap; job killed.)")
        if state["status"] == "orphaned":
            lines.append("(Host restarted; exit code unknown. Output files kept.)")
        return ToolResult(
            name=self.definition.name,
            output="\n\n".join(lines) if lines else "(No output yet)",
            is_error=False,
            metadata={
                "job_id": state["id"],
                "status": state["status"],
                "exit_code": state["exit_code"],
            },
        )


@dataclass(frozen=True, slots=True)
class StopCommandTool(BaseTool):
    """Terminate a running background job."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="stop_command",
            description=(
                "Terminate a running background job. Poll afterwards for any "
                "final output. Already-finished jobs report their state."
            ),
            category=ToolCategory.SHELL,
            parameters=(
                ToolParameter(
                    name="job_id",
                    type_name="string",
                    description="Job id from run_command_background.",
                    required=True,
                ),
            ),
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        job_id = arguments.get("job_id")
        if not isinstance(job_id, str) or not job_id.strip():
            return ToolResult(
                name=self.definition.name,
                output="Error: 'job_id' parameter is required.",
                is_error=True,
            )
        try:
            state = _manager(context).stop(job_id.strip())
        except KeyError:
            return ToolResult(
                name=self.definition.name,
                output=f"Error: unknown background job {job_id!r}.",
                is_error=True,
            )
        return ToolResult(
            name=self.definition.name,
            output=f"Job {state['id']}: {state['status']}.{state['note']}",
            is_error=False,
            metadata={
                "job_id": state["id"],
                "status": state["status"],
                "exit_code": state["exit_code"],
            },
        )
