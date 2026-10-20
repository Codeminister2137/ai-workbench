"""Exercise cancellation and time guards without waiting or suspending Windows."""

import json
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
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
    -ControlDirectory '{tmp_path / "control"}' `
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
    -ControlDirectory '{tmp_path / "control"}' `
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
    -ControlDirectory '{tmp_path / "control"}' `
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


def wait_receipt(path, predicate):
    end = time.monotonic() + 10
    while time.monotonic() < end:
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
            if predicate(value):
                return value
        except (FileNotFoundError, json.JSONDecodeError, PermissionError):
            pass
        time.sleep(0.05)
    pytest.fail(f"Receipt acknowledgement missing: {path}")


@contextmanager
def safe_timer(tmp_path, control, *, rolling=False, deadline_minutes=120):
    tmp_path.mkdir(parents=True, exist_ok=True)
    receipt = tmp_path / "receipt.json"
    marker = tmp_path / "cancel"
    command = f"""
$ErrorActionPreference = 'Stop'
$source = [IO.File]::ReadAllText('{SCRIPT.as_posix()}')
$powerCall = '$accepted = [System.Windows.Forms.Application]::SetSuspendState('
if (-not $source.Contains($powerCall)) {{ throw 'Suspend safety shim no longer matches' }}
$source = $source.Replace($powerCall, "throw 'Suspend forbidden in tests'`n" + $powerCall)
& ([scriptblock]::Create($source)) -Sleep {"-Rolling" if rolling else ""} `
    -ControlDirectory '{control.as_posix()}' `
    -SleepAtUtc ([datetimeoffset]::UtcNow.AddMinutes({deadline_minutes})) `
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
        saved = wait_receipt(receipt, lambda value: value["status"] == "sleep_scheduled")
        yield process, receipt, saved
    finally:
        marker.touch()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=3)


def test_fixed_command_cancels_multiple_timers_from_another_directory(tmp_path):
    repo = tmp_path / "repository with spaces"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy2(SCRIPT, repo / "scripts" / SCRIPT.name)
    wrapper = repo / "cancel-sleep.cmd"
    shutil.copy2(SCRIPT.parent.parent / wrapper.name, wrapper)
    control = repo / "artifacts" / "workstation-sleep-control"
    with (
        safe_timer(tmp_path / "one", control) as first,
        safe_timer(tmp_path / "two", control, rolling=True) as second,
    ):
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", str(wrapper)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stderr
        for process, receipt, _ in (first, second):
            saved = wait_receipt(receipt, lambda value: value["status"] == "sleep_cancelled")
            assert "sleep_requested" not in saved["transition_times_utc"]
            process.wait(timeout=5)
            assert process.returncode == 0
        # Idempotent, with no path or timer identifier supplied by the owner.
        assert (
            run_helper(f"& '{(repo / 'scripts' / SCRIPT.name).as_posix()}' -CancelAll").returncode
            == 0
        )


def test_rolling_renewal_protects_long_work_without_replacing_process(tmp_path):
    control = tmp_path / "control"
    with safe_timer(tmp_path / "timer", control, rolling=True) as (process, receipt, initial):
        first_due = datetime.fromisoformat(initial["planned_sleep_utc"])
        assert 29 * 60 < (first_due - datetime.now(UTC)).total_seconds() <= 30 * 60
        result = run_helper(
            f"& '{SCRIPT.as_posix()}' -Renew -ReceiptPath '{receipt.as_posix()}' "
            f"-ControlDirectory '{control.as_posix()}' "
            "-ProtectedUntilUtc ([datetimeoffset]::UtcNow.AddMinutes(50))"
        )
        assert result.returncode == 0, result.stderr
        renewed = wait_receipt(
            receipt, lambda value: value["planned_sleep_utc"] != initial["planned_sleep_utc"]
        )
        assert datetime.fromisoformat(renewed["planned_sleep_utc"]) > first_due + timedelta(
            minutes=19
        )
        assert renewed["process_id"] == process.pid
        assert renewed["window_deadline_utc"] == initial["window_deadline_utc"]
        assert (
            renewed["transition_times_utc"]["sleep_scheduled"]
            == initial["transition_times_utc"]["sleep_scheduled"]
        )
        refresh = run_helper(
            f"& '{SCRIPT.as_posix()}' -Renew -ReceiptPath '{receipt.as_posix()}' "
            f"-ControlDirectory '{control.as_posix()}'"
        )
        assert refresh.returncode == 0, refresh.stderr
        assert Path(renewed["lease_path"]).read_text() == renewed["planned_sleep_utc"]
        refused = run_helper(
            f"& '{SCRIPT.as_posix()}' -Renew -ReceiptPath '{receipt.as_posix()}' "
            f"-ControlDirectory '{control.as_posix()}' "
            "-ProtectedUntilUtc ([datetimeoffset]::UtcNow.AddHours(3))"
        )
        assert refused.returncode != 0
        assert "exceeds the fixed deadline" in refused.stderr
        cancelled = run_helper(
            f"& '{SCRIPT.as_posix()}' -CancelAll -ControlDirectory '{control.as_posix()}'"
        )
        assert cancelled.returncode == 0, cancelled.stderr
        refused = run_helper(
            f"& '{SCRIPT.as_posix()}' -Renew -ReceiptPath '{receipt.as_posix()}' "
            f"-ControlDirectory '{control.as_posix()}'"
        )
        assert refused.returncode != 0
        assert "active rolling timer" in refused.stderr


def test_rolling_initial_due_is_capped_at_original_deadline(tmp_path):
    with safe_timer(
        tmp_path / "timer", tmp_path / "control", rolling=True, deadline_minutes=20
    ) as (_, _, saved):
        assert saved["planned_sleep_utc"] == saved["window_deadline_utc"]


def test_cancel_all_whatif_does_not_create_control_state(tmp_path):
    control = tmp_path / "control"
    result = run_helper(
        f"& '{SCRIPT.as_posix()}' -CancelAll -WhatIf -ControlDirectory '{control.as_posix()}'"
    )
    assert result.returncode == 0, result.stderr
    assert not control.exists()


def test_renewal_cannot_revive_an_expired_lease(tmp_path):
    receipt = tmp_path / "expired.json"
    lease = tmp_path / "lease"
    lease.write_text("original")
    receipt.write_text(
        json.dumps(
            {
                "lease_path": str(lease),
                "status": "sleep_scheduled",
                "cancel_generation": "",
                "cancel_path": "",
                "window_deadline_utc": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "planned_sleep_utc": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
            }
        )
    )
    result = run_helper(
        f"& '{SCRIPT.as_posix()}' -Renew -ReceiptPath '{receipt.as_posix()}' "
        f"-ControlDirectory '{tmp_path / 'control'}'"
    )
    assert result.returncode != 0
    assert "Expired leases" in result.stderr
    assert lease.read_text() == "original"


def test_tampered_lease_outside_deadline_stops_without_power_request(tmp_path):
    with safe_timer(tmp_path / "timer", tmp_path / "control", rolling=True) as (
        process,
        receipt,
        saved,
    ):
        Path(saved["lease_path"]).write_text((datetime.now(UTC) + timedelta(days=1)).isoformat())
        _, stderr = process.communicate(timeout=5)
        assert process.returncode != 0
        assert "outside fixed deadline" in stderr
        current = json.loads(receipt.read_text(encoding="utf-8-sig"))
        assert "sleep_requested" not in current["transition_times_utc"]
