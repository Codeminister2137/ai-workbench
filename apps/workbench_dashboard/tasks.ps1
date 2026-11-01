param(
    [Parameter(Position = 0)]
    [ValidateSet("init", "start", "stop", "status")]
    [string] $Task = "status",

    [string] $HostName = "127.0.0.1",
    [int] $Port = 8766
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $Root "logs"
$OutLog = Join-Path $LogDir "dashboard.out.log"
$ErrLog = Join-Path $LogDir "dashboard.err.log"
$LocalConfig = Join-Path $Root "dashboard.json"
$ExampleConfig = Join-Path $Root "dashboard.example.json"

function Invoke-Init {
    if (Test-Path $LocalConfig) {
        Write-Host "Local config already exists: $LocalConfig"
        return
    }
    Copy-Item -Path $ExampleConfig -Destination $LocalConfig
    Write-Host "Created local config: $LocalConfig"
    Write-Host "Edit the provider/model before use; never commit secrets."
}

function Get-DashboardProcess {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine.Contains("workbench_dashboard") -and
            $_.CommandLine.Contains("dashboard_web_app.py") -and
            $_.CommandLine.Contains("--port") -and
            $_.CommandLine.Contains([string]$Port)
        }
}

function Invoke-Start {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    $existing = Get-DashboardProcess
    if ($existing) {
        Write-Host "Dashboard is already running at http://${HostName}:$Port"
        $existing | Select-Object ProcessId, CommandLine
        return
    }
    $repoRoot = Split-Path -Parent (Split-Path -Parent $Root)
    $python = Join-Path $repoRoot ".venv\Scripts\python.exe"
    $env:PYTHONPATH = @(
        (Join-Path $repoRoot "packages\ai_provider\src"),
        (Join-Path $repoRoot "packages\ai_orchestrator\src"),
        (Join-Path $repoRoot "packages\ai_agent\src")
    ) -join ";"
    $arguments = "dashboard_web_app.py --host $HostName --port $Port"
    $process = Start-Process -FilePath $python -ArgumentList $arguments `
        -WorkingDirectory $Root -RedirectStandardOutput $OutLog `
        -RedirectStandardError $ErrLog -PassThru
    Start-Sleep -Seconds 2
    if ($process.HasExited) {
        Write-Host "Dashboard failed to start; see $ErrLog"
        Get-Content $ErrLog -Tail 20
        exit 1
    }
    Write-Host "Dashboard running at http://${HostName}:$Port (PID $($process.Id))"
}

function Invoke-Stop {
    $existing = Get-DashboardProcess
    if (-not $existing) {
        Write-Host "Dashboard is not running on port $Port"
        return
    }
    $existing | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force
        Write-Host "Stopped dashboard PID $($_.ProcessId)"
    }
}

function Invoke-Status {
    $existing = Get-DashboardProcess
    if ($existing) {
        Write-Host "Dashboard is running at http://${HostName}:$Port"
        $existing | Select-Object ProcessId, CommandLine
    } else {
        Write-Host "Dashboard is not running on port $Port"
    }
}

switch ($Task) {
    "init" { Invoke-Init }
    "start" { Invoke-Start }
    "stop" { Invoke-Stop }
    "status" { Invoke-Status }
}
