# Weekly wake-path self-test wrapper: run with the repo venv.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repo
& "$repo\.venv\Scripts\python.exe" "$repo\scripts\wake-self-test.py" @args
exit $LASTEXITCODE
