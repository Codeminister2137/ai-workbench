<#
  Register (or remove) the weekly mail-digest task.

  The task runs scripts/weekly_digest.py with the checkout venv: probe the
  Gmail login, fetch the latest mails, summarize via the hosted no-training
  route, and mail the summary to the owner's own address. A receipt lands
  under .tmp/weekly-digest/ on every run. Missed runs start when available.

  Examples:
    .\scripts\register-weekly-digest.ps1
    .\scripts\register-weekly-digest.ps1 -Day Friday -At '18:00'
    .\scripts\register-weekly-digest.ps1 -Unregister
#>
[CmdletBinding()]
param(
  [string]$TaskName = 'WorkbenchWeeklyDigest',
  [string]$Day = 'Monday',
  [string]$At = '08:00',
  [switch]$Unregister
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$Script = Join-Path $Root 'scripts\weekly_digest.py'

if ($Unregister) {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
  Write-Host "Removed scheduled task '$TaskName'."
  return
}

if (-not (Test-Path $VenvPython)) { throw "Venv python not found: $VenvPython" }
if (-not (Test-Path $Script)) { throw "Digest script not found: $Script" }
try {
  $when = [datetime]::ParseExact($At, 'HH:mm', $null)
} catch {
  throw "Time '$At' must use 24h HH:mm (example '08:00')."
}

$action = New-ScheduledTaskAction -Execute $VenvPython `
  -Argument "`"$Script`"" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Day -At $when
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
  -Settings $settings `
  -Description 'Mail the owner a weekly Gmail digest (fetch, summarize, send).' `
  -Force | Out-Null
$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "Registered '$TaskName': $($task.State), next run $($info.NextRunTime)."
