# Serve every local workbench service with one command.
#
# Starts (only what is down) and verifies: dashboard :8766, Ollama :11434,
# and the tailnet mapping for remote dashboard access. Appending a service
# means adding one entry to $services below: name, probe URL, and a start
# block that leaves the service running detached.
#
# Usage:  .\serve.cmd            (from the repo root)
#         powershell -NoProfile -ExecutionPolicy Bypass -File scripts/serve-all.ps1
# Logs: TEMP files per service (dashboard-8766.log, ollama-serve.log).

$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\Jakub\PycharmProjects\ai-workbench'

function Test-Endpoint($url, $timeoutSec = 8) {
    try {
        return (Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec $timeoutSec).StatusCode -eq 200
    } catch {
        return $false
    }
}

function Wait-Endpoint($url, $seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Endpoint $url) { return $true }
        Start-Sleep -Seconds 3
    }
    return $false
}

$services = @(
    @{
        Name = 'dashboard'
        Probe = 'http://127.0.0.1:8766/api/status'
        Start = {
            Start-Process -WindowStyle Hidden `
                -FilePath (Join-Path $repo '.venv\Scripts\python.exe') `
                -ArgumentList 'dashboard_web_app.py', '--host', '127.0.0.1', '--port', '8766' `
                -WorkingDirectory (Join-Path $repo 'apps\workbench_dashboard') `
                -RedirectStandardOutput (Join-Path $env:TEMP 'dashboard-8766.log') `
                -RedirectStandardError (Join-Path $env:TEMP 'dashboard-8766.err.log')
        }.GetNewClosure()
        WaitSeconds = 15
    },
    @{
        Name = 'ollama'
        Probe = 'http://127.0.0.1:11434/api/tags'
        Start = {
            Start-Process -WindowStyle Hidden `
                -FilePath 'C:\Users\Jakub\AppData\Local\Programs\Ollama\ollama.exe' `
                -ArgumentList 'serve' `
                -RedirectStandardOutput (Join-Path $env:TEMP 'ollama-serve.log') `
                -RedirectStandardError (Join-Path $env:TEMP 'ollama-serve.err.log')
        }.GetNewClosure()
        WaitSeconds = 60
    }
)

$failed = @()
foreach ($service in $services) {
    if (Test-Endpoint $service.Probe) {
        "$($service.Name): already up"
        continue
    }
    "$($service.Name): down, starting..."
    & $service.Start
    if (Wait-Endpoint $service.Probe $service.WaitSeconds) {
        "$($service.Name): started"
    } else {
        "$($service.Name): STILL DOWN after $($service.WaitSeconds)s"
        $failed += $service.Name
    }
}

$serveStatus = (tailscale.exe serve status 2>&1 | Out-String)
if ($serveStatus -match '127\.0\.0\.1:8766') {
    'tailnet: mapping present'
} else {
    'tailnet: mapping missing, applying...'
    tailscale.exe serve --bg http://127.0.0.1:8766 2>&1 | Select-Object -Last 1
    $serveStatus = (tailscale.exe serve status 2>&1 | Out-String)
    if ($serveStatus -match '127\.0\.0\.1:8766') { 'tailnet: mapping applied' }
    else { 'tailnet: MAPPING FAILED'; $failed += 'tailnet' }
}

try {
    $remote = Invoke-WebRequest -Uri 'https://desktop-j2m5erf.tailc59785.ts.net/api/status' -UseBasicParsing -TimeoutSec 15
    'remote dashboard: HTTP ' + $remote.StatusCode
} catch {
    'remote dashboard: UNREACHABLE (' + $_.Exception.Message + ')'
    $failed += 'remote-check'
}

if ($failed.Count -eq 0) { 'ALL SERVICES UP'; exit 0 } else { 'FAILED: ' + ($failed -join ', '); exit 1 }
