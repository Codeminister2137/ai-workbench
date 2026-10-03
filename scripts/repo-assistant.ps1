param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $CliArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    $scriptDirectory = Split-Path -Parent $PSCommandPath
    return (Resolve-Path (Join-Path $scriptDirectory "..")).Path
}

function Import-DotEnv {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }

        $name, $value = $trimmed -split "=", 2
        if (-not $name -or $null -eq $value) {
            continue
        }

        $cleanValue = $value.Trim()
        if (
            $cleanValue.Length -ge 2 -and
            (
                ($cleanValue.StartsWith('"') -and $cleanValue.EndsWith('"')) -or
                ($cleanValue.StartsWith("'") -and $cleanValue.EndsWith("'"))
            )
        ) {
            $cleanValue = $cleanValue.Substring(1, $cleanValue.Length - 2)
        }

        [Environment]::SetEnvironmentVariable($name.Trim(), $cleanValue, "Process")
    }
}

function Add-DefaultLogFile {
    param(
        [Parameter(Mandatory = $true)]
        [string[]] $Args,
        [Parameter(Mandatory = $true)]
        [string] $RepoRoot
    )

    if (
        $Args -contains "--log-file" -or
        $Args -contains "--local-capabilities" -or
        $Args -contains "--codex-login" -or
        $Args -contains "--codex-login-device"
    ) {
        return $Args
    }

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $artifactDirectory = Join-Path $RepoRoot "artifacts\repo-assistant-$timestamp"
    New-Item -ItemType Directory -Path $artifactDirectory -Force | Out-Null
    $logFile = Join-Path $artifactDirectory "assistant.log"

    $effectiveArgs = @($Args + @("--log-file", $logFile))
    if ($Args -notcontains "--ollama-log-file") {
        $effectiveArgs += @("--ollama-log-file", (Join-Path $artifactDirectory "ollama.log"))
    }
    return $effectiveArgs
}

$repoRoot = Get-RepoRoot
$envPath = Join-Path $repoRoot ".env"

Import-DotEnv -Path $envPath
Set-Location -LiteralPath $repoRoot

$effectiveCliArgs = Add-DefaultLogFile -Args $CliArgs -RepoRoot $repoRoot

& python -m uv run ai-assistant @effectiveCliArgs
exit $LASTEXITCODE
