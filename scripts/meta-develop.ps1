param(
    [Parameter(Mandatory = $true)] [string] $RepoRoot,
    [string] $TaskFile,
    [Parameter(Mandatory = $true)] [string] $RunDirectory,
    [string] $PythonExecutable,
    [switch] $Check,
    [switch] $Chat,
    [string] $SessionDatabase
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$targetRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
if (!$Chat -and !$TaskFile) { throw '-TaskFile is required outside -Chat.' }
$taskPath = if ($TaskFile) { (Resolve-Path -LiteralPath $TaskFile).Path } else { $null }
$runPath = if ([IO.Path]::IsPathRooted($RunDirectory)) {
    [IO.Path]::GetFullPath($RunDirectory)
} else {
    [IO.Path]::GetFullPath((Join-Path (Get-Location).Path $RunDirectory))
}
if (!$PythonExecutable) {
    $PythonExecutable = Join-Path $projectRoot '.venv\Scripts\python.exe'
}
if (!(Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
    throw 'Pass -PythonExecutable with the configured project Python; no interpreter will be installed.'
}

# Use the existing development environment; do not import all Workbench .env values
# or change the caller's working directory. Python loads only the required Meta key.
$previousPythonPath = [Environment]::GetEnvironmentVariable('PYTHONPATH', 'Process')
$sourcePaths = @(
    (Join-Path $projectRoot 'packages\ai_provider\src'),
    (Join-Path $projectRoot 'packages\ai_orchestrator\src'),
    (Join-Path $projectRoot 'packages\ai_agent\src'),
    (Join-Path $projectRoot '.venv\Lib\site-packages')
)
if ($previousPythonPath) { $sourcePaths += $previousPythonPath }
$launcherArgs = @(
    (Join-Path $PSScriptRoot 'meta-develop.py'),
    '--repo-root', $targetRoot,
    '--run-dir', $runPath
)
if ($taskPath) { $launcherArgs += @('--task-file', $taskPath) }
if ($Chat) { $launcherArgs += '--chat' }
if ($SessionDatabase) { $launcherArgs += @('--session-db', (Resolve-Path -LiteralPath $SessionDatabase).Path) }
if ($Check) { $launcherArgs += '--check' }
$resultCode = 1
try {
    $env:PYTHONPATH = $sourcePaths -join [IO.Path]::PathSeparator
    & $PythonExecutable @launcherArgs
    $resultCode = $LASTEXITCODE
}
finally {
    [Environment]::SetEnvironmentVariable('PYTHONPATH', $previousPythonPath, 'Process')
}
exit $resultCode
