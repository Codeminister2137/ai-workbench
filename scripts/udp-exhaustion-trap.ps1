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

function Get-UdpOwnerGroups {
    # Primary: CIM-based endpoints. Filters nulls (CIM races emit them and
    # broke the 2026-11-02 firing's owner snapshot).
    try {
        $udp = @(Get-NetUDPEndpoint -ErrorAction Stop | Where-Object { $_ -ne $null -and $_.OwningProcess })
        $groups = @($udp | Group-Object OwningProcess | Sort-Object Count -Descending | Select-Object -First 15)
        return @{ total = $udp.Count; groups = $groups; via = 'cim' }
    } catch {
        $cimErr = $_.Exception.Message
    }
    # Fallback: netstat parsing (no CIM dependency).
    try {
        $pids = @()
        foreach ($line in (netstat -ano -p udp)) {
            if ($line -match '^\s*UDP\s+\S+\s+\S+\s+(\d+)\s*$') { $pids += $Matches[1] }
        }
        $groups = @($pids | Group-Object | Sort-Object Count -Descending | Select-Object -First 15)
        return @{ total = $pids.Count; groups = $groups; via = ("netstat (cim failed: $cimErr)") }
    } catch {
        throw "both cim and netstat snapshots failed: $cimErr / $($_.Exception.Message)"
    }
}

try {
    $snap = Get-UdpOwnerGroups
    $lines += "total UDP endpoints: $($snap.total) via $($snap.via)"
    $groups = $snap.groups
    foreach ($g in $groups) {
        if (-not $g.Name) { $lines += ("pid=? udp={0} (no owner)" -f $g.Count); continue }
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
