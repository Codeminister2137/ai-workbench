<#
  Register (or remove) the daily allowance health check task.

  The task runs scripts/allowance_healthcheck.py with the checkout venv:
  read native allowance windows, flag exhausted windows and failed codex
  reads, list stale models, write a receipt under .tmp/allowance-health/
  on every run, and file one owner inbox task per new problem set
  (deduped by hash, so repeats never spam). Missed runs start when
  available.

  Examples:
    .\scripts\register-allowance-healthcheck.ps1
    .\scripts\register-allowance-healthcheck.ps1 -At '07:30'
    .\scripts\register-allowance-healthcheck.ps1 -Unregister
#>
[CmdletBinding()]
param(
  [string]$TaskName = 'WorkbenchAllowanceCheck',
  [string]$At = '07:30',
  [switch]$Unregister
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$Script = Join-Path $Root 'scripts\allowance_healthcheck.py'

if ($Unregister) {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
  Write-Host "Removed scheduled task '$TaskName'."
  return
}

if (-not (Test-Path $VenvPython)) { throw "Venv python not found: $VenvPython" }
if (-not (Test-Path $Script)) { throw "Healthcheck script not found: $Script" }
try {
  $when = [datetime]::ParseExact($At, 'HH:mm', $null)
} catch {
  throw "Time '$At' must use 24h HH:mm (example '07:30')."
}

$action = New-ScheduledTaskAction -Execute $VenvPython `
  -Argument "`"$Script`"" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -Daily -At $when
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
  -Settings $settings `
  -Description 'Daily allowance health check (windows, refresh eve, stale models; file owner task on problems).' `
  -Force | Out-Null
$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "Registered '$TaskName': $($task.State), next run $($info.NextRunTime)."
