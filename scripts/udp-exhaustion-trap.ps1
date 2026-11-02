# UDP ephemeral-port exhaustion trap.
#
# Fired by the UDPPortExhaustionTrap scheduled task on Tcpip event 4266
# ("all UDP ports in use" - the outage that kills DNS while the link stays
# up). Capture only: snapshots which processes hold UDP endpoints so the
# leaker can be identified after the fact. Never kills, restarts, or
# reconfigures anything. Safe to run manually for a baseline.
#
# Log: <repo>/.tmp/udp-trap/trap.log (gitignored scratch, appended).

$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\Jakub\PycharmProjects\ai-workbench'
$dir = Join-Path $repo '.tmp\udp-trap'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$log = Join-Path $dir 'trap.log'

$stamp = (Get-Date).ToString('o') + ' / ' + [DateTime]::UtcNow.ToString("HH:mm'Z'")
$lines = @('', "=== UDP trap fired at $stamp ===")

try {
    $recent = @(Get-WinEvent -FilterHashtable @{LogName = 'System'; Id = 4266; StartTime = (Get-Date).AddHours(-1) } -ErrorAction SilentlyContinue)
    $lines += "Tcpip-4266 events in last hour: $($recent.Count)"
} catch {
    $lines += "Tcpip-4266 query failed: $($_.Exception.Message)"
}

try {
    $udp = @(Get-NetUDPEndpoint -ErrorAction Stop)
    $lines += "total UDP endpoints: $($udp.Count)"
    $groups = $udp | Group-Object OwningProcess | Sort-Object Count -Descending | Select-Object -First 15
    foreach ($g in $groups) {
        try {
            $proc = Get-Process -Id $g.Name -ErrorAction Stop
            $started = '?'
            try { $started = $proc.StartTime.ToString('HH:mm') } catch { $started = '(protected)' }
            $cmd = '(cmdline unavailable)'
            try {
                $cim = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $g.Name) -ErrorAction Stop
                if ($cim -and $cim.CommandLine) { $cmd = $cim.CommandLine }
            } catch { }
            $lines += ("pid={0} name={1} started={2} udp={3} cmd={4}" -f $g.Name, $proc.ProcessName, $started, $g.Count, $cmd)
        } catch {
            $lines += ("pid={0} udp={1} (details unavailable)" -f $g.Name, $g.Count)
        }
    }
} catch {
    $lines += "UDP snapshot failed: $($_.Exception.Message)"
}

$lines | Out-File -FilePath $log -Append -Encoding utf8
'wrote snapshot to ' + $log
