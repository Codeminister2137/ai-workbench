# Backup of company-sensitive working docs (NOT secrets).
# A: push allowlisted private dirs to the private ai-workbench-private repo.
# B: write a timestamped zip snapshot to a SECOND physical disk
#    (default G:\ai-workbench-backup; G: is disk 1, the C: checkout is disk 2).
#    Snapshot covers plans + library + research + data/ (incl. sqlite); push
#    stays plans + library only per the approved design (inbox 1b310ead A+B).
# Fail-closed: any denylisted filename (env/secret/credential/key material)
# anywhere in the staged set aborts before any push or zip is written, and a
# missing snapshot drive aborts instead of silently falling back to C:.
param(
    [switch] $NoPush,
    [switch] $NoSnapshot,
    [string] $RemoteUrl = "git@github.com:Codeminister2137/ai-workbench-private.git",
    [string] $SnapshotDir = "G:\ai-workbench-backup"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Sources = @("docs/library-private", "docs/plans")
$SnapshotSources = @("docs/library-private", "docs/plans", "research", "data", "apps/workbench_dashboard/data")
$DenyList = @("*.env", "*secret*", "*credential*", "*.pem", "*.key", "id_*", "*.pfx", "*.p12")
$MaxFileBytes = 25MB

function Get-StagedFiles([string[]] $Sets) {
    $files = @()
    foreach ($rel in $Sets) {
        $dir = Join-Path $RepoRoot $rel
        if (-not (Test-Path $dir)) { continue }
        $files += Get-ChildItem $dir -Recurse -File
    }
    return $files
}

function Invoke-Git([string[]] $GitArgs) {
    $errFile = [IO.Path]::GetTempFileName()
    $prevAction = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        $out = git @GitArgs 2>$errFile
        $code = $LASTEXITCODE
        $err = (Get-Content $errFile -Raw)
        if ($code -ne 0) { throw "git $($GitArgs -join ' ') failed: $out $err" }
        return "$out $err".Trim()
    } finally {
        $ErrorActionPreference = $prevAction
        Remove-Item $errFile -Force -ErrorAction SilentlyContinue
    }
}

function Assert-BackupSafe($files) {
    foreach ($file in $files) {
        foreach ($pattern in $DenyList) {
            if ($file.Name -like $pattern) {
                throw "Refusing backup: denylisted file $($file.FullName)"
            }
        }
        if ($file.Length -gt $MaxFileBytes) {
            throw "Refusing backup: oversized file $($file.FullName) ($($file.Length) bytes)"
        }
    }
}

$files = Get-StagedFiles $Sources
if ($files.Count -eq 0) { throw "Nothing to back up: no files under $($Sources -join ', ')" }
Assert-BackupSafe $files
$snapFiles = Get-StagedFiles $SnapshotSources
Assert-BackupSafe $snapFiles
Write-Host "Manifest: $($files.Count) push files, $($snapFiles.Count) snapshot files, $([math]::Round(($snapFiles | Measure-Object Length -Sum).Sum / 1KB, 1)) KB snapshot"

if (-not $NoSnapshot) {
    $snapDrive = Split-Path -Qualifier $SnapshotDir
    if (-not (Test-Path $snapDrive)) { throw "Snapshot drive missing: $snapDrive (refusing C: fallback)" }
    New-Item -ItemType Directory -Force -Path $SnapshotDir | Out-Null
    $stage = Join-Path ([IO.Path]::GetTempPath()) "wb-private-snap"
    if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
    foreach ($rel in $SnapshotSources) {
        $src = Join-Path $RepoRoot $rel
        if (Test-Path $src) { Copy-Item $src (Join-Path $stage $rel) -Recurse -Force }
    }
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $zip = Join-Path $SnapshotDir "private-$stamp.zip"
    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -Force
    Remove-Item $stage -Recurse -Force
    Write-Host "Snapshot: $zip"
}

if (-not $NoPush) {
    $clone = Join-Path ([IO.Path]::GetTempPath()) "wb-private-mirror"
    if (Test-Path $clone) { Remove-Item $clone -Recurse -Force }
    Invoke-Git @("clone", $RemoteUrl, $clone) | Out-Null
    Push-Location $clone
    try {
        try { Invoke-Git @("checkout", "main") | Out-Null }
        catch { try { Invoke-Git @("checkout", "-b", "main") | Out-Null } catch { } }
        @"
# ai-workbench private backup
Off-machine mirror of company-sensitive working docs from ai-workbench.
No secrets, credentials, or .env material may ever be committed here;
scripts/backup-private.ps1 refuses them before push.
"@ | Set-Content README.md -Encoding utf8 -NoNewline:$false
        @(".env", "*secret*", "*credential*", "*.pem", "*.key", "id_*", "*.pfx", "*.p12") |
            Set-Content .gitignore -Encoding utf8
        foreach ($rel in $Sources) {
            $src = Join-Path $RepoRoot $rel
            $dst = Join-Path $clone $rel
            if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
            if (Test-Path $src) { Copy-Item $src $dst -Recurse -Force }
        }
        Invoke-Git @("add", "-A") | Out-Null
        $changes = git status --porcelain
        if (-not $changes) {
            Write-Host "Push: no changes, already up to date"
        } else {
            $stamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ssZ")
            Invoke-Git @("commit", "-m", "Private backup $stamp ($($files.Count) files)", "--quiet") | Out-Null
            Write-Host (Invoke-Git @("push", "-u", "origin", "main"))
        }
    } finally {
        Pop-Location
        Remove-Item $clone -Recurse -Force
    }
}
