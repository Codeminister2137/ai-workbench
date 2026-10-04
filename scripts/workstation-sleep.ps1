#Requires -Version 5.1
#Requires -PSEdition Desktop

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch]$Sleep,
    [ValidateRange(0, 60)]
    [int]$DelaySeconds = 0,
    [string]$ReceiptPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $Sleep) {
    Write-Output "sleep_status: planned; pass -Sleep after saving work and finishing owned tasks"
    return
}

Add-Type -AssemblyName System.Windows.Forms
if (-not $PSCmdlet.ShouldProcess("This Windows computer", "Request sleep without forcing applications or disabling wake events")) {
    return
}

if ($ReceiptPath -and (Test-Path -LiteralPath $ReceiptPath)) {
    throw "Sleep receipt already exists; choose a new path to preserve earlier evidence."
}

function Write-SleepReceipt([string]$Status) {
    if ($ReceiptPath) {
        $receiptFile = [System.IO.Path]::GetFullPath($ReceiptPath)
        [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($receiptFile)) | Out-Null
        [ordered]@{
            status = $Status
            recorded_utc = [datetime]::UtcNow.ToString("o")
            process_id = $PID
            force = $false
            wake_events_disabled = $false
        } | ConvertTo-Json | Set-Content -LiteralPath $receiptFile -Encoding utf8
    }
}

Write-SleepReceipt "sleep_scheduled"
if ($DelaySeconds) {
    Start-Sleep -Seconds $DelaySeconds
}
Write-SleepReceipt "sleep_requested"
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
