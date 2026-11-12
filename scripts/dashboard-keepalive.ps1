# Workbench dashboard + Ollama keep-alive.
#
# Probes http://127.0.0.1:8766/api/status and http://127.0.0.1:11434/api/tags;
# recovers whichever does not answer. The dashboard is recovered through the
# redeploy supervisor (pinned serve-branch worktree + main data/root), never
# by launching the dev checkout directly: a direct launch serves whatever
# branch happens to be checked out (proven 2026-11-12: an unmerged feature
# branch went live after a reboot). Safe to run manually for a status check.
#
# Log: <repo>/.tmp/dashboard-keepalive/keepalive.log (gitignored scratch).
# Scheduled task 'WorkbenchDashboard' runs this every 5 minutes at user logon.
# Disable: Unregister-ScheduledTask -TaskName WorkbenchDashboard -Confirm:$false

$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\Jakub\PycharmProjects\ai-workbench'
$ollamaExe = 'C:\Users\Jakub\AppData\Local\Programs\Ollama\ollama.exe'
$dir = Join-Path $repo '.tmp\dashboard-keepalive'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$log = Join-Path $dir 'keepalive.log'

function Test-Endpoint($url) {
    try {
        return (Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8).StatusCode -eq 200
    } catch {
        return $false
    }
}

$stamp = (Get-Date).ToString('o')
$failures = @()

if (Test-Endpoint 'http://127.0.0.1:8766/api/status') {
    'dashboard up at ' + $stamp
} else {
    $superviseOut = & (Join-Path $repo 'scripts\dashboard-supervise.cmd') 2>&1 | Out-String
    Start-Sleep -Seconds 5
    $recovered = Test-Endpoint 'http://127.0.0.1:8766/api/status'
    $line = "$stamp dashboard was down; supervisor tick attempted; up_after_restart=$recovered; tick=$($superviseOut.Trim())"
    $line | Out-File -FilePath $log -Append -Encoding utf8
    $line
    if (-not $recovered) { $failures += 'dashboard' }
}

if (Test-Endpoint 'http://127.0.0.1:11434/api/tags') {
    'ollama up at ' + $stamp
} else {
    Start-Process -WindowStyle Hidden -FilePath $ollamaExe -ArgumentList 'serve' `
        -RedirectStandardOutput (Join-Path $env:TEMP 'ollama-serve.log') `
        -RedirectStandardError (Join-Path $env:TEMP 'ollama-serve.err.log')
    Start-Sleep -Seconds 12
    $recovered = Test-Endpoint 'http://127.0.0.1:11434/api/tags'
    $line = "$stamp ollama was down; restart attempted; up_after_restart=$recovered"
    $line | Out-File -FilePath $log -Append -Encoding utf8
    $line
    if (-not $recovered) { $failures += 'ollama' }
}

if ($failures.Count -eq 0) { exit 0 } else { exit 1 }
