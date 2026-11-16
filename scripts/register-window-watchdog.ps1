<#
.SYNOPSIS
  Register (or remove) the window-loss watchdog scheduled task.
.DESCRIPTION
  Creates task WorkbenchWindowWatch: runs watch-window-loss.ps1 every
  5 minutes, interactive-only (/IT) so it sees the user's desktop.
  With -Unregister, removes the task. State and evidence stay local.
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/register-window-watchdog.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/register-window-watchdog.ps1 -Unregister
#>
[CmdletBinding()]
param([switch]$Unregister)

$ErrorActionPreference = "Stop"
$taskName = "WorkbenchWindowWatch"

if ($Unregister) {
  schtasks /Delete /TN $taskName /F
  Write-Output "removed: $taskName"
  exit 0
}

$script = Join-Path $PSScriptRoot "watch-window-loss.ps1"
$action = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
schtasks /Create /TN $taskName /SC MINUTE /MO 5 /TR $action /IT /F
schtasks /Query /TN $taskName /FO LIST | Select-String -Pattern "TaskName|Status|Last Run|Next Run"
