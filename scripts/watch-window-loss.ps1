<#
.SYNOPSIS
  Watchdog tick: detect a vanished console and auto-capture evidence.
.DESCRIPTION
  Snapshots titled consoles (interactive windows; hidden tool shells
  carry no title). A console watched across two consecutive ticks
  whose window disappears while its process lives on is a suspected
  vanish: the capture script runs automatically into
  .tmp/window-loss/auto-<stamp>/, and the event fires only once per
  PID. Normal closes (process gone too) drop silently.

  Runs every 5 minutes as scheduled task WorkbenchWindowWatch (see
  register-window-watchdog.ps1). State lives in
  .tmp/watch-window-loss/state.json (never committed).
#>
[CmdletBinding()]
param(
  [string]$StateDir = "",
  [switch]$Reset
)

$ErrorActionPreference = "Stop"

function Get-ConsoleSnapshot {
  # Keyed by PID, not title: TUI repaints flicker titles ("? ai-workbench"
  # vs "ai-workbench"), and a flicker must not reset the stability count.
  $snap = @{}
  Get-Process -Name @("powershell", "pwsh", "cmd") -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowTitle } |
    ForEach-Object { $snap["$($_.Id)"] = @{pid = $_.Id; title = $_.MainWindowTitle } }
  return $snap
}

function Find-Vanishes($previous, $current, $testAlive) {
  $fired = @()
  foreach ($key in $previous.Keys) {
    if ($current.ContainsKey($key)) { continue }
    $entry = $previous[$key]
    if ($entry.seen -lt 2) { continue }
    if ($entry.fired) { continue }
    if (& $testAlive $entry.pid) { $fired += $key }
  }
  return $fired
}

function Merge-Snapshot($previous, $current, $firedKeys) {
  $next = @{}
  foreach ($key in $current.Keys) {
    $seen = 1
    $fired = $false
    if ($previous.ContainsKey($key)) {
      $seen = [int]$previous[$key].seen + 1
      $fired = [bool]$previous[$key].fired
    }
    $next[$key] = @{pid = $current[$key].pid; title = $current[$key].title; seen = $seen; fired = $fired }
  }
  foreach ($key in $firedKeys) {
    if ($previous.ContainsKey($key) -and -not $next.ContainsKey($key)) {
      $entry = $previous[$key]
      $entry.fired = $true
      $next[$key] = $entry
    }
  }
  return $next
}

if (-not $WatchNoMain) {
  $root = Split-Path -Parent $PSScriptRoot
  if ([string]::IsNullOrWhiteSpace($StateDir)) {
    $StateDir = Join-Path $root ".tmp/watch-window-loss"
  }
  New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
  $statePath = Join-Path $StateDir "state.json"
  if ($Reset -and (Test-Path $statePath)) { Remove-Item $statePath -Force }

  $previous = @{}
  if (Test-Path $statePath) {
    try {
      $raw = Get-Content $statePath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
      foreach ($prop in $raw.consoles.PSObject.Properties) {
        $previous[$prop.Name] = @{pid = $prop.Value.pid; title = $prop.Value.title; seen = $prop.Value.seen; fired = $prop.Value.fired }
      }
    } catch {
      $previous = @{}
    }
  }

  $current = Get-ConsoleSnapshot
  $alive = { param($id) $null -ne (Get-Process -Id $id -ErrorAction SilentlyContinue) }
  $fired = @(Find-Vanishes $previous $current $alive)
  foreach ($key in $fired) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $outDir = Join-Path $root ".tmp/window-loss/auto-$stamp"
    & (Join-Path $PSScriptRoot "capture-window-loss.ps1") -OutDir $outDir | Out-Null
    "VANISH $key -> $outDir"
  }
  $next = Merge-Snapshot $previous $current $fired
  @{consoles = $next; lastRun = (Get-Date).ToString("o") } |
    ConvertTo-Json -Depth 5 -Compress | Set-Content -Path $statePath -Encoding UTF8
  "watch: watched=$($previous.Count) current=$($current.Count) fired=$($fired.Count)"
}
