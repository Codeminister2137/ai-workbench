param(
    [string] $Prompt = "Investigate the next action for this repository and propose the smallest useful next milestone.",
    [string] $Provider = "ollama",
    [string] $Model = "deepseek-coder-v2:16b",
    [string] $LogFile = "",
    [string] $OllamaLogFile = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Keep the canonical broad-analysis workflow here. Append future quality gates
# or context flags to this argument list so repeated live tests evolve together.
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
if (-not $LogFile) {
    $LogFile = "logs\repo-assistant-broad-analysis-$timestamp.log"
}
if (-not $OllamaLogFile) {
    $OllamaLogFile = "logs\ollama-broad-analysis-$timestamp.log"
}

$cliArgs = @(
    "--mode", "ask",
    $Prompt,
    "--provider", $Provider,
    "--model", $Model,
    "--execute",
    "--start-ollama",
    "--scrutinize-response",
    "--log-full-prompt",
    "--log-file", $LogFile,
    "--ollama-log-file", $OllamaLogFile
)

& (Join-Path $PSScriptRoot "repo-assistant.ps1") @cliArgs
exit $LASTEXITCODE
