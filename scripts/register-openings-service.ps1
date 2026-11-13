<#
  Register (or remove) the Openings kept-service tasks.

  OpeningsWeb: starts the web/API on 127.0.0.1:8501 at logon (token-gated;
  the upstream entry point binds 0.0.0.0, so the wrapper launches uvicorn
  on loopback instead). OpeningsCollect: one collection run daily at 06:30
  (missed runs start when available). Both run as the registering user.

  Examples:
    .\scripts\register-openings-service.ps1
    .\scripts\register-openings-service.ps1 -At '07:00'
    .\scripts\register-openings-service.ps1 -Unregister
#>
[CmdletBinding()]
param(
  [string]$At = '06:30',
  [switch]$Unregister
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Svc = Join-Path $Root 'apps\job_search\openings-svc'
$WebWrapper = Join-Path $Root 'scripts\openings-web.cmd'
$CollectWrapper = Join-Path $Root 'scripts\openings-collect.cmd'

if ($Unregister) {
  Unregister-ScheduledTask -TaskName 'OpeningsWeb' -Confirm:$false -ErrorAction Stop
  Unregister-ScheduledTask -TaskName 'OpeningsCollect' -Confirm:$false -ErrorAction Stop
  Write-Host 'Removed OpeningsWeb + OpeningsCollect.'
  return
}

foreach ($path in @($WebWrapper, $CollectWrapper, "$Svc\.venv\Scripts\openings.exe")) {
  if (-not (Test-Path $path)) { throw "Missing: $path" }
}
try {
  $when = [datetime]::ParseExact($At, 'HH:mm', $null)
} catch {
  throw "Time '$At' must use 24h HH:mm (example '06:30')."
}

$webAction = New-ScheduledTaskAction -Execute $WebWrapper -WorkingDirectory $Root
$webTrigger = New-ScheduledTaskTrigger -AtLogOn
$webSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([timespan]::Zero) `
  -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName 'OpeningsWeb' -Action $webAction `
  -Trigger $webTrigger -Settings $webSettings `
  -Description 'Openings job-search web/API on 127.0.0.1:8501 (token-gated).' `
  -Force | Out-Null

$collectAction = New-ScheduledTaskAction -Execute $CollectWrapper -WorkingDirectory $Root
$collectTrigger = New-ScheduledTaskTrigger -Daily -At $when
$collectSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName 'OpeningsCollect' -Action $collectAction `
  -Trigger $collectTrigger -Settings $collectSettings `
  -Description 'Daily Openings collection run (LinkedIn + Indeed Poland).' `
  -Force | Out-Null

foreach ($name in @('OpeningsWeb', 'OpeningsCollect')) {
  $task = Get-ScheduledTask -TaskName $name
  $info = Get-ScheduledTaskInfo -TaskName $name
  Write-Host "Registered '$name': $($task.State), next run $($info.NextRunTime)."
}
