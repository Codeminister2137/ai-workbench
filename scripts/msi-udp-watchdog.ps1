# MSI UDP watchdog (containment).
#
# Counts MSI.CentralServer UDP endpoints. Above THRESHOLD (a runaway leak;
# baseline is <100, the 2026-11-05 outage held 15,484), restarts the
# MSI_Center_Service to free the leaked ports, then recounts. Every action
# is recorded with before/after counts so leak frequency can be analysed
# later. Counts at/below threshold are silent except elevated (>500) notes.
#
# This complements scripts/udp-exhaustion-trap.ps1, which stays capture-only
# and fires on the Tcpip 4266 event itself.
#
# Incident record: <repo>/.tmp/msi-watchdog/incidents.log (gitignored).
# Scheduled task 'MsiUdpWatchdog' runs this daily (morning), elevated.
# Game guard: disruptive action is deferred while a game process runs.
# Disable: schtasks /change /tn MsiUdpWatchdog /disable

$ErrorActionPreference = 'Continue'
$THRESHOLD = 2000
$WATCH = 500
$SERVICE = 'MSI_Center_Service'
$PROCESS = 'MSI.CentralServer'
# Game guard: skip disruptive action while any of these run (extend freely).
$GAME_PROCESSES = @('deadlock')
$repo = 'C:\Users\Jakub\PycharmProjects\ai-workbench'
$dir = Join-Path $repo '.tmp\msi-watchdog'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$log = Join-Path $dir 'incidents.log'

function Get-MsiUdpCount {
    $udp = @(Get-NetUDPEndpoint -ErrorAction Stop | Where-Object { $_ -ne $null -and $_.OwningProcess })
    $total = $udp.Count
    $msi = 0
    $top = @()
    foreach ($group in ($udp | Group-Object OwningProcess | Sort-Object Count -Descending | Select-Object -First 5)) {
        $name = ''
        try { $name = (Get-Process -Id $group.Name -ErrorAction Stop).ProcessName } catch { $name = '?' }
        if ($name -eq $PROCESS) { $msi = $group.Count }
        $top += ("{0}={1}" -f $name, $group.Count)
    }
    return @{ msi = $msi; total = $total; top = ($top -join ', ') }
}

function Test-GameRunning {
    try {
        $running = @(Get-Process -ErrorAction Stop | Where-Object { $GAME_PROCESSES -contains $_.ProcessName })
        return ($running.Count -gt 0), (($running | Select-Object -ExpandProperty ProcessName) -join ',')
    } catch {
        return $false, ''
    }
}

$stamp = (Get-Date).ToString('o')
try {
    $snap = Get-MsiUdpCount
} catch {
    $line = "$stamp snapshot failed: $($_.Exception.Message)"
    $line | Out-File -FilePath $log -Append -Encoding utf8
    Write-Output $line
    exit 1
}

if ($snap.msi -le $WATCH) {
    Write-Output ("msi udp={0} total={1} (calm)" -f $snap.msi, $snap.total)
    exit 0
}
if ($snap.msi -le $THRESHOLD) {
    $line = "$stamp elevated (no action): msi udp=$($snap.msi) total=$($snap.total) top=[$($snap.top)]"
    $line | Out-File -FilePath $log -Append -Encoding utf8
    Write-Output $line
    exit 0
}

$before = $snap.msi
$gaming, $games = Test-GameRunning
if ($gaming) {
    $line = "$stamp DEFERRED (game running: $games): msi udp=$before; retry at next run"
    $line | Out-File -FilePath $log -Append -Encoding utf8
    Write-Output $line
    exit 0
}
$action = ''
try {
    Restart-Service -Name $SERVICE -Force -ErrorAction Stop
    $action = "restarted service $SERVICE"
} catch {
    $action = "service restart failed ($($_.Exception.Message))"
}
Start-Sleep -Seconds 10
try {
    $after = (Get-MsiUdpCount).msi
} catch {
    $after = -1
}
if ($after -ge 0 -and $after -ge $before) {
    # Restart did not free ports: they belong to MSI.CentralServer itself.
    try {
        Get-Process -Name $PROCESS -ErrorAction Stop | Stop-Process -Force
        $action += "; restart ineffective, killed $PROCESS"
    } catch {
        $action += '; restart ineffective, kill failed: ' + $_.Exception.Message
    }
    Start-Sleep -Seconds 10
    try {
        $after = (Get-MsiUdpCount).msi
    } catch {
        $after = -1
    }
}
$line = "$stamp LEAK ACTION: msi udp before=$before; $action; msi udp after=$after"
$line | Out-File -FilePath $log -Append -Encoding utf8
Write-Output $line
exit 0
