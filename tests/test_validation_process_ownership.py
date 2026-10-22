"""Validation must not retain descendants or wait for inherited output pipes."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast

import pytest
from ai_agent.validation import run_validation_commands
from ai_provider.acceptance_processes import process_identity
from ai_provider.process_ownership import WindowsJob


def descendant_running(pid):
    if os.name == "nt":
        return process_identity(pid) is not None
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except FileNotFoundError:
        return False
    # POSIX group termination can leave an orphan awaiting init's reap. It is
    # dead and cannot retain output or continue workspace effects.
    return state not in {"Z", "X"}


@pytest.mark.skipif(
    os.name != "nt" and sys.platform != "linux", reason="Windows handles or Linux /proc inspection"
)
@pytest.mark.parametrize(
    "mode", ["timeout", "inherited_output", "root_exit", "root_failure", "interrupt"]
)
def test_validation_closes_its_tree_before_return(tmp_path, monkeypatch, mode):
    script = tmp_path / "validator.py"
    script.write_text(
        "import subprocess,sys,time\n"
        "from pathlib import Path\n"
        "def _publish_pid(path,pid):\n"
        "    tmp=Path(str(path)+'.tmp')\n"
        "    tmp.write_text(str(pid))\n"
        "    tmp.replace(path)\n"
        "while not Path('release').exists(): time.sleep(.01)\n"
        "mode=sys.argv[1]\n"
        "kwargs={} if mode=='inherited_output' else "
        "dict(stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(6)'],**kwargs)\n"
        "_publish_pid(Path('child.pid'),p.pid)\n"
        "print('validator started',flush=True)\n"
        "print('diagnostic stderr',file=sys.stderr,flush=True)\n"
        "if mode=='root_failure': sys.exit(3)\n"
        "if mode!='root_exit': time.sleep(20)\n"
    )
    original_popen = subprocess.Popen
    jobs, processes = [], []

    def start(*args, **kwargs):
        if os.name != "nt":
            kwargs.setdefault("start_new_session", True)
        process = original_popen(*args, **kwargs)
        processes.append(process)
        # Retain independent test ownership even when exercising the broken runner.
        # The fixture cannot spawn until this outer ownership is established.
        if os.name == "nt":
            jobs.append(WindowsJob(process))
        (tmp_path / "release").touch()
        return process

    monkeypatch.setattr(subprocess, "Popen", start)
    if mode == "interrupt":
        original_wait = original_popen.wait
        interrupted = False

        def wait(process, *args, **kwargs):
            nonlocal interrupted
            if not interrupted:
                interrupted = True
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    pid_file = tmp_path / "child.pid"
                    if pid_file.exists() and pid_file.read_text().strip():
                        break
                    time.sleep(0.01)
                raise KeyboardInterrupt
            return original_wait(process, *args, **kwargs)

        monkeypatch.setattr(original_popen, "wait", wait)
    command = subprocess.list2cmdline([sys.executable, str(script), mode])
    try:
        started = time.monotonic()
        if mode == "interrupt":
            with pytest.raises(KeyboardInterrupt):
                run_validation_commands(
                    (command,),
                    repo_root=tmp_path,
                    timeout_seconds=0.8,
                    progress_callback=lambda _: None,
                )
            result = None
        else:
            result = run_validation_commands(
                (command,),
                repo_root=tmp_path,
                timeout_seconds=0.8,
                progress_callback=lambda _: None,
            )[0]
        elapsed = time.monotonic() - started
        pid_text = (tmp_path / "child.pid").read_text().strip()
        child_pid = int(pid_text)
        until = time.monotonic() + 0.5
        while descendant_running(child_pid) and time.monotonic() < until:
            time.sleep(0.01)
        descendant_alive = descendant_running(child_pid)
    finally:
        for job in jobs:
            assert job.stop(2)
        if os.name != "nt":
            for process in processes:
                try:
                    cast(Any, os).killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        for process in processes:
            process.wait(timeout=3)
    if result is not None:
        assert result.status == (
            "passed" if mode == "root_exit" else "failed" if mode == "root_failure" else "timeout"
        )
        assert result.returncode == (
            3 if mode == "root_failure" else 0 if mode == "root_exit" else None
        )
        assert result.executable == sys.executable
        assert "validator started" in result.stdout_preview
        assert "diagnostic stderr" in result.stderr_preview
    assert elapsed < 3.5
    assert not descendant_alive


def test_cleanup_failure_is_not_success_or_failed_start_and_stops_admissions(tmp_path):
    from ai_agent.validation_process import ValidationCleanupError

    calls = []

    def runner(arguments, **kwargs):
        calls.append(arguments)
        raise ValidationCleanupError("Validation process-tree cleanup could not be verified")

    results = run_validation_commands(
        ("validator", "must-not-start"),
        repo_root=tmp_path,
        timeout_seconds=1,
        runner=runner,
        progress_callback=lambda _: None,
    )
    assert calls == [["validator"]]
    assert len(results) == 1 and results[0].status == "failed"
    assert "cleanup could not be verified" in results[0].failure_reason


@pytest.mark.skipif(os.name != "nt", reason="Windows suspended ownership admission")
@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_ownership_failure_does_not_execute_workspace_code(tmp_path, monkeypatch, cleanup_fails):
    from ai_agent import validation_process

    script = tmp_path / "must_not_run.py"
    script.write_text("from pathlib import Path;Path('executed').touch()")
    original_popen = subprocess.Popen
    processes = []

    def start(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        processes.append(process)
        return process

    def reject(_process):
        raise OSError("Synthetic ownership setup failure")

    monkeypatch.setattr(subprocess, "Popen", start)
    monkeypatch.setattr("ai_agent.validation_process.WindowsJob", reject)
    if cleanup_fails:
        original_stop = validation_process._stop

        def cleanup(process, job):
            original_stop(process, job)
            raise validation_process.ValidationCleanupError(
                "Synthetic cleanup could not be verified"
            )

        monkeypatch.setattr(validation_process, "_stop", cleanup)
    results = run_validation_commands(
        (subprocess.list2cmdline([sys.executable, str(script)]),)
        + (("must-not-start",) if cleanup_fails else ()),
        repo_root=tmp_path,
        timeout_seconds=1,
        progress_callback=lambda _: None,
    )
    assert len(results) == 1
    result = results[0]
    assert result.status == ("failed" if cleanup_fails else "failed_to_start")
    assert (
        "cleanup could not be verified" if cleanup_fails else "ownership setup failure"
    ) in result.failure_reason
    assert len(processes) == 1 and processes[0].poll() is not None
    assert not (tmp_path / "executed").exists()


def test_owned_runner_environment_and_bounded_capture_without_real_child(tmp_path, monkeypatch):
    from ai_agent import validation_process

    class Process:
        pid = 123
        returncode = -1

        def wait(self, **kwargs):
            raise subprocess.TimeoutExpired("synthetic", 1)

    process = Process()
    stopped = []

    def start(arguments, **kwargs):
        assert kwargs["env"] == {"OWNED_TEST_VALUE": "context-value"}
        kwargs["stdout"].write(b"x" * 20_000 + b"final progress")
        kwargs["stderr"].write(b"stderr progress")
        return process

    monkeypatch.setattr(subprocess, "Popen", start)
    monkeypatch.setattr(validation_process, "_stop", lambda p, job: stopped.append(p))
    # Exercise the platform-independent capture path without a native process.
    from types import SimpleNamespace

    monkeypatch.setattr(
        validation_process, "os", SimpleNamespace(name="posix", SEEK_END=os.SEEK_END)
    )
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        validation_process.run_validation_process(
            ["synthetic"], cwd=tmp_path, timeout=1, env={"OWNED_TEST_VALUE": "context-value"}
        )
    assert stopped == [process]
    output = cast(str, caught.value.stdout)
    assert isinstance(output, str)
    assert len(output.encode()) <= 16_000
    assert "final progress" in output
    assert caught.value.stderr == "stderr progress"
