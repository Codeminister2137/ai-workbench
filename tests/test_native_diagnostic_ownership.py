"""Native diagnostics retain tree ownership through completion and cancellation."""

import os
import subprocess
import sys
import time

import pytest
from ai_provider import diagnostic_process
from ai_provider.acceptance_processes import process_identity
from ai_provider.external_agents import run_diagnostic_command
from ai_provider.process_ownership import WindowsJob


@pytest.mark.parametrize(
    "states, expected",
    [
        (["Z", "X"], False),
        (["S", "Z"], True),
        (["R"], True),
        (["D"], True),
        ([], False),
        (["malformed"], True),
    ],
)
def test_linux_group_state_controls(monkeypatch, tmp_path, states, expected):
    """Offline /proc controls do not claim POSIX runtime execution."""
    for index, state in enumerate(states, 10):
        entry = tmp_path / str(index)
        entry.mkdir()
        (entry / "stat").write_text(
            "bad stat" if state == "malformed" else f"{index} (name with ) spaces) {state} 1 42 42"
        )
    other = tmp_path / "99"
    other.mkdir()
    (other / "stat").write_text("99 (other) R 1 99 99")
    monkeypatch.setattr(diagnostic_process, "Path", lambda _: tmp_path)
    monkeypatch.setattr(diagnostic_process.sys, "platform", "linux")
    monkeypatch.setattr(diagnostic_process.os, "killpg", lambda *_: None, raising=False)
    assert diagnostic_process._posix_group_running(42) is expected


def test_linux_group_disappearing_member(monkeypatch, tmp_path):
    (tmp_path / "10").mkdir()
    monkeypatch.setattr(diagnostic_process, "Path", lambda _: tmp_path)
    monkeypatch.setattr(diagnostic_process.sys, "platform", "linux")
    monkeypatch.setattr(diagnostic_process.os, "killpg", lambda *_: None, raising=False)
    assert not diagnostic_process._posix_group_running(42)


def test_linux_group_unreadable_state_is_not_verified(monkeypatch, tmp_path):
    entry = tmp_path / "10"
    entry.mkdir()
    (entry / "stat").mkdir()  # Reading a directory fails on Windows and POSIX.
    monkeypatch.setattr(diagnostic_process, "Path", lambda _: tmp_path)
    monkeypatch.setattr(diagnostic_process.sys, "platform", "linux")
    monkeypatch.setattr(diagnostic_process.os, "killpg", lambda *_: None, raising=False)
    assert diagnostic_process._posix_group_running(42)


@pytest.mark.parametrize(
    "platform, absent, expected",
    [
        ("linux", True, False),
        ("darwin", True, False),
        ("darwin", False, True),
    ],
)
def test_posix_group_absence_and_unobservable_platform(monkeypatch, platform, absent, expected):
    def probe(*_):
        if absent:
            raise ProcessLookupError

    monkeypatch.setattr(diagnostic_process.sys, "platform", platform)
    monkeypatch.setattr(diagnostic_process.os, "killpg", probe, raising=False)
    assert diagnostic_process._posix_group_running(42) is expected


@pytest.mark.skipif(os.name != "nt", reason="Windows suspended diagnostic admission")
@pytest.mark.parametrize("failure", ["assignment", "resume_load", "resume_status"])
def test_diagnostic_setup_failure_cannot_execute_child(monkeypatch, tmp_path, failure):
    marker = tmp_path / "executed"
    processes, jobs = [], []
    original_popen = subprocess.Popen
    original_dll = diagnostic_process.ctypes.WinDLL

    def start(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        processes.append(process)
        try:
            jobs.append(WindowsJob(process))
        except BaseException:
            process.kill()
            process.wait(timeout=2)
            raise
        return process

    def job(process):
        if failure == "assignment":
            raise OSError("assignment failed")
        return WindowsJob(process)

    def load(name, *args, **kwargs):
        if name != "ntdll":
            return original_dll(name, *args, **kwargs)
        if failure == "resume_load":
            raise OSError("resume setup failed")
        from types import SimpleNamespace

        return SimpleNamespace(NtResumeProcess=lambda _: -1)

    monkeypatch.setattr(subprocess, "Popen", start)
    monkeypatch.setattr(diagnostic_process, "WindowsJob", job)
    monkeypatch.setattr(diagnostic_process.ctypes, "WinDLL", load)
    try:
        result = run_diagnostic_command(
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(marker)!r}).touch()",
        )
        assert not result["ok"]
        assert result["stderr"] == "Diagnostic command could not be executed."
        assert len(processes) == 1
        assert processes[0].poll() is not None
        assert not marker.exists()
    finally:
        for owned in jobs:
            assert owned.stop(2), "Independent setup-test cleanup failed"
        for process in processes:
            process.wait(timeout=2)


@pytest.mark.skipif(os.name != "nt", reason="Windows retained process-tree ownership")
@pytest.mark.parametrize(
    "mode",
    [
        "exit_root",
        "timeout",
        "interrupt",
        "cleanup_false",
        "cleanup_error",
        "interrupt_cleanup_false",
        "interrupt_cleanup_error",
        "exit_cleanup_false",
        "exit_cleanup_error",
    ],
)
def test_diagnostic_owns_descendants(monkeypatch, tmp_path, mode):
    script = tmp_path / "diagnostic.py"
    ready = tmp_path / "ready"
    pid_file = tmp_path / "child.pid"
    script.write_text(
        "import subprocess, sys, time\n"
        "from pathlib import Path\n"
        "ready, pid_file, mode = map(str, sys.argv[1:])\n"
        "deadline = time.monotonic() + 5\n"
        "while not Path(ready).exists():\n"
        "    if time.monotonic() >= deadline: sys.exit(3)\n"
        "    time.sleep(.01)\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(15)'])\n"
        "Path(pid_file).write_text(str(child.pid))\n"
        "print('hello', flush=True)\n"
        "if mode == 'timeout' or mode.startswith(('interrupt', 'exit_cleanup')): time.sleep(15)\n",
        encoding="utf-8",
    )
    original_popen = subprocess.Popen
    processes, outer_jobs = [], []

    def start(command, **kwargs):
        process = original_popen(command, **kwargs)
        processes.append(process)
        try:
            outer_jobs.append(WindowsJob(process))
        except BaseException:
            process.kill()
            process.wait(timeout=2)
            raise
        # Root is suspended until production ownership is installed. The gate
        # also protects this fixture if the production suspension regresses.
        ready.touch()
        if mode.startswith(("interrupt", "exit_cleanup")):
            original_wait = process.wait

            def interrupt_wait(timeout=None):
                deadline = time.monotonic() + 3
                while not pid_file.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                process.wait = original_wait
                if mode.startswith("exit_cleanup"):
                    raise SystemExit(23)
                raise KeyboardInterrupt

            process.wait = interrupt_wait
        return process

    if "cleanup" in mode:

        class FailedJob:
            def __init__(self, process):
                self.job = WindowsJob(process)

            def stop(self, timeout):
                assert self.job.stop(timeout)
                if mode.endswith("cleanup_error"):
                    raise OSError("private_cleanup_error")
                return False

        monkeypatch.setattr(diagnostic_process, "WindowsJob", FailedJob)
    monkeypatch.setattr(subprocess, "Popen", start)
    result = None
    caught = None
    try:
        started = time.monotonic()
        if mode.startswith(("interrupt", "exit_cleanup")):
            expected = SystemExit if mode.startswith("exit_cleanup") else KeyboardInterrupt
            with pytest.raises(expected) as caught:
                run_diagnostic_command(
                    sys.executable,
                    str(script),
                    str(ready),
                    str(pid_file),
                    mode,
                    timeout_seconds=1,
                )
        else:
            result = run_diagnostic_command(
                sys.executable,
                str(script),
                str(ready),
                str(pid_file),
                mode,
                timeout_seconds=1,
            )
        if mode.startswith(("interrupt_", "exit_cleanup")):
            assert caught is not None
            assert caught.value.__notes__ == [
                "Diagnostic process-tree cleanup could not be verified"
            ]
        elapsed = time.monotonic() - started
        assert pid_file.exists()
        child_pid = int(pid_file.read_text())
        assert process_identity(child_pid) is None
        assert processes[0].poll() is not None
        assert elapsed < 5
        if mode == "exit_root":
            assert result == {"ok": True, "returncode": 0, "stdout": "hello", "stderr": ""}
        elif not mode.startswith(("interrupt", "exit_cleanup")):
            assert result == {
                "ok": False,
                "returncode": None,
                "stdout": "",
                "stderr": (
                    "Diagnostic command timed out."
                    if mode == "timeout"
                    else "Diagnostic command could not be executed."
                ),
            }
    finally:
        for job in outer_jobs:
            assert job.stop(2), "Outer test tree cleanup could not be verified"
        for process in processes:
            process.wait(timeout=2)
