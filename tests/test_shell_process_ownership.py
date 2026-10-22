"""Real shell regressions run inside an independently owned Windows worker."""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from ai_provider.acceptance_processes import process_identity
from ai_provider.process_ownership import WindowsJob

WORKER = r"""
import json, os, subprocess, sys, time
from pathlib import Path
from ai_agent.tools.base import ToolContext
from ai_agent.tools.shell import RunCommandTool
from ai_agent import validation_process
from ai_provider.acceptance_processes import process_identity

mode = sys.argv[1]


def _publish_pid(path, pid):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(str(pid))
    tmp.replace(path)


def _read_pid(path, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            text = path.read_text().strip()
            if text:
                return int(text)
        time.sleep(0.01)
    raise FileNotFoundError("PID was not published in time")


while not Path("release").exists():
    time.sleep(.01)
original_stop = validation_process._stop
if mode == "setup_failure":
    def reject(process):
        raise OSError("synthetic setup failure")
    validation_process.WindowsJob = reject
if mode in {"cleanup_failure", "interrupt_cleanup"}:
    def cleanup(process, job):
        original_stop(process, job)
        raise validation_process.ValidationCleanupError("synthetic cleanup failure")
    validation_process._stop = cleanup
if mode in {"interrupt", "interrupt_cleanup"}:
    original_wait = subprocess.Popen.wait
    interrupted = False
    def wait(process, *args, **kwargs):
        global interrupted
        if not interrupted:
            interrupted = True
            _read_pid(Path("child.pid"), timeout=4)
            raise KeyboardInterrupt
        return original_wait(process, *args, **kwargs)
    subprocess.Popen.wait = wait

command = "& '" + sys.executable.replace("'", "''") + "' fixture.py " + mode
started = time.monotonic()
try:
    result = RunCommandTool().execute(
        {"command": command, "timeout_seconds": 2},
        ToolContext(workspace_root=Path.cwd(), env={"SHELL_TEST_OVERRIDE": "context-value"}),
    )
    data = {"output": result.output, "error": result.is_error, "metadata": result.metadata}
except KeyboardInterrupt:
    data = {"interrupted": True}
data["elapsed"] = time.monotonic() - started
if Path("child.pid").exists():
    pid = _read_pid(Path("child.pid"))
    data["child_alive"] = process_identity(pid) is not None
Path("result.json").write_text(json.dumps(data))
"""

FIXTURE = r"""
import os, subprocess, sys, time
from pathlib import Path
mode = sys.argv[1]


def _publish_pid(path, pid):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(str(pid))
    tmp.replace(path)


Path("executed").touch()
print("stdout progress", flush=True)
print("stderr progress", file=sys.stderr, flush=True)
print(os.environ["SHELL_TEST_OVERRIDE"], flush=True)
print(os.environ["SHELL_TEST_INHERITED"], flush=True)
if mode in {
    "timeout", "large_timeout", "interrupt", "interrupt_cleanup", "root_exit", "root_failure"
}:
    child = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(60)"])
    _publish_pid(Path("child.pid"), child.pid)
if mode == "large_timeout":
    print("x" * 20000, flush=True)
    print("final progress", flush=True)
if mode in {"timeout", "large_timeout", "interrupt", "interrupt_cleanup"}:
    time.sleep(60)
if mode == "root_failure":
    sys.exit(7)
"""


@pytest.mark.skipif(os.name != "nt", reason="Independent Windows Job ownership regression")
@pytest.mark.parametrize(
    "mode",
    [
        "root_exit",
        "root_failure",
        "timeout",
        "large_timeout",
        "interrupt",
        "interrupt_cleanup",
        "setup_failure",
        "cleanup_failure",
    ],
)
def test_shell_owned_worker_has_outer_deadline_and_cleanup(tmp_path: Path, mode: str) -> None:
    (tmp_path / "worker.py").write_text(textwrap.dedent(WORKER))
    (tmp_path / "fixture.py").write_text(textwrap.dedent(FIXTURE))
    env = dict(os.environ, SHELL_TEST_INHERITED="inherited-value", SHELL_TEST_OVERRIDE="old-value")
    # The worker cannot launch workspace code until this independent job owns it.
    process = subprocess.Popen(
        [sys.executable, str(tmp_path / "worker.py"), mode],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    job = None
    try:
        job = WindowsJob(process)
        (tmp_path / "release").touch()
        try:
            stdout, stderr = process.communicate(timeout=12)
        except subprocess.TimeoutExpired:
            assert job.stop(2), "Outer job failed to stop the regressed worker tree"
            job = None
            process.communicate(timeout=3)
            pytest.fail("Shell exceeded its independent 12-second outer deadline")
        assert process.returncode == 0, (stdout, stderr)
        data = json.loads((tmp_path / "result.json").read_text())
        assert data["elapsed"] < 6
        assert not data.get("child_alive", False)
        if mode in {"interrupt", "interrupt_cleanup"}:
            assert data["interrupted"]
        elif mode == "setup_failure":
            assert data["error"]
            assert not (tmp_path / "executed").exists()
        elif mode == "cleanup_failure":
            assert data["error"]
            assert "ValidationCleanupError" in data["output"]
        else:
            if mode == "large_timeout":
                assert len(data["output"]) < 16_200
                assert "final progress" in data["output"]
            else:
                assert "stdout progress" in data["output"]
            assert "[STDERR]\nstderr progress" in data["output"]
            if mode != "large_timeout":
                assert "context-value" in data["output"]
                assert "inherited-value" in data["output"]
            assert "old-value" not in data["output"]
            assert data["error"] == (mode != "root_exit")
            if mode in {"timeout", "large_timeout"}:
                assert "timed out after 2.0 seconds" in data["output"]
                assert data["metadata"]["timeout"] == 2
                assert "exit_code" not in data["metadata"]
            else:
                # PowerShell -Command reports 1 for a failing final native command.
                assert data["metadata"]["exit_code"] == (1 if mode == "root_failure" else 0)
                assert data["metadata"]["cwd"] == str(tmp_path)
                if mode == "root_failure":
                    assert "[Process exited with code 1]" in data["output"]
        if (tmp_path / "child.pid").exists():
            text = (tmp_path / "child.pid").read_text().strip()
            if text:
                assert process_identity(int(text)) is None
    finally:
        if job is not None:
            assert job.stop(2)
        elif process.poll() is None:
            process.kill()
        process.wait(timeout=3)
