param(
    [Parameter(Mandatory = $true)] [string] $RepoRoot,
    [Parameter(Mandatory = $true)] [string] $TaskFile,
    [Parameter(Mandatory = $true)] [string] $RunDirectory,
    [string] $PythonExecutable,
    [switch] $Check
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$targetRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$taskPath = (Resolve-Path -LiteralPath $TaskFile).Path
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
    '--task-file', $taskPath,
    '--run-dir', $runPath
)
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
