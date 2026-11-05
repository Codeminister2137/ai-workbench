# Workbench dashboard keep-alive.
#
# Probes http://127.0.0.1:8766/api/status; starts the dashboard when it does
# not answer. Never stops, kills, or reconfigures anything. Safe to run
# manually for a status check.
#
# Log: <repo>/.tmp/dashboard-keepalive/keepalive.log (gitignored scratch).
# Scheduled task 'WorkbenchDashboard' runs this every 5 minutes at user logon.
# Disable: Unregister-ScheduledTask -TaskName WorkbenchDashboard -Confirm:$false

$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\Jakub\PycharmProjects\ai-workbench'
$dir = Join-Path $repo '.tmp\dashboard-keepalive'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$log = Join-Path $dir 'keepalive.log'

$stamp = (Get-Date).ToString('o')
$up = $false
try {
    $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8766/api/status' -UseBasicParsing -TimeoutSec 8
    $up = ($response.StatusCode -eq 200)
} catch {
    $up = $false
}

if ($up) {
    'dashboard up at ' + $stamp
    exit 0
}

Start-Process -WindowStyle Hidden `
    -FilePath (Join-Path $repo '.venv\Scripts\python.exe') `
    -ArgumentList 'dashboard_web_app.py', '--host', '127.0.0.1', '--port', '8766' `
    -WorkingDirectory (Join-Path $repo 'apps\workbench_dashboard') `
    -RedirectStandardOutput (Join-Path $env:TEMP 'dashboard-8766.log') `
    -RedirectStandardError (Join-Path $env:TEMP 'dashboard-8766.err.log')
Start-Sleep -Seconds 5
$recovered = $false
try {
    $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8766/api/status' -UseBasicParsing -TimeoutSec 8
    $recovered = ($response.StatusCode -eq 200)
} catch {
    $recovered = $false
}
$line = "$stamp dashboard was down; restart attempted; up_after_restart=$recovered"
$line | Out-File -FilePath $log -Append -Encoding utf8
$line
if ($recovered) { exit 0 } else { exit 1 }
