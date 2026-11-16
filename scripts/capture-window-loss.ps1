<#
.SYNOPSIS
  One-shot evidence capture for a vanished Muse/PowerShell window.
.DESCRIPTION
  Collects everything the window-loss investigation needs into one
  timestamped folder: process table, visible-window enumeration,
  screenshot attempt, WER archives, event-log tail, reliability
  records, nearby scheduled tasks, and Muse session state.

  Window enumeration and screenshots only work in an interactive
  session (the agent sandbox is window-blind by isolation). The
  script records which context it ran in, so blind evidence is
  never mistaken for "no windows existed".
.EXAMPLE
  .\capture-window-loss.cmd 01a1d930-f0ab-7d73-8d3a-c7976cdb5d92
#>
[CmdletBinding()]
param(
  [string]$SessionId = "",
  [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($OutDir)) {
  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $OutDir = Join-Path $root ".tmp/window-loss/$stamp"
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function Write-Section([string]$name, [scriptblock]$body) {
  $path = Join-Path $OutDir $name
  try {
    & $body | Out-String -Width 200 | Set-Content -Path $path -Encoding UTF8
  } catch {
    "CAPTURE FAILED: $($_.Exception.Message)" | Set-Content -Path $path -Encoding UTF8
  }
}

$now = Get-Date

Write-Section "meta.txt" {
  "captured_local: $($now.ToString('o'))"
  "captured_utc: $($now.ToUniversalTime().ToString('o'))"
  "machine: $env:COMPUTERNAME"
  "user: $env:USERNAME"
  "interactive: $([Environment]::UserInteractive)"
  "session_id: $SessionId"
}

Write-Section "processes.txt" {
  $names = @("powershell", "pwsh", "conhost", "muse", "WindowsTerminal", "werfault")
  Get-Process -Name $names -ErrorAction SilentlyContinue |
    Select-Object Id, ProcessName, StartTime, MainWindowTitle, Path |
    Format-Table -AutoSize | Out-String -Width 200
  ""
  "--- command lines (CIM, may be unavailable in sandbox) ---"
  try {
    Get-CimInstance Win32_Process -ErrorAction Stop |
      Where-Object { $names -contains $_.Name.Replace(".exe", "") } |
      Select-Object ProcessId, ParentProcessId, Name, CommandLine |
      Format-List | Out-String -Width 200
  } catch {
    "CIM unavailable: $($_.Exception.Message)"
  }
}

Add-Type -TypeDefinition @"
using System; using System.Text; using System.Runtime.InteropServices;
public class CWE2 {
  public delegate bool Cb(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(Cb c, IntPtr l);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L; public int T; public int R; public int B; }
}
"@ -ErrorAction SilentlyContinue

Write-Section "windows.txt" {
  $script:found = @()
  try {
    [CWE2]::EnumWindows({
      param($h, $l)
      $sb = New-Object Text.StringBuilder 256
      $cs = New-Object Text.StringBuilder 128
      [CWE2]::GetWindowText($h, $sb, 256) | Out-Null
      [CWE2]::GetClassName($h, $cs, 128) | Out-Null
      $p = 0
      [CWE2]::GetWindowThreadProcessId($h, [ref]$p) | Out-Null
      $r = New-Object CWE2+RECT
      [CWE2]::GetWindowRect($h, [ref]$r) | Out-Null
      $script:found += ("pid={0} visible={1} min={2} rect={3},{4},{5},{6} class=[{7}] title=[{8}]" -f `
        $p, [CWE2]::IsWindowVisible($h), [CWE2]::IsIconic($h), $r.L, $r.T, $r.R, $r.B, $cs, $sb)
      return $true
    }, [IntPtr]::Zero) | Out-Null
  } catch {
    "ENUM FAILED: $($_.Exception.Message)"
  }
  if ($script:found.Count -eq 0) {
    "NO WINDOWS ENUMERATED - window-blind context (sandbox/service), not evidence of absence."
  } else {
    "enumerated: $($script:found.Count)"
    $script:found
  }
}

Write-Section "desktops.txt" {
  try {
    $key = "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops\Desktops"
    $ids = (Get-ChildItem -Path $key -ErrorAction Stop).Count
    "virtual_desktops: $ids"
  } catch {
    "virtual desktop registry unreadable: $($_.Exception.Message)"
  }
}

try {
  Add-Type -AssemblyName System.Drawing, System.Windows.Forms -ErrorAction Stop
  $bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
  $bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
  $gfx = [System.Drawing.Graphics]::FromImage($bmp)
  $gfx.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
  $shot = Join-Path $OutDir "screenshot.png"
  $bmp.Save($shot, [System.Drawing.Imaging.ImageFormat]::Png)
  $gfx.Dispose(); $bmp.Dispose()
  "saved: screenshot.png ($($bounds.Width)x$($bounds.Height))" |
    Set-Content -Path (Join-Path $OutDir "screenshot.txt") -Encoding UTF8
} catch {
  "SCREENSHOT FAILED (expected headless): $($_.Exception.Message)" |
    Set-Content -Path (Join-Path $OutDir "screenshot.txt") -Encoding UTF8
}

Write-Section "wer.txt" {
  $roots = @(
    (Join-Path $env:LOCALAPPDATA "Microsoft\Windows\WER"),
    (Join-Path $env:ProgramData "Microsoft\Windows\WER")
  )
  foreach ($wer in $roots) {
    foreach ($sub in @("ReportArchive", "ReportQueue")) {
      $dir = Join-Path $wer $sub
      if (Test-Path $dir) {
        "$dir (newest 20):"
        Get-ChildItem $dir -ErrorAction SilentlyContinue |
          Sort-Object LastWriteTime -Descending | Select-Object -First 20 Name, LastWriteTime
      } else {
        "$dir missing"
      }
      ""
    }
  }
}

Write-Section "eventlog.txt" {
  $since = $now.AddMinutes(-30)
  $events = Get-WinEvent -FilterHashtable @{LogName = "Application"; StartTime = $since } `
    -MaxEvents 300 -ErrorAction Stop |
    Where-Object { $_.ProviderName -match "muse|powershell|conhost|terminal|werfault|Application Error" } |
    Select-Object -First 100 TimeCreated, ProviderName, Id, LevelDisplayName,
      @{N = "Message"; E = { ($_.Message -replace "\s+", " ").Substring(0, [Math]::Min(300, $_.Message.Length)) } }
  if ($events) { $events | Format-Table -AutoSize | Out-String -Width 200 }
  else { "no matching Application events in the last 30 minutes" }
}

Write-Section "reliability.txt" {
  $since = $now.AddHours(-24)
  $recs = Get-CimInstance Win32_ReliabilityRecords -ErrorAction Stop |
    Where-Object { $_.TimeGenerated -gt $since } |
    Sort-Object TimeGenerated -Descending | Select-Object -First 30 TimeGenerated, SourceName, EventIdentifier
  if ($recs) { $recs | Format-Table -AutoSize | Out-String -Width 200 }
  else { "no reliability records in the last 24 hours" }
}

Write-Section "tasks.txt" {
  $lo = $now.AddMinutes(-45)
  $hi = $now.AddMinutes(5)
  Get-ScheduledTask -ErrorAction Stop | ForEach-Object {
    $info = $_ | Get-ScheduledTaskInfo -ErrorAction SilentlyContinue
    if ($info -and $info.LastRunTime -gt $lo -and $info.LastRunTime -lt $hi) {
      "{0:HH:mm:ss} {1} ({2})" -f $info.LastRunTime, $_.TaskName, $info.LastTaskResult
    }
  }
}

if (-not [string]::IsNullOrWhiteSpace($SessionId)) {
  Write-Section "muse-session.txt" {
    $sessions = Join-Path $HOME ".local/share/muse/sessions"
    $dir = Get-ChildItem $sessions -Directory -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -match "^[0-9]{4}$" } |
      Get-ChildItem -Directory -Recurse -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -eq $SessionId } | Select-Object -First 1
    if (-not $dir) { "session dir not found: $SessionId"; return }
    "dir: $($dir.FullName)"
    $lock = Join-Path $dir.FullName ".session.lock"
    "lock_path_present: $(Test-Path $lock) (presence only - never delete or recreate it)"
    $crashes = Join-Path $HOME ".local/share/muse/crashes"
    if (Test-Path $crashes) {
      "crashes (newest 5):"
      Get-ChildItem $crashes -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 5 Name, LastWriteTime
    } else {
      "crashes dir absent"
    }
    $log = Join-Path $dir.FullName "session.jsonl"
    if (Test-Path $log) {
      $info = Get-Item $log
      "log_bytes: $($info.Length)"
      "log_last_write: $($info.LastWriteTime.ToString('o'))"
      "--- tail (truncated) ---"
      Get-Content $log -Tail 15 -ErrorAction SilentlyContinue |
        ForEach-Object { $_.Substring(0, [Math]::Min(300, $_.Length)) }
    } else {
      "session.jsonl missing"
    }
  }
}

$files = Get-ChildItem $OutDir | Select-Object -ExpandProperty Name
"evidence: $OutDir"
"files: $($files -join ', ')"
