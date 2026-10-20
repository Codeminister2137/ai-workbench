#Requires -Version 5.1
#Requires -PSEdition Desktop

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch]$Sleep,
    [switch]$CancelAll,
    [switch]$Renew,
    [switch]$Rolling,
    [datetimeoffset]$ProtectedUntilUtc = [datetimeoffset]::MinValue,
    [string]$ControlDirectory = "",
    [ValidateRange(0, 600)]
    [int]$DelaySeconds = 0,
    [datetimeoffset]$SleepAtUtc = [datetimeoffset]::MinValue,
    [string]$ReceiptPath = "",
    [string]$CancelPath = "",
    [datetimeoffset]$NotBeforeUtc = [datetimeoffset]::MinValue
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $ControlDirectory) {
    $ControlDirectory = Join-Path $PSScriptRoot '../artifacts/workstation-sleep-control'
}
$ControlDirectory = [IO.Path]::GetFullPath($ControlDirectory)
$cancelAllPath = Join-Path $ControlDirectory 'cancel-all.txt'
function Read-ControlText([string]$Path) {
    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read,
        ([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
    $reader = [IO.StreamReader]::new($stream)
    try { return $reader.ReadToEnd() } finally { $reader.Dispose() }
}
function Read-CancelGeneration {
    if (Test-Path -LiteralPath $cancelAllPath) {
        return Read-ControlText $cancelAllPath
    }
    return ''
}
function Write-AtomicText([string]$Path, [string]$Text) {
    $temporary = "$Path.$([guid]::NewGuid()).tmp"
    try {
        [IO.File]::WriteAllText($temporary, $Text)
        if (Test-Path -LiteralPath $Path) {
            # Windows PowerShell converts plain $null to an invalid empty backup path.
            [IO.File]::Replace($temporary, $Path, [NullString]::Value)
        } else {
            [IO.File]::Move($temporary, $Path)
        }
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary }
    }
}
if (@($Sleep, $CancelAll, $Renew | Where-Object { $_ }).Count -gt 1) {
    throw 'Choose only one of Sleep, CancelAll or Renew.'
}
if ($CancelAll) {
    if (-not $PSCmdlet.ShouldProcess('All repository sleep timers', 'Cancel')) { return }
    [IO.Directory]::CreateDirectory($ControlDirectory) | Out-Null
    Write-AtomicText $cancelAllPath ([guid]::NewGuid().ToString())
    $pending = @()
    foreach ($registration in Get-ChildItem -LiteralPath $ControlDirectory -Filter 'timer-*.json') {
        $record = Read-ControlText $registration.FullName | ConvertFrom-Json
        $pending += $record.receipt_path
    }
    $waitUntil = [datetimeoffset]::UtcNow.AddSeconds(5)
    do {
        $pending = @($pending | Where-Object {
            if (-not (Test-Path -LiteralPath $_)) { return $true }
            $state = Read-ControlText $_ | ConvertFrom-Json
            $state.status -eq 'sleep_scheduled'
        })
        if ($pending.Count -eq 0) { break }
        Start-Sleep -Milliseconds 100
    } while ([datetimeoffset]::UtcNow -lt $waitUntil)
    if ($pending.Count) { throw "Cancellation sent; acknowledgement missing for: $($pending -join ', ')" }
    Write-Output 'sleep_status: cancellation acknowledged; no registered timer remains pending (submitted power requests cannot be undone)'
    return
}
if ($Renew) {
    $record = Read-ControlText $ReceiptPath | ConvertFrom-Json
    if (-not $record.lease_path -or $record.status -ne 'sleep_scheduled') {
        throw 'Only an active rolling timer can be renewed.'
    }
    if ((Read-CancelGeneration) -ne $record.cancel_generation -or
        ($record.cancel_path -and (Test-Path -LiteralPath $record.cancel_path))) {
        throw 'Cancelled timers cannot be renewed; start a new authorized window instead.'
    }
    $deadline = [datetimeoffset]::Parse($record.window_deadline_utc)
    if ([datetimeoffset]::UtcNow -ge [datetimeoffset]::Parse($record.planned_sleep_utc)) {
        throw 'Expired leases cannot be renewed.'
    }
    if ($ProtectedUntilUtc -gt $deadline) { throw 'Protected work exceeds the fixed deadline.' }
    $nextDue = [datetimeoffset]::UtcNow.AddMinutes(30)
    # A routine refresh must not shorten protection already granted to owned work.
    if ([datetimeoffset]::Parse($record.planned_sleep_utc) -gt $nextDue) {
        $nextDue = [datetimeoffset]::Parse($record.planned_sleep_utc)
    }
    if ($ProtectedUntilUtc -gt $nextDue) { $nextDue = $ProtectedUntilUtc }
    if ($nextDue -gt $deadline) { $nextDue = $deadline }
    if ($record.not_before_utc -and $nextDue -lt [datetimeoffset]::Parse($record.not_before_utc)) {
        $nextDue = [datetimeoffset]::Parse($record.not_before_utc)
    }
    if ($PSCmdlet.ShouldProcess($record.lease_path, 'Renew sleep lease')) {
        Write-AtomicText $record.lease_path ($nextDue.ToUniversalTime().ToString('o'))
        Write-Output "sleep_lease_submitted_utc: $($nextDue.ToString('o')); verify receipt acknowledgement"
    }
    return
}

if (-not $Sleep) {
    Write-Output "sleep_status: planned; pass -Sleep after saving work and finishing owned tasks"
    return
}

function Assert-WorkWindowEnded {
    if ([datetimeoffset]::UtcNow -lt $NotBeforeUtc) {
        throw "The unattended work window has not ended. Sleep is refused before $($NotBeforeUtc.ToUniversalTime().ToString('o'))."
    }
}

$absoluteSchedule = $PSBoundParameters.ContainsKey('SleepAtUtc')
if ($Rolling -and -not $absoluteSchedule) { throw 'Rolling requires a fixed SleepAtUtc deadline.' }
if ($absoluteSchedule) {
    if ($PSBoundParameters.ContainsKey('DelaySeconds')) {
        throw 'Choose SleepAtUtc or DelaySeconds, not both.'
    }
    if ($SleepAtUtc -le [datetimeoffset]::UtcNow) {
        throw 'SleepAtUtc must be a future timestamp; expired windows cannot be scheduled.'
    }
    if ($SleepAtUtc -lt $NotBeforeUtc) {
        throw 'SleepAtUtc cannot precede NotBeforeUtc.'
    }
    if (-not $ReceiptPath -or -not $CancelPath) {
        throw 'Absolute scheduling requires ReceiptPath and CancelPath.'
    }
} else {
    Assert-WorkWindowEnded
}
$dueUtc = if ($absoluteSchedule) { $SleepAtUtc.ToUniversalTime() } else {
    [datetimeoffset]::UtcNow.AddSeconds($DelaySeconds)
}
$windowDeadline = $dueUtc
if ($Rolling) {
    if ($ProtectedUntilUtc -gt $windowDeadline) { throw 'Protected work exceeds the fixed deadline.' }
    $dueUtc = [datetimeoffset]::UtcNow.AddMinutes(30)
    if ($ProtectedUntilUtc -gt $dueUtc) { $dueUtc = $ProtectedUntilUtc }
    if ($dueUtc -gt $windowDeadline) { $dueUtc = $windowDeadline }
    if ($dueUtc -lt $NotBeforeUtc) { $dueUtc = $NotBeforeUtc }
}
Add-Type -AssemblyName System.Windows.Forms
if (-not $PSCmdlet.ShouldProcess("This Windows computer", "Request sleep without forcing applications or disabling wake events")) {
    return
}

if ($ReceiptPath -and (Test-Path -LiteralPath $ReceiptPath)) {
    throw "Sleep receipt already exists; choose a new path to preserve earlier evidence."
}
$cancelGeneration = Read-CancelGeneration
$leasePath = if ($Rolling) { "$([IO.Path]::GetFullPath($ReceiptPath)).lease" } else { '' }
if ($leasePath -and (Test-Path -LiteralPath $leasePath)) { throw 'Lease path already exists.' }
[IO.Directory]::CreateDirectory($ControlDirectory) | Out-Null
if ($leasePath) {
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($leasePath)) | Out-Null
    Write-AtomicText $leasePath ($dueUtc.ToString('o'))
}
if ($ReceiptPath) {
    $registrationPath = Join-Path $ControlDirectory "timer-$([guid]::NewGuid()).json"
    Write-AtomicText $registrationPath (@{receipt_path = [IO.Path]::GetFullPath($ReceiptPath)} | ConvertTo-Json)
}

$warsawTimeZone = [TimeZoneInfo]::FindSystemTimeZoneById("Central European Standard Time")
$sleepTransitionTimesUtc = [ordered]@{}
$sleepTransitionTimesWarsaw = [ordered]@{}
$plannedSleepWarsaw = [TimeZoneInfo]::ConvertTimeFromUtc(
    $dueUtc.UtcDateTime, $warsawTimeZone
).ToString("yyyy-MM-dd HH:mm:ss")

function Write-SleepReceipt([string]$Status) {
    $transitionUtc = [datetime]::UtcNow
    if (-not $sleepTransitionTimesUtc.Contains($Status)) {
        $sleepTransitionTimesUtc[$Status] = $transitionUtc.ToString("o")
        $sleepTransitionTimesWarsaw[$Status] = [TimeZoneInfo]::ConvertTimeFromUtc(
            $transitionUtc, $warsawTimeZone
        ).ToString("yyyy-MM-dd HH:mm:ss")
    }
    if ($ReceiptPath) {
        $receiptFile = [System.IO.Path]::GetFullPath($ReceiptPath)
        [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($receiptFile)) | Out-Null
        [ordered]@{
            status = $Status
            recorded_utc = $transitionUtc.ToString("o")
            time_zone = "Europe/Warsaw"
            planned_sleep_warsaw = $plannedSleepWarsaw
            planned_sleep_utc = $dueUtc.ToString("o")
            window_deadline_utc = $windowDeadline.ToString('o')
            lease_path = $leasePath
            cancel_generation = $cancelGeneration
            not_before_utc = if ($NotBeforeUtc -eq [datetimeoffset]::MinValue) {
                $null
            } else {
                $NotBeforeUtc.ToUniversalTime().ToString("o")
            }
            transition_times_utc = $sleepTransitionTimesUtc
            transition_times_warsaw = $sleepTransitionTimesWarsaw
            process_id = $PID
            cancel_path = $CancelPath
            force = $false
            wake_events_disabled = $false
        } | ConvertTo-Json | ForEach-Object { Write-AtomicText $receiptFile $_ }
    }
}

Write-SleepReceipt "sleep_scheduled"
Write-Output "sleep_planned_warsaw: $plannedSleepWarsaw (Europe/Warsaw; estimated)"
while ($true) {
    if ((Read-CancelGeneration) -ne $cancelGeneration -or
        ($CancelPath -and (Test-Path -LiteralPath $CancelPath))) {
        Write-SleepReceipt "sleep_cancelled"
        Write-Output "sleep_status: cancelled"
        return
    }
    if ($leasePath) {
        $leaseDue = [datetimeoffset]::Parse((Read-ControlText $leasePath))
        if ($leaseDue -gt $windowDeadline -or $leaseDue -lt $NotBeforeUtc) {
            throw 'Invalid lease: outside fixed deadline or not-before guard.'
        }
        if ($leaseDue -ne $dueUtc) {
            $dueUtc = $leaseDue
            $plannedSleepWarsaw = [TimeZoneInfo]::ConvertTimeFromUtc(
                $dueUtc.UtcDateTime, $warsawTimeZone
            ).ToString('yyyy-MM-dd HH:mm:ss')
            Write-SleepReceipt 'sleep_scheduled'
        }
    }
    if ([datetimeoffset]::UtcNow -ge $dueUtc) { break }
    Start-Sleep -Seconds 1
}
if ((Read-CancelGeneration) -ne $cancelGeneration -or
    ($CancelPath -and (Test-Path -LiteralPath $CancelPath))) {
    Write-SleepReceipt "sleep_cancelled"
    Write-Output "sleep_status: cancelled"
    return
}
Assert-WorkWindowEnded
Write-SleepReceipt "sleep_requested"
Write-Output "sleep_requested_warsaw: $($sleepTransitionTimesWarsaw['sleep_requested']) (Europe/Warsaw)"
Write-Output "sleep_status: requesting"
$accepted = [System.Windows.Forms.Application]::SetSuspendState(
    [System.Windows.Forms.PowerState]::Suspend, $false, $false
)
if (-not $accepted) {
    Write-SleepReceipt "sleep_request_rejected"
    throw "Windows rejected the sleep request."
}
Write-SleepReceipt "sleep_api_returned_success"
Write-Output "sleep_status: API returned success (may return after wake)"
