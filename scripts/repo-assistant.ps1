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

$repoRoot = Get-RepoRoot
$envPath = Join-Path $repoRoot ".env"
$cliPath = Join-Path $repoRoot "packages\ai_provider\examples\repo_coding_assistant.py"

Import-DotEnv -Path $envPath
Set-Location -LiteralPath $repoRoot

& python -m uv run python $cliPath @CliArgs
exit $LASTEXITCODE
