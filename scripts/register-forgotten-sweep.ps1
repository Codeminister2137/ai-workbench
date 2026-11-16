<#
  Register (or remove) the weekly forgotten-items sweep task.

  The task runs scripts/forgotten_sweep.py with the checkout venv: scan
  dashboard stores, git branches/worktrees, plans/goals linkage and stale
  E2E drafts, file one inbox task per new finding group (deduped by the
  previous receipt, so repeats never spam), and write a receipt under
  .tmp/forgotten-sweep/ on every run. Missed runs start when available.

  Examples:
    .\scripts\register-forgotten-sweep.ps1
    .\scripts\register-forgotten-sweep.ps1 -Day Sunday -At '18:00'
    .\scripts\register-forgotten-sweep.ps1 -Unregister
#>
[CmdletBinding()]
param(
  [string]$TaskName = 'WorkbenchForgottenSweep',
  [string]$Day = 'Sunday',
  [string]$At = '18:00',
  [switch]$Unregister
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$Script = Join-Path $Root 'scripts\forgotten_sweep.py'

if ($Unregister) {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
  Write-Host "Removed scheduled task '$TaskName'."
  return
}

if (-not (Test-Path $VenvPython)) { throw "Venv python not found: $VenvPython" }
if (-not (Test-Path $Script)) { throw "Sweep script not found: $Script" }
try {
  $when = [datetime]::ParseExact($At, 'HH:mm', $null)
} catch {
  throw "Time '$At' must use 24h HH:mm (example '18:00')."
}

$action = New-ScheduledTaskAction -Execute $VenvPython `
  -Argument "`"$Script`" --file" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Day -At $when
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
  -Settings $settings `
  -Description 'Weekly forgotten-items sweep (scan stores/git/plans, file new findings, write receipt).' `
  -Force | Out-Null
$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host "Registered '$TaskName': $($task.State), next run $($info.NextRunTime)."
