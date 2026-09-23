param(
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

function Write-Item($Label, $Value) {
    if (-not $Quiet) {
        Write-Output ("{0}: {1}" -f $Label, $Value)
    }
}

$repoRoot = git rev-parse --show-toplevel 2>$null
if (-not $repoRoot) {
    throw "Not inside a Git repository."
}

Set-Location $repoRoot

$branch = git branch --show-current
$statusLines = @(git status --short)
$contextPath = Join-Path $repoRoot "CURRENT_CONTEXT.md"
$hasContext = Test-Path $contextPath
$contextAgeHours = $null

if ($hasContext) {
    $contextAgeHours = [math]::Round(
        ((Get-Date) - (Get-Item $contextPath).LastWriteTime).TotalHours,
        1
    )
}

Write-Item "repo" $repoRoot
Write-Item "branch" $branch
Write-Item "uncommitted_changes" $statusLines.Count
Write-Item "current_context" $(if ($hasContext) { "present, age_hours=$contextAgeHours" } else { "missing" })

if ($statusLines.Count -gt 0 -and -not $Quiet) {
    Write-Output ""
    Write-Output "git_status:"
    $statusLines | ForEach-Object { Write-Output "  $_" }
}

$recommendation = "continue current chat"
$reasons = New-Object System.Collections.Generic.List[string]

if (-not $hasContext) {
    $recommendation = "do not switch yet"
    $reasons.Add("CURRENT_CONTEXT.md is missing; update a handoff before switching.")
}
elseif ($statusLines.Count -gt 0) {
    $recommendation = "do not switch yet"
    $reasons.Add("There are uncommitted changes; finish, validate, or capture the exact mid-change state first.")
}
else {
    $recommendation = "update handoff then start new chat"
    $reasons.Add("The worktree is clean and a handoff exists, so switching is low-risk if the next task is distinct.")
}

if ($contextAgeHours -ne $null -and $contextAgeHours -gt 24) {
    $recommendation = "do not switch yet"
    $reasons.Add("CURRENT_CONTEXT.md is older than 24 hours; refresh it before relying on it.")
}

Write-Output ""
Write-Output "recommendation: $recommendation"
$reasons | ForEach-Object { Write-Output "reason: $_" }
Write-Output "ide_status_needed: Run /status in the PyCharm Codex chat when context pressure, rate limits, or compaction symptoms matter; this script cannot inspect private IDE chat state."
