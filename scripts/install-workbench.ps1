<# AI Workbench - local dashboard installer (Windows, no admin needed
   except for the optional private-network step).

   What it does:
     1. Checks Python (>= 3.12).
     2. Offers to install uv and ffmpeg when missing, then creates or
        reuses .venv and installs the workbench (prefers uv sync --locked,
        falls back to plain Python).
     3. Creates apps/workbench_dashboard/dashboard.json from the example
        config when missing. An existing config is kept and never printed.
     4. Offers to install Tailscale (private-network app for reaching the
        dashboard from another device). You can say no; the dashboard
        still works on this PC.
     5. Registers the dashboard to start automatically at sign-in (a per-user
        Scheduled Task - no admin needed), starts it now and checks that
        it answers. The summary always shows how to start it by hand.

   Run from the project folder in PowerShell:
     powershell -ExecutionPolicy Bypass -File .\scripts\install-workbench.ps1

   Useful switches:
     -NoTailscale     Skip the private-network step silently this run.
     -NonInteractive  No questions; safe defaults (skips install offers).
     -Uninstall       Remove the automatic start entry again (keeps your files).
     -Port 8766       Loopback port the dashboard listens on.

   Re-running is safe: every step checks the current state first.

   Local-first by design: no passwords, no access codes, no Docker, no phone
   flow. The dashboard trusts local-browser requests only (localhost-trust).
#>
[CmdletBinding()]
param(
  [int]$Port = 8766,
  [string]$TaskName = 'WorkbenchDashboard',
  [string]$RepoRoot = '',
  [switch]$NonInteractive,
  [switch]$NoTailscale,
  [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------- helpers ---

function Write-Step($Text) {
  Write-Host ''
  Write-Host "==> $Text"
}

function Read-Choice($Prompt, [bool]$DefaultYes) {
  if ($NonInteractive) { return $DefaultYes }
  $hint = 'Y/n'
  if (-not $DefaultYes) { $hint = 'y/N' }
  $answer = (Read-Host "$Prompt [$hint]").Trim().ToLowerInvariant()
  if ($answer -eq '') { return $DefaultYes }
  return ($answer -eq 'y' -or $answer -eq 'yes')
}

function Get-RepoRoot {
  if ($RepoRoot -ne '') { return (Resolve-Path $RepoRoot).Path }
  return (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}

function Confirm-Checkout($Root) {
  $app = Join-Path $Root 'apps\workbench_dashboard\dashboard_web_app.py'
  $project = Join-Path $Root 'pyproject.toml'
  $lock = Join-Path $Root 'uv.lock'
  if (-not (Test-Path $app) -or -not (Test-Path $project) -or -not (Test-Path $lock)) {
    throw "This does not look like the ai-workbench project folder: $Root"
  }
}

# --------------------------------------------- python / install (.venv) ---

function Find-Python {
  foreach ($name in @('python', 'python3', 'py')) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($null -eq $cmd) { continue }
    try {
      $out = (& $cmd.Source --version 2>&1 | Out-String).Trim()
    } catch { continue }
    if ($out -match 'Python\s+3\.(\d+)') {
      $minor = [int]$Matches[1]
      if ($minor -ge 12) { return $cmd.Source }
    }
  }
  return $null
}

function Test-VenvImport($VenvPython) {
  if (-not (Test-Path $VenvPython)) { return $false }
  try {
    & $VenvPython -c 'import ai_agent, ai_orchestrator, ai_provider' 2>$null
    return ($LASTEXITCODE -eq 0)
  } catch { return $false }
}

function Ensure-Install($Root, $PythonExe) {
  $venvPython = Join-Path $Root '.venv\Scripts\python.exe'
  $uv = Get-Command uv -ErrorAction SilentlyContinue
  if ($null -ne $uv) {
    Write-Host 'Installing with uv (uses the project lockfile)...'
    Push-Location $Root
    try {
      & $uv.Source sync --locked
      if ($LASTEXITCODE -ne 0) { throw 'uv sync failed.' }
    } finally { Pop-Location }
  } elseif (Test-VenvImport $venvPython) {
    Write-Host 'Program files are already installed; skipping reinstall.'
    return $venvPython
  } else {
    Write-Host 'uv not found; using plain Python (.venv + pip)...'
    if (-not (Test-Path $venvPython)) {
      & $PythonExe -m venv (Join-Path $Root '.venv')
      if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv.' }
    }
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
    & $venvPython -m pip install -e $Root
    if ($LASTEXITCODE -ne 0) { throw 'pip install failed.' }
  }
  if (-not (Test-VenvImport $venvPython)) {
    throw 'Install finished but the workbench packages still cannot be loaded.'
  }
  return $venvPython
}

# ------------------------------------------------------- dashboard config ---

function Ensure-DashboardConfig($Root) {
  $appDir = Join-Path $Root 'apps\workbench_dashboard'
  $local = Join-Path $appDir 'dashboard.json'
  $example = Join-Path $appDir 'dashboard.example.json'
  if (Test-Path $local) {
    Write-Host 'Kept your existing dashboard config (not shown).'
    return $false
  }
  if (-not (Test-Path $example)) { throw "Missing example config: $example" }
  Copy-Item -Path $example -Destination $local
  Write-Host 'Created dashboard.json from the example config.'
  Write-Host 'Edit the provider/model inside it before use; never commit secrets.'
  return $true
}

# --------------------------------- start wrapper + automatic start entry ---

function Write-StartWrapper($Root, $Port, $VenvPython) {
  $runtime = Join-Path $Root '.runtime'
  if (-not (Test-Path $runtime)) { [void](New-Item -ItemType Directory $runtime) }
  $wrapper = Join-Path $runtime 'start-dashboard.ps1'
  $template = @'
# Generated by scripts/install-workbench.ps1 - do not edit by hand, re-run the installer.
# Starts the local workbench dashboard. Nothing secret is ever printed here.
$ErrorActionPreference = 'Stop'
$RepoRoot = '__REPO__'
$Port = __PORT__
$AppDir = Join-Path $RepoRoot 'apps\workbench_dashboard'
$LogFile = Join-Path $RepoRoot '.runtime\dashboard.log'
$VenvPython = '__VENVPYTHON__'

if (-not (Test-Path $VenvPython)) {
  throw "Missing venv Python: $VenvPython. Re-run scripts/install-workbench.ps1."
}
if (-not (Test-Path (Join-Path $AppDir 'dashboard_web_app.py'))) {
  throw "Missing dashboard app under: $AppDir. Re-run scripts/install-workbench.ps1."
}

# A scheduled task inherits the scheduler's stale PATH, which hides tools
# installed later (ffmpeg, uv). Refresh from the registry before serving.
$env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') +
  ';' + [System.Environment]::GetEnvironmentVariable('Path', 'User')

'' + "`n=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') starting dashboard ===`n" | Out-File -Append -Encoding utf8 $LogFile
# Native stderr must not abort the server: with 'Stop' in effect, a redirected
# stderr line becomes a fatal NativeCommandError before the port binds.
$ErrorActionPreference = 'Continue'
& $VenvPython (Join-Path $AppDir 'dashboard_web_app.py') --host 127.0.0.1 --port "$Port" *>> $LogFile
'@
  # Single-quoted PowerShell strings escape a quote by doubling it. Without
  # this, a folder name with an apostrophe (legal on Windows, e.g. O'Brien)
  # breaks the generated wrapper, and a crafted checkout path could inject a
  # statement that runs at every sign-in. $Port is an int and needs no escape.
  $content = $template.Replace('__REPO__', $Root.Replace("'", "''")).Replace(
    '__PORT__', "$Port").Replace('__VENVPYTHON__', $VenvPython.Replace("'", "''"))
  $old = ''
  if (Test-Path $wrapper) { $old = [System.IO.File]::ReadAllText($wrapper) }
  [System.IO.File]::WriteAllText($wrapper, $content, [System.Text.UTF8Encoding]::new($false))
  return (@{ Path = $wrapper; Changed = ($old -ne $content) })
}

function Register-DashboardTask($TaskName, $Root, $WrapperPath) {
  $action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$WrapperPath`"" `
    -WorkingDirectory $Root
  $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
  $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable
  Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description 'Start the AI Workbench dashboard at sign-in.' -Force | Out-Null
}

function Stop-OwnDashboard($Root) {
  # Best effort: stop only dashboard processes started for THIS project folder.
  try {
    $mine = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction Stop |
      Where-Object { $null -ne $_.CommandLine -and
        $_.CommandLine.Contains('dashboard_web_app.py') -and $_.CommandLine.Contains($Root) }
    foreach ($p in $mine) {
      try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch { }
    }
  } catch { }
}

function Test-ServePort($Port) {
  $client = New-Object Net.Sockets.TcpClient
  try {
    $iar = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
    return $iar.AsyncWaitHandle.WaitOne(1000)
  } catch { return $false } finally { $client.Close() }
}

function Restart-DashboardTask($TaskName, $Root, [bool]$ConfigChanged) {
  $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  if ($null -eq $task) { return 'missing' }
  if ($task.State -eq 'Running' -and $ConfigChanged) {
    Write-Host 'Restarting the dashboard so the new settings take effect...'
    try { Stop-ScheduledTask -TaskName $TaskName -ErrorAction Stop } catch { }
    Start-Sleep -Seconds 2
    Stop-OwnDashboard $Root
    Start-Sleep -Seconds 1
  }
  if ((Get-ScheduledTask -TaskName $TaskName).State -ne 'Running') {
    try {
      Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
      return 'started'
    } catch {
      return 'start-failed'
    }
  }
  return 'already-running'
}

# ------------------------------------------------------------- tailscale ---

function Find-Tailscale {
  $cmd = Get-Command tailscale.exe, tailscale -ErrorAction SilentlyContinue |
    Select-Object -First 1
  if ($null -ne $cmd) { return $cmd.Source }
  $probe = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'
  if (Test-Path $probe) { return $probe }
  return $null
}

function Find-UvCommand {
  $cmd = Get-Command uv -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($null -ne $cmd) { return $cmd.Source }
  # A fresh winget install may not be on this shell's PATH yet; refresh it
  # from the registry once before giving up.
  $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') +
    ';' + [System.Environment]::GetEnvironmentVariable('Path', 'User')
  $cmd = Get-Command uv -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($null -ne $cmd) { return $cmd.Source }
  return $null
}

function Find-FfmpegCommand {
  $cmd = Get-Command ffmpeg -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($null -ne $cmd) { return $cmd.Source }
  # A previous install may not be on this shell's PATH yet; refresh it
  # from the registry once before offering a reinstall.
  $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'Machine') +
    ';' + [System.Environment]::GetEnvironmentVariable('Path', 'User')
  $cmd = Get-Command ffmpeg -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($null -ne $cmd) { return $cmd.Source }
  return $null
}

function Install-Uv {
  Write-Host 'Installing uv (fast Python installer)...'
  $winget = Get-Command winget.exe, winget -ErrorAction SilentlyContinue |
    Select-Object -First 1
  if ($null -eq $winget) { throw 'winget is not available.' }
  & $winget.Source install -e --id astral-sh.uv `
    --accept-source-agreements --accept-package-agreements
  if ($LASTEXITCODE -ne 0) { throw 'winget could not install uv.' }
  if ($null -eq (Find-UvCommand)) { throw 'uv installed but is not on PATH yet.' }
}

function Install-Ffmpeg {
  Write-Host 'Installing ffmpeg (audio converter for voice dictation)...'
  $winget = Get-Command winget.exe, winget -ErrorAction SilentlyContinue |
    Select-Object -First 1
  if ($null -eq $winget) { throw 'winget is not available.' }
  & $winget.Source install -e --id Gyan.FFmpeg `
    --accept-source-agreements --accept-package-agreements
  if ($LASTEXITCODE -ne 0) {
    # winget reports a nonzero code when the package is already installed;
    # that counts as success when the binary is actually usable.
    if ($null -ne (Find-FfmpegCommand)) {
      Write-Host 'ffmpeg was already installed; using it.'
      return
    }
    throw 'winget could not install ffmpeg.'
  }
  if ($null -eq (Find-FfmpegCommand)) {
    throw 'ffmpeg installed but is not on PATH yet (sign out and back in).'
  }
}

function Install-Tailscale {
  Write-Host 'Installing Tailscale (Windows may show an administrator approval dialog)...'
  $winget = Get-Command winget.exe, winget -ErrorAction SilentlyContinue |
    Select-Object -First 1
  if ($null -eq $winget) { throw 'winget is not available.' }
  & $winget.Source install -e --id Tailscale.Tailscale `
    --accept-source-agreements --accept-package-agreements
  if ($LASTEXITCODE -ne 0) { throw 'winget could not install Tailscale.' }
}

function Write-TailscaleSkipped {
  Write-Host ''
  Write-Host 'Skipping the private-network step. The dashboard will still'
  Write-Host 'work on THIS PC, but other devices cannot reach it yet.'
  Write-Host ''
  Write-Host 'The dashboard is local-first: it only answers this PC. If you'
  Write-Host 'later want it on another device, install Tailscale (or ZeroTier,'
  Write-Host 'Cloudflare Tunnel, a home VPN) and re-run this installer.'
  Write-Host 'Finding and setting up an alternative is your responsibility;'
  Write-Host 'the installer cannot do it for you.'
}

# ------------------------------------------------------------------ main ---

function Invoke-Uninstall($Root, $TaskName) {
  Write-Step "Removing the automatic start entry '$TaskName'"
  try { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue } catch { }
  Start-Sleep -Seconds 1
  Stop-OwnDashboard $Root
  try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    Write-Host 'Removed the automatic start entry.'
  } catch {
    Write-Host 'No automatic start entry was found (nothing to remove).'
  }
  $wrapper = Join-Path $Root '.runtime\start-dashboard.ps1'
  if (Test-Path $wrapper) { Remove-Item $wrapper -Force }
  Write-Host ''
  Write-Host 'Kept on purpose: .venv (program files),'
  Write-Host 'apps/workbench_dashboard/data (your chats, plans, runs, inbox),'
  Write-Host '.runtime (logs). Delete them by hand if you want'
  Write-Host 'a full removal.'
}

function Invoke-Installer {
  $root = Get-RepoRoot
  Confirm-Checkout $root
  if ($Port -lt 1 -or $Port -gt 65535) { throw "Port $Port is out of range (1-65535)." }
  $manualSteps = @()

  if ($Uninstall) {
    Invoke-Uninstall $root $TaskName
    return
  }

  Write-Step "AI Workbench dashboard setup ($root)"

  # 1. Python ----------------------------------------------------------
  $pythonExe = Find-Python
  if ($null -eq $pythonExe) {
    throw ('Python 3.12 or newer was not found. Install it from ' +
      'https://www.python.org/downloads/ (tick "Add python.exe to PATH"), ' +
      'then re-run this installer.')
  }
  Write-Host "Using Python: $pythonExe"

  # uv: faster installs using the project lockfile; offer to install it.
  if ($null -eq (Find-UvCommand)) {
    $wantsUv = $false
    if (-not $NonInteractive) {
      Write-Host 'uv (fast Python installer) was not found.'
      $wantsUv = Read-Choice 'Install uv now (winget)?' $true
    }
    if ($wantsUv) {
      try {
        Install-Uv
        Write-Host 'uv installed.'
      } catch {
        Write-Host "Could not install uv automatically: $($_.Exception.Message)"
        Write-Host 'Continuing with plain Python instead.'
      }
    } else {
      Write-Host 'Skipping uv; plain Python will be used instead.'
    }
  }

  # ffmpeg: voice dictation needs it to convert browser audio for transcription.
  if ($null -eq (Find-FfmpegCommand)) {
    $wantsFfmpeg = $false
    if (-not $NonInteractive) {
      Write-Host 'ffmpeg (audio converter for voice dictation) was not found.'
      $wantsFfmpeg = Read-Choice 'Install ffmpeg now (winget)?' $true
    }
    if ($wantsFfmpeg) {
      try {
        Install-Ffmpeg
        Write-Host 'ffmpeg installed.'
      } catch {
        Write-Host "Could not install ffmpeg automatically: $($_.Exception.Message)"
        $manualSteps += 'Install ffmpeg (winget install -e --id Gyan.FFmpeg) or voice dictation falls back to browser speech.'
      }
    } else {
      Write-Host 'Skipping ffmpeg; voice dictation will use browser speech instead.'
      $manualSteps += 'Install ffmpeg (winget install -e --id Gyan.FFmpeg) to enable server-side voice dictation.'
    }
  }

  # 2. Program files ---------------------------------------------------
  Write-Step 'Installing the program files'
  $venvPython = Ensure-Install $root $pythonExe
  Write-Host 'Program files are ready.'

  # 3. Dashboard config ------------------------------------------------
  Write-Step 'Checking the dashboard config'
  $configChanged = Ensure-DashboardConfig $root

  # 4. Private network (optional) --------------------------------------
  if ($NoTailscale -or $NonInteractive) {
    if ($null -eq (Find-Tailscale)) { Write-TailscaleSkipped }
  } elseif ($null -eq (Find-Tailscale)) {
    Write-Host 'Tailscale (private network for other devices) was not found.'
    if (Read-Choice 'Install Tailscale now (winget)?' $false) {
      try {
        Install-Tailscale
        Write-Host 'Tailscale installed. Sign in to the same account on each device,'
        Write-Host 'then re-run this installer to finish the address setup.'
      } catch {
        Write-Host "Could not install Tailscale automatically: $($_.Exception.Message)"
        Write-TailscaleSkipped
      }
    } else {
      Write-TailscaleSkipped
    }
  }

  # 5. Automatic start -------------------------------------------------
  Write-Step 'Registering the automatic start entry'
  $wrapper = Write-StartWrapper $root $Port $venvPython
  Register-DashboardTask $TaskName $root $wrapper.Path
  $started = Restart-DashboardTask $TaskName $root $configChanged
  if ($started -eq 'start-failed') {
    $manualSteps += 'The dashboard did not start automatically; start it by hand (see below) and read .runtime\dashboard.log.'
  }

  # 6. Health check ----------------------------------------------------
  Write-Step 'Checking that the dashboard answers'
  $answering = $false
  for ($i = 0; $i -lt 30; $i++) {
    if (Test-ServePort $Port) { $answering = $true; break }
    Start-Sleep -Seconds 1
  }
  if ($answering) {
    Write-Host "Dashboard is answering at http://127.0.0.1:$Port"
  } else {
    Write-Host "Dashboard is NOT answering on port $Port yet."
    Write-Host "If it stays silent, read '.runtime\dashboard.log' in the project folder."
    $manualSteps += 'Start the dashboard by hand (see below) and check .runtime\dashboard.log.'
  }

  # Summary ------------------------------------------------------------
  Write-Step 'Setup summary'
  Write-Host "Dashboard: http://127.0.0.1:$Port"
  Write-Host 'The dashboard also starts by itself every time you sign in to Windows.'
  Write-Host 'START IT YOURSELF (any time, from the project folder):'
  Write-Host '  powershell -ExecutionPolicy Bypass -File .\.runtime\start-dashboard.ps1'
  Write-Host "If something looks wrong, check '.runtime\dashboard.log' in the project folder."
  if ($manualSteps.Count -gt 0) {
    Write-Host ''
    Write-Host 'STILL TO DO BY HAND:'
    $n = 1
    foreach ($step in $manualSteps) {
      Write-Host "  $n. $step"
      $n++
    }
  }
  Write-Host ''
}

if ($MyInvocation.InvocationName -ne '.') {
  Invoke-Installer
}
