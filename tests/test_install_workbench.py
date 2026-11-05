"""Regression tests for scripts/install-workbench.ps1.

Mirrors the sibling remote-operator wrapper-test approach: static guards over
the installer text (the EAP lesson, the apostrophe-injection lesson, the
always-print-manual-start lesson) plus a few live probes of safe,
side-effect-free functions via dot-sourcing. Nothing here registers scheduled
tasks, installs software, or starts servers.
"""

from __future__ import annotations

import re
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

INSTALL_PS1 = Path(__file__).resolve().parent.parent / "scripts" / "install-workbench.ps1"
POWERSHELL = shutil.which("powershell")

needs_powershell = pytest.mark.skipif(
    POWERSHELL is None, reason="powershell.exe is required to probe the installer"
)


def _text() -> str:
    return INSTALL_PS1.read_text(encoding="utf-8")


def _template() -> str:
    text = _text()
    match = re.search(r"\$template = @'\n(.*?)\n'@", text, re.DOTALL)
    assert match, "wrapper template block not found in scripts/install-workbench.ps1"
    return match.group(1)


def _run_ps(script: str, *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    assert POWERSHELL is not None
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


class TestStaticGuards:
    def test_stderr_must_not_abort_dashboard(self):
        template = _template()
        invoke = template.index("& $VenvPython")
        strict = template.index("$ErrorActionPreference = 'Stop'")
        relaxed = template.index("$ErrorActionPreference = 'Continue'")
        assert strict < relaxed, "setup validation must stay strict"
        assert relaxed < invoke, "stderr must be non-fatal before the dashboard starts"

    def test_wrapper_escapes_apostrophes_in_paths(self):
        text = _text()
        assert '.Replace("\'", "\'\'")' in text

    def test_summary_always_prints_manual_start(self):
        text = _text()
        assert "START IT YOURSELF" in text
        assert r".\.runtime\start-dashboard.ps1" in text

    def test_port_probe_waits_thirty_seconds(self):
        text = _text()
        assert "for ($i = 0; $i -lt 30; $i++)" in text
        assert "Test-ServePort $Port" in text

    def test_uv_and_ffmpeg_offers_with_path_refresh(self):
        text = _text()
        assert "function Find-UvCommand" in text
        assert "function Find-FfmpegCommand" in text
        assert "function Install-Uv" in text
        assert "function Install-Ffmpeg" in text
        assert "GetEnvironmentVariable('Path', 'Machine')" in text
        assert "ffmpeg was already installed; using it." in text

    def test_tailscale_is_opt_out(self):
        text = _text()
        assert "[switch]$NoTailscale" in text
        assert "function Write-TailscaleSkipped" in text
        assert "work on THIS PC" in text

    def test_local_first_no_password_no_docker(self):
        text = _text()
        assert "OPERATOR_ACCESS_TOKEN" not in text
        assert "New-AccessToken" not in text
        assert "Docker.DockerDesktop" not in text
        assert "Install Docker" not in text
        assert "localhost-trust" in text

    def test_uninstall_keeps_data(self):
        text = _text()
        assert "function Invoke-Uninstall" in text
        assert "apps/workbench_dashboard/data" in text

    def test_dot_source_guard(self):
        text = _text()
        assert "if ($MyInvocation.InvocationName -ne '.')" in text


class TestLiveProbes:
    @needs_powershell
    def test_script_parses_without_errors(self):
        script = (
            "$e = $null; $t = $null; "
            f"[void][System.Management.Automation.PSParser]::Tokenize("
            f"[System.IO.File]::ReadAllText('{INSTALL_PS1}'), [ref]$e); "
            "$e.Count"
        )
        proc = _run_ps(script)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "0", proc.stdout

    @needs_powershell
    def test_find_python_returns_working_interpreter(self):
        proc = _run_ps(f". '{INSTALL_PS1}'; Find-Python")
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip().lower().endswith(".exe")

    @needs_powershell
    def test_closed_port_probes_false(self):
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        proc = _run_ps(f". '{INSTALL_PS1}'; Test-ServePort {port}")
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "False"

    @needs_powershell
    def test_generated_wrapper_parses_and_targets_dashboard(self, tmp_path):
        root = tmp_path / "O'Brien-root"
        root.mkdir()
        quoted_root = str(root).replace("'", "''")
        script = (
            f". '{INSTALL_PS1}'; "
            f"$w = Write-StartWrapper '{quoted_root}' 8766 'C:\\py\\python.exe'; "
            "$w.Path"
        )
        proc = _run_ps(script)
        assert proc.returncode == 0, proc.stderr
        wrapper = Path(proc.stdout.strip())
        assert wrapper.name == "start-dashboard.ps1"
        content = wrapper.read_text(encoding="utf-8")
        assert "O''Brien-root" in content, "apostrophe must be escaped in the wrapper"
        assert "dashboard_web_app.py" in content
        quoted_wrapper = str(wrapper).replace("'", "''")
        parse = _run_ps(
            "$e = $null; "
            "[void][System.Management.Automation.PSParser]::Tokenize("
            f"[System.IO.File]::ReadAllText('{quoted_wrapper}'), [ref]$e); "
            "$e.Count"
        )
        assert parse.returncode == 0, parse.stderr
        assert parse.stdout.strip() == "0", parse.stdout
