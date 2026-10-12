#Requires -Version 5.1
<# Read-only bounded resource sampling. No process names or commands are emitted. #>
[CmdletBinding()]
param(
    [ValidateRange(1, 10000)][int]$SampleCount = 1,
    [ValidateRange(1, 3600)][int]$IntervalSeconds = 60,
    [datetimeoffset]$NotAfterUtc = [datetimeoffset]::MaxValue
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-ResourceCounterRows([string]$ClassName) {
    try {
        return @{ available = $true; rows = @(Get-CimInstance -Namespace root/cimv2 `
            -ClassName $ClassName -OperationTimeoutSec 5 -ErrorAction Stop) }
    } catch {
        # Missing counters and denied queries are unavailable, never idle/zero.
        return @{ available = $false; rows = @() }
    }
}

function ConvertTo-ResourceSnapshot([hashtable]$Samples) {
    $missing = [System.Collections.Generic.List[string]]::new()
    $cpuBusy = $null
    $memoryTotal = $null
    $memoryAvailable = $null
    $gpuBusy = $null
    $gpuDedicated = $null
    $gpuShared = $null
    try {
        $cpu = @($Samples.cpu.rows | Where-Object { $_.Name -eq '_Total' })
        if ($Samples.cpu.available -and $cpu.Count -eq 1) {
            if ($null -eq $cpu[0].PercentProcessorTime) { throw 'Unavailable CPU value' }
            $value = [double]$cpu[0].PercentProcessorTime
            if (-not [double]::IsNaN($value) -and $value -ge 0 -and $value -le 100) {
                $cpuBusy = $value
            }
        }
    } catch { }
    if ($null -eq $cpuBusy) { $missing.Add('cpu_busy') }
    try {
        if ($Samples.memory.available -and $Samples.memory.rows.Count -eq 1) {
            if ($null -eq $Samples.memory.rows[0].TotalVisibleMemorySize -or
                $null -eq $Samples.memory.rows[0].FreePhysicalMemory) { throw 'Unavailable memory' }
            $total = [decimal]$Samples.memory.rows[0].TotalVisibleMemorySize
            $free = [decimal]$Samples.memory.rows[0].FreePhysicalMemory
            if ($total -gt 0 -and $free -ge 0 -and $free -le $total) {
                $memoryTotal = [long]($total * 1024)
                $memoryAvailable = [long]($free * 1024)
            }
        }
    } catch { }
    if ($null -eq $memoryAvailable) { $missing.Add('memory') }
    try {
        $adapters = @($Samples.gpu_memory.rows | Where-Object { $_.Name -ne '_Total' })
        if ($Samples.gpu_memory.available -and $adapters.Count -gt 0) {
            [decimal]$dedicated = 0
            [decimal]$shared = 0
            foreach ($adapter in $adapters) {
                if ($null -eq $adapter.DedicatedUsage -or $null -eq $adapter.SharedUsage) {
                    throw 'Unavailable adapter memory'
                }
                $dedicated += [decimal]$adapter.DedicatedUsage
                $shared += [decimal]$adapter.SharedUsage
            }
            if ($dedicated -ge 0 -and $shared -ge 0) {
                $gpuDedicated = [long]$dedicated
                $gpuShared = [long]$shared
            }
        }
    } catch { }
    if ($null -eq $gpuDedicated) { $missing.Add('gpu_memory') }
    try {
        $engines = @{}
        if ($Samples.gpu_engines.available) {
            foreach ($row in $Samples.gpu_engines.rows) {
                # Counter instances are per process/engine. Sum one engine's
                # processes before taking the busiest engine; do not sum engines.
                if ($row.Name -notmatch '^pid_\d+_(luid_.+_phys_\d+_eng_\d+_engtype_.+)$') {
                    continue
                }
                $key = $Matches[1]
                if ($null -eq $row.UtilizationPercentage) { throw 'Unavailable GPU engine value' }
                $value = [double]$row.UtilizationPercentage
                if ([double]::IsNaN($value) -or $value -lt 0 -or $value -gt 100) {
                    throw 'Unavailable GPU engine value'
                }
                if (-not $engines.ContainsKey($key)) { $engines[$key] = 0.0 }
                $engines[$key] += $value
            }
        }
        if ($engines.Count -gt 0) {
            $gpuBusy = [math]::Min(100, ($engines.Values | Measure-Object -Maximum).Maximum)
        }
    } catch { }
    if ($null -eq $gpuBusy) { $missing.Add('gpu_engines') }
    [ordered]@{
        schema_version = 1
        sampled_at_utc = [datetimeoffset]::UtcNow.ToString('o')
        source = 'windows_cim'
        cpu_busy_percent = $cpuBusy
        memory_total_bytes = $memoryTotal
        memory_available_bytes = $memoryAvailable
        gpu_busiest_engine_percent_estimate = $gpuBusy
        gpu_dedicated_used_bytes = $gpuDedicated
        gpu_shared_used_bytes = $gpuShared
        # These counters do not expose a trustworthy per-adapter VRAM budget.
        gpu_dedicated_available_bytes = $null
        unavailable = @($missing.ToArray())
    }
}

function Get-WorkstationResourceSnapshot {
    ConvertTo-ResourceSnapshot @{
        cpu = Get-ResourceCounterRows 'Win32_PerfFormattedData_PerfOS_Processor'
        memory = Get-ResourceCounterRows 'Win32_OperatingSystem'
        gpu_memory = Get-ResourceCounterRows 'Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory'
        gpu_engines = Get-ResourceCounterRows 'Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine'
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    for ($index = 0; $index -lt $SampleCount; $index++) {
        if ([datetimeoffset]::UtcNow -ge $NotAfterUtc) { break }
        Get-WorkstationResourceSnapshot | ConvertTo-Json -Depth 4 -Compress
        if ($index + 1 -ge $SampleCount) { break }
        $remaining = ($NotAfterUtc - [datetimeoffset]::UtcNow).TotalSeconds
        if ($remaining -le 0) { break }
        Start-Sleep -Seconds ([math]::Min($IntervalSeconds, [math]::Ceiling($remaining)))
    }
}
