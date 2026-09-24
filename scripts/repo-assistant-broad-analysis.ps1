param(
    [string] $Prompt = "Investigate the next action for this repository and propose the smallest useful next milestone.",
    [string] $Provider = "ollama",
    [string] $Model = "deepseek-coder-v2:16b",
    [string] $LogFile = "logs\repo-assistant-broad-analysis.log",
    [string] $OllamaLogFile = "logs\ollama-broad-analysis.log"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Keep the canonical broad-analysis workflow here. Append future quality gates
# or context flags to this argument list so repeated live tests evolve together.
$cliArgs = @(
    "--mode", "ask",
    $Prompt,
    "--provider", $Provider,
    "--model", $Model,
    "--execute",
    "--start-ollama",
    "--scrutinize-response",
    "--log-file", $LogFile,
    "--ollama-log-file", $OllamaLogFile
)

& (Join-Path $PSScriptRoot "repo-assistant.ps1") @cliArgs
exit $LASTEXITCODE
