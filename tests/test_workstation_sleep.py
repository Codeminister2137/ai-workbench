"""Exercise cancellation and time guards without waiting or suspending Windows."""

import json
import subprocess
import sys
import time
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


@pytest.mark.parametrize(
    "arguments,reason",
    [
        ("-SleepAtUtc ([datetimeoffset]::UtcNow.AddSeconds(-1))", "future timestamp"),
        ("-SleepAtUtc ([datetimeoffset]::UtcNow.AddHours(1)) -DelaySeconds 1", "not both"),
        (
            "-SleepAtUtc ([datetimeoffset]::UtcNow.AddHours(1)) "
            "-NotBeforeUtc ([datetimeoffset]::UtcNow.AddHours(2))",
            "cannot precede",
        ),
    ],
)
def test_invalid_absolute_schedule_refused(tmp_path, arguments, reason):
    receipt = tmp_path / "receipt.json"
    result = run_helper(
        f"& '{SCRIPT.as_posix()}' -Sleep {arguments} -WhatIf "
        f"-ReceiptPath '{receipt.as_posix()}' -CancelPath '{tmp_path / 'cancel'}'"
    )
    assert result.returncode != 0
    assert reason in result.stderr
    assert not receipt.exists()


def test_separate_future_timer_reports_and_accepts_owner_cancellation(tmp_path):
    receipt = tmp_path / "receipt.json"
    marker = tmp_path / "cancel"
    # A hard safety shim forbids suspension even if cancellation fails.
    command = f"""
$source = [IO.File]::ReadAllText('{SCRIPT.as_posix()}')
$powerCall = '$accepted = [System.Windows.Forms.Application]::SetSuspendState('
if (-not $source.Contains($powerCall)) {{ throw 'Suspend safety shim no longer matches' }}
$source = $source.Replace($powerCall, "throw 'Suspend forbidden in tests'`n" + $powerCall)
& ([scriptblock]::Create($source)) -Sleep `
    -SleepAtUtc ([datetimeoffset]::UtcNow.AddHours(1)) `
    -NotBeforeUtc ([datetimeoffset]::UtcNow.AddMinutes(30)) `
    -ReceiptPath '{receipt.as_posix()}' -CancelPath '{marker.as_posix()}'
"""
    process = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        end = time.monotonic() + 10
        while time.monotonic() < end:
            try:
                saved = json.loads(receipt.read_text(encoding="utf-8-sig"))
                break
            except (FileNotFoundError, json.JSONDecodeError):
                time.sleep(0.05)
        else:
            pytest.fail("Separate timer did not publish its scheduling receipt")
        assert saved["status"] == "sleep_scheduled"
        assert saved["process_id"] == process.pid
        assert saved["planned_sleep_utc"] > saved["not_before_utc"]
        marker.touch()
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, stderr
        assert "cancelled" in stdout
        saved = json.loads(receipt.read_text(encoding="utf-8-sig"))
        assert saved["status"] == "sleep_cancelled"
        assert "sleep_requested" not in saved["transition_times_utc"]
    finally:
        if process.poll() is None:
            marker.touch()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


def test_absolute_deadline_reaches_mock_power_call_only_after_due(tmp_path):
    receipt = tmp_path / "receipt.json"
    command = f"""
$source = [IO.File]::ReadAllText('{SCRIPT.as_posix()}')
$powerCall = @'
$accepted = [System.Windows.Forms.Application]::SetSuspendState(
    [System.Windows.Forms.PowerState]::Suspend, $false, $false
)
'@
$source = $source.Replace("`r`n", "`n")
$powerCall = $powerCall.Replace("`r`n", "`n")
if (-not $source.Contains($powerCall)) {{ throw 'Suspend safety shim no longer matches' }}
$source = $source.Replace($powerCall, '$accepted = $false')
& ([scriptblock]::Create($source)) -Sleep `
    -SleepAtUtc ([datetimeoffset]::UtcNow.AddSeconds(2)) `
    -ReceiptPath '{receipt.as_posix()}' -CancelPath '{tmp_path / "cancel"}'
"""
    result = run_helper(command)
    assert result.returncode != 0
    assert "Windows rejected the sleep request" in result.stderr
    saved = json.loads(receipt.read_text(encoding="utf-8-sig"))
    assert saved["status"] == "sleep_request_rejected"
    assert saved["transition_times_utc"]["sleep_requested"] >= saved["planned_sleep_utc"]


def test_absolute_schedule_requires_owner_cancellation_path(tmp_path):
    result = run_helper(
        f"& '{SCRIPT.as_posix()}' -Sleep -WhatIf "
        "-SleepAtUtc ([datetimeoffset]::UtcNow.AddHours(1)) "
        f"-ReceiptPath '{tmp_path / 'receipt.json'}'"
    )
    assert result.returncode != 0
    assert "requires ReceiptPath and CancelPath" in result.stderr
