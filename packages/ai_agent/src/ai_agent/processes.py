"""Model-free supervision of direct child processes owned by one foreground host."""

import codecs
import os
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai_agent.contracts import ToolCategory, ToolDefinition, ToolParameter, ToolResult
from ai_agent.tools.base import BaseTool, ToolContext

OUTPUT_LIMIT = 32_000


@dataclass
class OwnedProcess:
    process: subprocess.Popen[bytes]
    output: dict[str, str] = field(default_factory=lambda: {"stdout": "", "stderr": ""})
    truncated: set[str] = field(default_factory=set)
    readers: list[threading.Thread] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


class ProcessSupervisor:
    """Handles survive agent switches while this host lives; PIDs grant no ownership."""

    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        self.processes: dict[str, OwnedProcess] = {}
        self.lock = threading.RLock()
        self.closed = False

    def start(self, argv: list[str], cwd: str = ".") -> str:
        with self.lock:
            if self.closed:
                raise ValueError("Process supervisor has closed; no new children can start")
            return self._start(argv, cwd)

    def _start(self, argv: list[str], cwd: str) -> str:
        directory = (self.workspace / cwd).resolve()
        if not directory.is_relative_to(self.workspace) or not directory.is_dir():
            raise ValueError("Process working directory must be inside the workspace")
        if not argv or any(not isinstance(arg, str) or "\0" in arg for arg in argv):
            raise ValueError("Process argv must be a nonempty list of strings without NUL")
        process = subprocess.Popen(
            argv,
            cwd=directory,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
        handle = uuid.uuid4().hex
        owned = OwnedProcess(process)
        self.processes[handle] = owned
        for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            assert stream is not None

            def read(label=name, source=stream):
                decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
                try:
                    while raw := os.read(source.fileno(), 4096):
                        chunk = decoder.decode(raw)
                        with owned.lock:
                            combined = owned.output[label] + chunk
                            if len(combined) > OUTPUT_LIMIT:
                                owned.truncated.add(label)
                            owned.output[label] = combined[-OUTPUT_LIMIT:]
                finally:
                    with owned.lock:
                        owned.output[label] = (
                            owned.output[label] + decoder.decode(b"", final=True)
                        )[-OUTPUT_LIMIT:]
                    source.close()

            reader = threading.Thread(target=read, daemon=True)
            reader.start()
            owned.readers.append(reader)
        return handle

    def status(self, handle: str) -> dict[str, Any]:
        owned = self.processes.get(handle)
        if owned is None:
            raise ValueError(
                "Unknown process handle; only this foreground host's children are accessible"
            )
        code = owned.process.poll()
        if code is not None:
            for reader in owned.readers:
                reader.join(timeout=1)
        with owned.lock:
            return {
                "process_handle": handle,
                "pid": owned.process.pid,
                "status": "running" if code is None else "completed" if code == 0 else "failed",
                "returncode": code,
                **owned.output,
                "truncated": sorted(owned.truncated),
            }

    def stop(self, handle: str) -> dict[str, Any]:
        owned = self.processes.get(handle)
        if owned is None:
            raise ValueError("Unknown process handle")
        if owned.process.poll() is None:
            owned.process.terminate()
            try:
                owned.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                owned.process.kill()
                owned.process.wait(timeout=5)
        return self.status(handle)

    def close(self) -> None:
        with self.lock:
            self.closed = True
            handles = tuple(self.processes)
        failure: Exception | None = None
        for handle in handles:
            try:
                self.stop(handle)
            except (OSError, subprocess.TimeoutExpired) as error:
                # One failed termination must not leave the other owned children alive.
                if failure is None:
                    failure = error
        if failure is not None:
            raise failure


class ProcessTool(BaseTool):
    """Three operations share one host-owned supervisor and ordinary permission checks."""

    def __init__(self, supervisor: ProcessSupervisor, operation: str):
        if operation not in {"start", "status", "stop"}:
            raise ValueError("Unknown process operation")
        self.supervisor = supervisor
        self.operation = operation

    @property
    def definition(self) -> ToolDefinition:
        parameters = (
            (
                ToolParameter("argv", "array", "Executable and arguments; no implicit shell"),
                ToolParameter("cwd", "string", "Workspace-relative working directory", False, "."),
            )
            if self.operation == "start"
            else (
                ToolParameter(
                    "process_handle", "string", "Opaque handle from this foreground host"
                ),
            )
        )
        return ToolDefinition(
            "process_" + self.operation,
            "Start an authorized direct child without waiting"
            if self.operation == "start"
            else "Read direct-child completion/output without a model call"
            if self.operation == "status"
            else "Stop an owned direct child; descendants are not managed",
            ToolCategory.READ if self.operation == "status" else ToolCategory.SHELL,
            parameters,
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        import json

        if context.workspace_root.resolve() != self.supervisor.workspace:
            raise ValueError("Process supervisor belongs to a different workspace")
        if self.operation == "start":
            argv = arguments.get("argv")
            if not isinstance(argv, list):
                raise ValueError("argv must be an array")
            handle = self.supervisor.start(argv, arguments.get("cwd", "."))
            result = self.supervisor.status(handle)
        else:
            handle = arguments["process_handle"]
            result = (
                self.supervisor.status(handle)
                if self.operation == "status"
                else self.supervisor.stop(handle)
            )
        return ToolResult(self.definition.name, json.dumps(result), metadata=result)
