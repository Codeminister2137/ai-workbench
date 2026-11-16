<#
.SYNOPSIS
  Reclaim a Muse session whose window vanished but whose processes live on.
.DESCRIPTION
  Finds processes whose command line references the session id, then
  either prints the recovery drill (default dry-run, no signals sent)
  or, with -Execute, kills them, verifies they are gone, and opens a
  fresh window running `muse resume <id>`.

  Self-preservation: the script's own process chain is excluded
  from the kill set (it trivially references the id it was given),
  so it can never kill its invoker. Run it from a fresh window
  outside the lost session, otherwise the lost chain hides among
  the excluded ancestors.
.EXAMPLE
  .\recover-muse-session.cmd 01a1d930-f0ab-7d73-8d3a-c7976cdb5d92
  .\recover-muse-session.cmd 01a1d930-f0ab-7d73-8d3a-c7976cdb5d92 -Execute
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$SessionId,
  [switch]$Execute
)

$ErrorActionPreference = "Stop"

$sessions = Join-Path $HOME ".local/share/muse/sessions"
$dir = Get-ChildItem $sessions -Directory -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -match "^[0-9]{4}$" } |
  Get-ChildItem -Directory -Recurse -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -eq $SessionId } | Select-Object -First 1
if (-not $dir) {
  Write-Error -ErrorAction Continue "session dir not found: $SessionId"
  exit 2
}
Write-Output "session: $($dir.FullName)"

$candidates = @()
try {
  $procs = Get-CimInstance Win32_Process -ErrorAction Stop
} catch {
  Write-Error -ErrorAction Continue "CIM process query failed (run from an interactive window): $($_.Exception.Message)"
  exit 3
}
$chain = @($PID)
$seen = @{}
$cursor = $PID
while ($cursor -and -not $seen.ContainsKey($cursor)) {
  $seen[$cursor] = $true
  $parent = ($procs | Where-Object { $_.ProcessId -eq $cursor } | Select-Object -First 1).ParentProcessId
  if (-not $parent -or $parent -eq $cursor) { break }
  $chain += $parent
  $cursor = $parent
}
foreach ($proc in $procs) {
  if ($proc.CommandLine -and $proc.CommandLine.Contains($SessionId) -and $chain -notcontains $proc.ProcessId) {
    $candidates += $proc
  }
}
if ($candidates.Count -eq 0) {
  Write-Output "no live processes outside my own chain reference $SessionId - nothing to kill."
  Write-Output "resume directly: muse resume $SessionId"
  exit 0
}
Write-Output "kill set:"
$candidates | Select-Object ProcessId, ParentProcessId, Name,
  @{N = "CommandLine"; E = { $_.CommandLine.Substring(0, [Math]::Min(160, $_.CommandLine.Length)) } } |
  Format-Table -AutoSize | Out-String -Width 200 | Write-Output

$pids = ($candidates | Select-Object -ExpandProperty ProcessId) -join " /PID "
Write-Output "visible consoles right now (only reclaim when the session has none):"
Get-Process -Name @("powershell", "pwsh", "conhost") -ErrorAction SilentlyContinue |
  Where-Object { $_.MainWindowTitle } |
  Select-Object Id, ProcessName, MainWindowTitle |
  Format-Table -AutoSize | Out-String -Width 200 | Write-Output

if (-not $Execute) {
  Write-Output "DRY RUN - no signals sent. To reclaim:"
  Write-Output "  taskkill /F /PID $pids"
  Write-Output "  muse resume $SessionId"
  Write-Output "Or re-run with -Execute."
  exit 0
}

$killArgs = @("/F")
foreach ($proc in $candidates) { $killArgs += "/PID"; $killArgs += $proc.ProcessId }
& taskkill @killArgs | Out-Null
Start-Sleep -Seconds 2
$still = @()
foreach ($proc in $candidates) {
  if (Get-Process -Id $proc.ProcessId -ErrorAction SilentlyContinue) {
    $still += $proc.ProcessId
  }
}
if ($still.Count -gt 0) {
  Write-Error -ErrorAction Continue ("these PIDs survived taskkill: {0}" -f ($still -join ", "))
  exit 5
}
Write-Output "kill set verified gone."
if ([Environment]::UserInteractive) {
  Start-Process powershell -ArgumentList "-NoExit", "-NoProfile", "-Command", "muse resume $SessionId"
  Write-Output "fresh window launched: muse resume $SessionId"
} else {
  Write-Output "headless context - run this yourself: muse resume $SessionId"
}

