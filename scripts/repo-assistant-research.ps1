param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string] $Request,
    [string] $Topic = "custom_research",
    [double] $AwayMinutes = 110,
    [string] $Provider = "ollama",
    [string] $Model = "gpt-oss:20b",
    [ValidateSet("auto", "tavily", "brave", "searxng", "none")]
    [string] $SearchProvider = "auto",
    [ValidateSet("standard", "reduced_tracking", "disabled")]
    [string] $SearchPrivacy = "standard",
    [string] $LogFile = "",
    [string] $OllamaLogFile = "",
    [string] $OutputFile = "",
    [string[]] $SourceUrl = @(),
    [ValidateRange(1, 2147483647)]
    [Nullable[int]] $MaxSources = $null,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $CliArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function ConvertTo-LegacyNativeArgument {
    param([string] $Value)

    # Windows PowerShell rebuilds a native command line and otherwise drops quotes.
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    if ($Value -match '\s') {
        $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    }
    return $escaped
}

function ConvertTo-SafeTopic {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Value
    )

    $safe = $Value.ToLowerInvariant() -replace "[^a-z0-9]+", "_"
    $safe = $safe.Trim("_")
    if (-not $safe) {
        return "custom_research"
    }
    return $safe
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$safeTopic = ConvertTo-SafeTopic -Value $Topic
$artifactDirectory = "artifacts\research-${safeTopic}-${timestamp}"

if (-not $OutputFile) {
    $OutputFile = "$artifactDirectory\report.md"
}
if (-not $LogFile) {
    $LogFile = "$artifactDirectory\assistant.log"
}
if (-not $OllamaLogFile) {
    $OllamaLogFile = "$artifactDirectory\ollama.log"
}

$sourceHints = if ($SourceUrl.Count) { "Start with these public source URLs:`n" + ($SourceUrl -join "`n") } else { "" }
$prompt = @"
Conduct an extensive unattended internet research run for this repository.

User research request:
$Request
$sourceHints

Requirements:
- Use local model/runtime only. Do not use Codex CLI, ChatGPT, OpenAI API, Requesty, Google, or any paid/cloud AI route.
- Use search_web when available to discover public source URLs, then fetch_url to retrieve them. Search snippets are discovery only. Never send private prompts, secrets, or workspace content to search providers. Use write_research_report/read_research_report for the configured report. Shell, generic editing, and delegation are unavailable.
- Cross-check claims against multiple sources where practical.
- Prefer primary sources first: provider docs, model cards, official announcements, benchmark pages, and reputable public leaderboards.
- Clearly separate verified facts from inference.
- Include source URLs and access dates.
- Use Markdown headings for all eight report sections listed below; give each section substantive content.
- In Source map, declare every source URL with an optional unique ID such as S1, its retrieval status (fetched or not fetched), and its actual access date in YYYY-MM-DD when fetched. Never invent an access date for a source not fetched.
- Source map may use table rows, bullets with continuation lines, or source subsections. Example row: | S1 | https://provider.example/docs | YYYY-MM-DD | fetched |. Replace placeholders with actual evidence.
- Label every candidate fact/model entry as verified, inferred, unknown, or stale-risk. Cite its declared URL or [S1] ID in the same entry; unsupported entries must be unknown. Only use verified when supporting sources were actually fetched.
- Put all cited URLs in Source map, and explicitly describe unknowns or uncertainties in the risks section, even if none remain.
- In Repair checks performed, report only checks actually executed and their results; the deterministic gate checks structure and current-run fetch/write receipts, but cannot establish factual truth.
- Run scrutiny/repair passes before finishing.
- Continue improving until the away-time limit is close or there is nothing material left to improve.
- Do not edit repository source files.
- Write the final report to exactly: $OutputFile
- Write a useful first report early, then improve it. The 7,000-visible-character guideline is advisory; length alone does not fail completion or require repair. Give each section substantive coverage without filler. Do not spend the whole run fetching without saving a report.

Final report structure:
1. Executive summary
2. Source map
3. Candidate models, practices, or facts to add/revisit
4. Recommended fields, metrics, or decision criteria
5. Provider/source-specific notes
6. Risks, stale-data warnings, and unknowns
7. Suggested next implementation slice
8. Repair checks performed
"@

$baseArgs = @(
    $prompt,
    "--mode", "implement",
    "--provider", $Provider,
    "--model", $Model,
    "--privacy", "local_only",
    "--cost-policy", "local_only",
    "--quality", "standard",
    "--execute",
    "--native-tools",
    "--tool-profile", "research",
    "--research-report", $OutputFile,
    "--search-provider", $SearchProvider,
    "--search-privacy", $SearchPrivacy,
    "--away-run-db", "$artifactDirectory\runs.sqlite3",
    "--max-action-rounds", "40",
    "--timeout-seconds", "300",
    "--start-ollama",
    "--approval-policy", "trusted_local",
    "--away-minutes", "$AwayMinutes",
    "--orchestrated",
    "--max-repair-cycles", "-1",
    "--log-file", $LogFile,
    "--ollama-log-file", $OllamaLogFile
)

$effectiveArgs = @($baseArgs)
if ($null -ne $MaxSources) {
    $effectiveArgs += @("--research-max-sources", "$MaxSources")
}
if ($null -ne $CliArgs) {
    $effectiveArgs += @($CliArgs | Where-Object { $_ -ne "" })
}

Push-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
try {
    $uvArgs = @("run")
    if (Test-Path -LiteralPath ".env") {
        $uvArgs += @("--env-file", ".env")
    }
    $uvArgs += @("python", "-m", "ai_provider.research_runner")
    $nativeArgs = @("-m", "uv") + $uvArgs + $effectiveArgs
    $nativePassing = Get-Variable -Name PSNativeCommandArgumentPassing -ValueOnly -ErrorAction SilentlyContinue
    if (-not $nativePassing -or $nativePassing -eq "Legacy") {
        $nativeArgs = @($nativeArgs | ForEach-Object { ConvertTo-LegacyNativeArgument $_ })
    }
    & python @nativeArgs
    $researchExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $researchExitCode
