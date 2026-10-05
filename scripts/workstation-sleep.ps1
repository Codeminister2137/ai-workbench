#Requires -Version 5.1
#Requires -PSEdition Desktop

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch]$Sleep,
    [ValidateRange(0, 60)]
    [int]$DelaySeconds = 0,
    [string]$ReceiptPath = "",
    [datetimeoffset]$NotBeforeUtc = [datetimeoffset]::MinValue
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $Sleep) {
    Write-Output "sleep_status: planned; pass -Sleep after saving work and finishing owned tasks"
    return
}

function Assert-WorkWindowEnded {
    if ([datetimeoffset]::UtcNow -lt $NotBeforeUtc) {
        throw "The unattended work window has not ended. Sleep is refused before $($NotBeforeUtc.ToUniversalTime().ToString('o'))."
    }
}

Assert-WorkWindowEnded
Add-Type -AssemblyName System.Windows.Forms
if (-not $PSCmdlet.ShouldProcess("This Windows computer", "Request sleep without forcing applications or disabling wake events")) {
    return
}

if ($ReceiptPath -and (Test-Path -LiteralPath $ReceiptPath)) {
    throw "Sleep receipt already exists; choose a new path to preserve earlier evidence."
}

$warsawTimeZone = [TimeZoneInfo]::FindSystemTimeZoneById("Central European Standard Time")
$sleepTransitionTimesUtc = [ordered]@{}
$sleepTransitionTimesWarsaw = [ordered]@{}
$plannedSleepWarsaw = [TimeZoneInfo]::ConvertTimeFromUtc(
    [datetime]::UtcNow.AddSeconds($DelaySeconds), $warsawTimeZone
).ToString("yyyy-MM-dd HH:mm:ss")

function Write-SleepReceipt([string]$Status) {
    $transitionUtc = [datetime]::UtcNow
    $sleepTransitionTimesUtc[$Status] = $transitionUtc.ToString("o")
    $sleepTransitionTimesWarsaw[$Status] = [TimeZoneInfo]::ConvertTimeFromUtc(
        $transitionUtc, $warsawTimeZone
    ).ToString("yyyy-MM-dd HH:mm:ss")
    if ($ReceiptPath) {
        $receiptFile = [System.IO.Path]::GetFullPath($ReceiptPath)
        [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($receiptFile)) | Out-Null
        [ordered]@{
            status = $Status
            recorded_utc = $transitionUtc.ToString("o")
            time_zone = "Europe/Warsaw"
            planned_sleep_warsaw = $plannedSleepWarsaw
            not_before_utc = if ($NotBeforeUtc -eq [datetimeoffset]::MinValue) {
                $null
            } else {
                $NotBeforeUtc.ToUniversalTime().ToString("o")
            }
            transition_times_utc = $sleepTransitionTimesUtc
            transition_times_warsaw = $sleepTransitionTimesWarsaw
            process_id = $PID
            force = $false
            wake_events_disabled = $false
        } | ConvertTo-Json | Set-Content -LiteralPath $receiptFile -Encoding utf8
    }
}

Write-SleepReceipt "sleep_scheduled"
Write-Output "sleep_planned_warsaw: $plannedSleepWarsaw (Europe/Warsaw; estimated)"
if ($DelaySeconds) {
    Start-Sleep -Seconds $DelaySeconds
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
