"""Authentication preflight must own and clean its native client descendants."""

import json
import os
import subprocess
import sys
import time

import pytest
from ai_provider.acceptance_processes import process_identity
from ai_provider.agent_readiness import _copilot_authenticated
from ai_provider.process_ownership import WindowsJob


@pytest.mark.skipif(os.name != "nt", reason="Windows retained process-tree ownership")
@pytest.mark.parametrize("mode", ["success", "hang", "exit_root"])
def test_copilot_auth_does_not_leave_a_descendant(monkeypatch, tmp_path, mode):
    script = tmp_path / "auth_client.py"
    script.write_text(
        """
import json, subprocess, sys, time
from pathlib import Path
directory = Path(sys.argv[1])
mode = sys.argv[2]
length = int(sys.stdin.buffer.readline().split(b':', 1)[1])
sys.stdin.buffer.readline()
request = json.loads(sys.stdin.buffer.read(length))
(directory / 'request.json').write_text(json.dumps(request))
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
(directory / 'child.pid').write_text(str(child.pid))
if mode == 'exit_root':
    sys.exit(0)
if mode == 'hang':
    time.sleep(30)
body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {
    'isAuthenticated': True, 'email': 'private@example.invalid'
}}).encode()
sys.stdout.buffer.write(f'Content-Length: {len(body)}\\r\\n\\r\\n'.encode() + body)
sys.stdout.buffer.flush()
time.sleep(30)
""",
        encoding="utf-8",
    )
    original_popen = subprocess.Popen
    test_jobs, processes, commands = [], [], []

    def start(command, **kwargs):
        commands.append(command)
        process = original_popen([sys.executable, "-u", str(script), str(tmp_path), mode], **kwargs)
        processes.append(process)
        # The synthetic child waits for its request before spawning. Retain outer
        # test ownership so even the pre-fix regression cannot leak a descendant.
        test_jobs.append(WindowsJob(process))
        return process

    monkeypatch.setattr(subprocess, "Popen", start)
    try:
        started = time.monotonic()
        authenticated = _copilot_authenticated("synthetic-copilot", 1)
        elapsed = time.monotonic() - started
        child_pid = int((tmp_path / "child.pid").read_text())
        descendant_alive = process_identity(child_pid) is not None
        request = json.loads((tmp_path / "request.json").read_text())
    finally:
        for job in test_jobs:
            assert job.stop(2)
        for process in processes:
            process.wait(timeout=2)
    assert authenticated is (mode == "success")
    assert elapsed < 4
    assert not descendant_alive
    assert processes[0].stdin.closed and processes[0].stdout.closed
    assert request == {"jsonrpc": "2.0", "id": 1, "method": "auth.getStatus", "params": {}}
    assert commands[0][1:] == ("--headless", "--no-auto-update", "--log-level", "none", "--stdio")
