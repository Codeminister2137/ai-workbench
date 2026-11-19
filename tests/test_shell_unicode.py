"""Real Windows shell round trips must preserve document text, not just ASCII."""

from __future__ import annotations

import sys
import time

import pytest
from ai_agent.tools.background import JobManager
from ai_agent.tools.base import ToolContext
from ai_agent.tools.shell import RunCommandTool


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell 5.1 pipe regression")
@pytest.mark.parametrize("background", [False, True])
def test_powershell_unicode_pipe_file_and_output(tmp_path, background):
    text = "Zażółć gęślą jaźń; Bielsko-Biała — “źródło” → ŁÓŚ"
    # The program comes from a UTF-8 file, while its input crosses the native
    # PowerShell pipe that previously replaced non-ASCII characters with '?'.
    (tmp_path / "copy.py").write_text(
        "import pathlib, sys\n"
        "text = sys.stdin.read().rstrip('\\r\\n')\n"
        "pathlib.Path('result.md').write_text(text, encoding='utf-8')\n"
        "print(text)\n"
        "print(text, file=sys.stderr)\n",
        encoding="utf-8",
    )
    executable = sys.executable.replace("'", "''")
    command = f"'{text}' | & '{executable}' copy.py"
    context = ToolContext(tmp_path)
    if background:
        manager = JobManager(tmp_path / "jobs")
        job = manager.start(command, tmp_path, context.command_environment())
        try:
            state = manager.poll(job.id)
            output = state["stdout"] + state["stderr"]
            deadline = time.monotonic() + 20
            while state["status"] == "running" and time.monotonic() < deadline:
                time.sleep(0.05)
                state = manager.poll(job.id)
                output += state["stdout"] + state["stderr"]
            assert state["status"] == "done", state
            assert state["exit_code"] == 0, state
        finally:
            manager.stop(job.id)
    else:
        result = RunCommandTool().execute({"command": command, "timeout_seconds": 20}, context)
        assert not result.is_error, result.output
        output = result.output
    assert output.count(text) == 2, repr(output)
    assert (tmp_path / "result.md").read_bytes() == text.encode("utf-8")
