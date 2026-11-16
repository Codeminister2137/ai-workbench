<#
.SYNOPSIS
  Watchdog tick: detect a vanished console, capture evidence, restore it.
.DESCRIPTION
  Snapshots titled consoles (interactive windows; hidden tool shells
  carry no title). A console watched across two consecutive ticks
  whose window disappears while its process lives on is a suspected
  vanish: the capture script runs automatically into
  .tmp/window-loss/auto-<stamp>/, a fire-context file records the
  foreground window, idle time, full process table and display
  topology for actor forensics, and the hidden console is restored
  (ShowWindow SW_SHOWNA — shown without stealing focus) when its
  window object still exists hidden with an intact rect.

  Restore guardrails (v2): never touch minimized/iconic windows
  (min keeps its title, so the watchdog ignores them by design, and
  a hidden-but-iconic window is left alone as owned-hidden); only
  restore ConsoleWindowClass windows of the fired PID that are
  hidden AND non-iconic with a non-empty title and a sane rect;
  fire (capture + restore) only once per PID; verify visibility
  after the restore call and record RESTORED / RESTORE_FAILED.

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

Add-Type -TypeDefinition @"
using System; using System.Text; using System.Runtime.InteropServices;
public class CWW {
  public delegate bool Cb(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(Cb c, IntPtr l);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("kernel32.dll")] public static extern ulong GetTickCount64();
  [DllImport("user32.dll")] public static extern bool GetLastInputInfo(ref LASTINPUTINFO i);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L; public int T; public int R; public int B; }
  [StructLayout(LayoutKind.Sequential)] public struct LASTINPUTINFO { public uint cbSize; public uint dwTime; }
  public static long IdleMs() {
    LASTINPUTINFO li = new LASTINPUTINFO();
    li.cbSize = (uint)Marshal.SizeOf(typeof(LASTINPUTINFO));
    if (!GetLastInputInfo(ref li)) return -1;
    unchecked { return (long)((uint)GetTickCount64() - li.dwTime); }
  }
}
"@ -ErrorAction SilentlyContinue

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

function Find-HiddenConsoles([int]$procId) {
  # Hidden-but-restorable consoles of one PID: ConsoleWindowClass,
  # hidden, NON-iconic (never touch minimized), titled, sane rect.
  # NOTE: the PID travels in $script:hcPid because the native callback
  # cannot see function locals (and $pid is an automatic variable).
  $script:hcPid = $procId
  $script:hcFound = @()
  try {
    [CWW]::EnumWindows({
      param($h, $l)
      $p = 0
      [CWW]::GetWindowThreadProcessId($h, [ref]$p) | Out-Null
      if ($p -eq $script:hcPid) {
        $sb = New-Object Text.StringBuilder 256
        $cs = New-Object Text.StringBuilder 128
        [CWW]::GetWindowText($h, $sb, 256) | Out-Null
        [CWW]::GetClassName($h, $cs, 128) | Out-Null
        if ($cs.ToString() -eq "ConsoleWindowClass") {
          $r = New-Object CWW+RECT
          [CWW]::GetWindowRect($h, [ref]$r) | Out-Null
          $script:hcFound += @{
            h = $h; title = $sb.ToString();
            visible = [CWW]::IsWindowVisible($h); iconic = [CWW]::IsIconic($h);
            rect = @($r.L, $r.T, $r.R, $r.B)
          }
        }
      }
      return $true
    }, [IntPtr]::Zero) | Out-Null
  } catch {
    return @()
  }
  return @($script:hcFound | Where-Object {
    -not $_.visible -and -not $_.iconic -and $_.title -and
    (($_.rect[2] - $_.rect[0]) -gt 100) -and (($_.rect[3] - $_.rect[1]) -gt 100)
  })
}

function Restore-HiddenConsoles([int]$procId) {
  $results = @()
  $targets = @(Find-HiddenConsoles $procId)
  if ($targets.Count -eq 0) {
    return @(@{pid = $procId; result = "NO_WINDOW"; detail = "no hidden non-iconic titled console window for PID" })
  }
  foreach ($w in $targets) {
    $res = "RESTORE_FAILED"
    $detail = ""
    try {
      # SW_SHOWNA (8): ask to show in its previous state (e.g. maximized)
      # without activating. Live test 2026-11-16: on a quiet desktop
      # Windows still brought the restored console forward — acceptable,
      # this runs at most once per genuine vanish, never on a timer.
      [CWW]::ShowWindow($w.h, 8) | Out-Null
      Start-Sleep -Milliseconds 300
      if ([CWW]::IsWindowVisible($w.h)) { $res = "RESTORED" }
      else { $detail = "ShowWindow(SW_SHOWNA) returned but window still hidden (cross-IL block?)" }
    } catch {
      $detail = $_.Exception.Message
    }
    $results += @{pid = $procId; result = $res; title = $w.title;
      rect = ($w.rect -join ","); detail = $detail }
  }
  return $results
}

function Write-FireContext([string]$outDir, $firedKeys, $restoreResults) {
  $lines = @()
  $lines += "fired_local: $((Get-Date).ToString('o'))"
  $lines += "fired_pids: $($firedKeys -join ', ')"
  $lines += "interactive: $([Environment]::UserInteractive)"
  try {
    $idle = [CWW]::IdleMs()
    $lines += "idle_ms: $idle"
  } catch { $lines += "idle_ms: unavailable ($($_.Exception.Message))" }
  try {
    $fg = [CWW]::GetForegroundWindow()
    $fp = 0
    [CWW]::GetWindowThreadProcessId($fg, [ref]$fp) | Out-Null
    $fn = ""
    try { $fn = (Get-Process -Id $fp -ErrorAction Stop).ProcessName } catch { $fn = "?" }
    $fsb = New-Object Text.StringBuilder 256
    [CWW]::GetWindowText($fg, $fsb, 256) | Out-Null
    $lines += "foreground: handle=$fg pid=$fp process=$fn title=[$($fsb.ToString())]"
  } catch { $lines += "foreground: unavailable ($($_.Exception.Message))" }
  $lines += "--- restore attempts ---"
  foreach ($r in $restoreResults) {
    $lines += ("pid={0} result={1} title=[{2}] rect=[{3}] {4}" -f $r.pid, $r.result, $r.title, $r.rect, $r.detail)
  }
  $lines += "--- all processes (actor hunt: any birth near the fire) ---"
  try {
    $procs = @()
    foreach ($pr in (Get-Process -ErrorAction Stop)) {
      $st = "?"
      try { $st = $pr.StartTime.ToString("HH:mm:ss") } catch { $st = "?" }
      $procs += ("{0} {1} {2}" -f $pr.Id, $st, $pr.ProcessName)
    }
    foreach ($pl in ($procs | Sort-Object)) { $lines += $pl }
  } catch { $lines += "process table unavailable: $($_.Exception.Message)" }
  $lines += "--- window-enum sanity (0 = blind context, not absence) ---"
  try {
    $script:enumCount = 0
    [CWW]::EnumWindows({ param($h, $l) $script:enumCount++; return $true }, [IntPtr]::Zero) | Out-Null
    $lines += "enumerated_top_level: $($script:enumCount)"
  } catch { $lines += "enumerated_top_level: enum failed ($($_.Exception.Message))" }
  $lines += "--- display topology ---"
  try {
    Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
    foreach ($s in [System.Windows.Forms.Screen]::AllScreens) {
      $lines += ("{0} primary={1} bounds={2}" -f $s.DeviceName, $s.Primary, $s.Bounds)
    }
  } catch { $lines += "screens unavailable: $($_.Exception.Message)" }
  $lines | Set-Content -Path (Join-Path $outDir "fire-context.txt") -Encoding UTF8
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
  $restoreResults = @()
  foreach ($key in $fired) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $outDir = Join-Path $root ".tmp/window-loss/auto-$stamp"
    try {
      & (Join-Path $PSScriptRoot "capture-window-loss.ps1") -OutDir $outDir | Out-Null
    } catch {
      "capture failed: $($_.Exception.Message)" | Set-Content -Path (Join-Path $outDir "capture-error.txt") -Encoding UTF8
    }
    try {
      $restoreResults += @(Restore-HiddenConsoles ([int]$key))
    } catch {
      $restoreResults += @(@{pid = $key; result = "RESTORE_ERROR"; title = ""; rect = ""; detail = $_.Exception.Message })
    }
    try {
      Write-FireContext $outDir $fired $restoreResults
    } catch {
      "fire-context failed: $($_.Exception.Message)" | Set-Content -Path (Join-Path $outDir "fire-context-error.txt") -Encoding UTF8
    }
    $rr = @($restoreResults | Where-Object { "$($_.pid)" -eq "$key" })
    "VANISH $key -> $outDir restore=$($(if ($rr.Count) { ($rr | ForEach-Object { $_.result }) -join '+' } else { 'none' }))"
  }
  $next = Merge-Snapshot $previous $current $fired
  foreach ($r in $restoreResults) {
    $k = "$($r.pid)"
    if ($next.ContainsKey($k)) {
      $next[$k].restore = $r.result
      $next[$k].restoreAt = (Get-Date).ToString("o")
    }
  }
  @{consoles = $next; lastRun = (Get-Date).ToString("o") } |
    ConvertTo-Json -Depth 5 -Compress | Set-Content -Path $statePath -Encoding UTF8
  "watch: watched=$($previous.Count) current=$($current.Count) fired=$($fired.Count)"
}
