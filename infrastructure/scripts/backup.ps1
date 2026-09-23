#Requires -Version 5.1
<#
.SYNOPSIS
  Timestamped, verified backups of the PostgreSQL database and the media volume.

.DESCRIPTION
  Runs the one-shot `backup` and `media-backup` Compose services (profile
  "tools"), writes timestamped artifacts into infrastructure\backups, verifies
  the newest dump with `pg_restore --list`, and prunes files older than the
  retention window.

  Backups are never committed (see .gitignore). Secrets are read from
  infrastructure\.env and are never printed.

.EXAMPLE
  .\backup.ps1
  .\backup.ps1 -RetentionDays 30 -SkipMedia
#>
param(
    [string]$BackupDir = "",
    [int]$RetentionDays = 14,
    [switch]$SkipMedia
)

$ErrorActionPreference = "Stop"

$Infra = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $Infra "docker-compose.yml"
if (-not $BackupDir) { $BackupDir = Join-Path $Infra "backups" }
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    & docker compose -f $ComposeFile --project-directory $Infra @Args
    if ($LASTEXITCODE -ne 0) { throw "docker compose $($Args -join ' ') failed (exit $LASTEXITCODE)" }
}

Write-Host "==> Backing up PostgreSQL..." -ForegroundColor Cyan
Invoke-Compose --profile tools run --rm backup

if (-not $SkipMedia) {
    Write-Host "==> Backing up the media volume..." -ForegroundColor Cyan
    Invoke-Compose --profile tools run --rm media-backup
}

# --- Verify the newest dump -------------------------------------------------
$dump = Get-ChildItem -Path $BackupDir -Filter "stock_pos_*.dump" -File |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($null -eq $dump) { throw "No database dump was produced in $BackupDir" }

Write-Host "==> Verifying $($dump.Name)..." -ForegroundColor Cyan
# pg_restore --list parses the archive; a non-zero exit means a corrupt dump.
Invoke-Compose --profile tools run --rm backup "pg_restore --list /backups/$($dump.Name) > /dev/null && echo BACKUP_VERIFIED"
Write-Host "Backup verified: $($dump.FullName) ($([math]::Round($dump.Length/1KB)) KB)" -ForegroundColor Green

# --- Retention --------------------------------------------------------------
$cutoff = (Get-Date).AddDays(-1 * [math]::Abs($RetentionDays))
$pruned = 0
Get-ChildItem -Path $BackupDir -File |
    Where-Object { $_.LastWriteTime -lt $cutoff } |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force; $pruned++ }
if ($pruned -gt 0) {
    Write-Host "Pruned $pruned backup file(s) older than $RetentionDays day(s)." -ForegroundColor Yellow
}
Write-Host "Done. Backups in $BackupDir" -ForegroundColor Green
