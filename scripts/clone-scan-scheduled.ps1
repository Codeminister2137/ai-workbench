# Weekly clone-scan wrapper: run the scheduled scanner with the repo venv.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repo
& "$repo\.venv\Scripts\python.exe" "$repo\scripts\clone-scan-scheduled.py" @args
exit $LASTEXITCODE
