"""Exercise cancellation and time guards without waiting or suspending Windows."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows sleep helper")
SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation-sleep.ps1"


def run_helper(command):
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        timeout=20,
    )


@pytest.mark.parametrize("delay,cancel_before", [(0, True), (600, True), (600, False), (1, False)])
def test_cancelled_sleep_never_reaches_suspend(tmp_path, delay, cancel_before):
    marker = tmp_path / "cancel"
    receipt = tmp_path / "receipt.json"
    if cancel_before:
        marker.touch()
    command = f"""
$ErrorActionPreference = 'Stop'
$source = [IO.File]::ReadAllText('{SCRIPT.as_posix()}')
$powerCall = '$accepted = [System.Windows.Forms.Application]::SetSuspendState('
if (-not $source.Contains($powerCall)) {{ throw 'Suspend safety shim no longer matches' }}
$source = $source.Replace($powerCall, "throw 'Suspend forbidden in tests'`n" + $powerCall)
function Start-Sleep {{
    param($Seconds)
    [IO.File]::WriteAllText('{marker.as_posix()}', 'cancel')
}}
& ([scriptblock]::Create($source)) -Sleep -DelaySeconds {delay} `
    -ReceiptPath '{receipt.as_posix()}' -CancelPath '{marker.as_posix()}'
"""
    result = run_helper(command)
    assert result.returncode == 0, result.stderr
    saved = json.loads(receipt.read_text(encoding="utf-8-sig"))
    assert saved["status"] == "sleep_cancelled"
    assert saved["cancel_path"] == marker.as_posix()
    assert "sleep_scheduled" in saved["transition_times_utc"]
    assert "sleep_requested" not in saved["transition_times_utc"]
    assert "sleep_status: cancelled" in result.stdout


def test_ten_minute_delay_can_be_previewed_without_sleep_or_receipt(tmp_path):
    receipt = tmp_path / "receipt.json"
    result = run_helper(
        f"& '{SCRIPT.as_posix()}' -Sleep -DelaySeconds 600 -WhatIf "
        f"-ReceiptPath '{receipt.as_posix()}'"
    )
    assert result.returncode == 0, result.stderr
    assert not receipt.exists()


def test_delay_above_ten_minutes_is_rejected():
    result = run_helper(f"& '{SCRIPT.as_posix()}' -Sleep -DelaySeconds 601 -WhatIf")
    assert result.returncode != 0
    assert "ParameterArgumentValidationError" in result.stderr


def test_future_deadline_still_prevents_sleep(tmp_path):
    receipt = tmp_path / "receipt.json"
    result = run_helper(
        f"& '{SCRIPT.as_posix()}' -Sleep -WhatIf "
        "-NotBeforeUtc ([datetimeoffset]::UtcNow.AddHours(1)) "
        f"-ReceiptPath '{receipt.as_posix()}'"
    )
    assert result.returncode != 0
    assert "Sleep is refused before" in result.stderr
    assert not receipt.exists()
