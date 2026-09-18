param(
    [Parameter(Position = 0)]
    [ValidateSet("init", "install", "pull-model", "start", "stop", "status", "cli", "list", "check")]
    [string] $Task = "status",

    [string] $Prompt = "",
    [string] $Conversation = "",
    [string] $Model = "llama3.2",
    [string] $HostName = "127.0.0.1",
    [int] $Port = 8765
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $Root "logs"
$OutLog = Join-Path $LogDir "council.out.log"
$ErrLog = Join-Path $LogDir "council.err.log"
$LocalConfig = Join-Path $Root "council.json"
$ExampleConfig = Join-Path $Root "council.example.json"

function Invoke-Init {
    if (Test-Path $LocalConfig) {
        Write-Host "Local config already exists: $LocalConfig"
        return
    }

    Copy-Item -Path $ExampleConfig -Destination $LocalConfig
    Write-Host "Created local config: $LocalConfig"
    Write-Host "Edit it before putting private model URLs, personas, or defaults into use."
}

function Get-CouncilProcess {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine.Contains("web_app.py") -and
            $_.CommandLine.Contains("--port") -and
            $_.CommandLine.Contains([string]$Port)
        }
}

function Invoke-Start {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

    $existing = Get-CouncilProcess
    if ($existing) {
        Write-Host "Council is already running at http://${HostName}:$Port"
        $existing | Select-Object ProcessId, CommandLine
        return
    }

    $arguments = @(
        "run",
        "python",
        "web_app.py",
        "--host",
        $HostName,
        "--port",
        [string]$Port
    )

    Start-Process `
        -FilePath "poetry" `
        -ArgumentList $arguments `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -RedirectStandardOutput $OutLog `
        -RedirectStandardError $ErrLog

    Start-Sleep -Seconds 2
    Write-Host "Council started at http://${HostName}:$Port"
    Write-Host "Logs:"
    Write-Host "  $OutLog"
    Write-Host "  $ErrLog"
}

function Invoke-Stop {
    $processes = Get-CouncilProcess
    if (-not $processes) {
        Write-Host "Council is not running on port $Port."
        return
    }

    foreach ($process in $processes) {
        Stop-Process -Id $process.ProcessId
        Write-Host "Stopped council process $($process.ProcessId)."
    }
}

function Invoke-Status {
    $processes = Get-CouncilProcess
    if (-not $processes) {
        Write-Host "Council is not running on port $Port."
        return
    }

    Write-Host "Council is running at http://${HostName}:$Port"
    $processes | Select-Object ProcessId, CommandLine
}

switch ($Task) {
    "init" {
        Invoke-Init
    }
    "install" {
        poetry install
    }
    "pull-model" {
        ollama pull $Model
    }
    "start" {
        Invoke-Start
    }
    "stop" {
        Invoke-Stop
    }
    "status" {
        Invoke-Status
    }
    "cli" {
        if (-not $Prompt.Trim()) {
            throw "Provide -Prompt when using the cli task."
        }

        $args = @("run", "python", "main.py")
        if ($Conversation.Trim()) {
            $args += @("--conversation", $Conversation)
        }
        $args += $Prompt
        poetry @args
    }
    "list" {
        poetry run python main.py --list-conversations
    }
    "check" {
        poetry check
        poetry run python -m py_compile agent.py config.py council.py domain.py main.py storage.py tools.py state.py web_app.py
        poetry run pytest
    }
}
