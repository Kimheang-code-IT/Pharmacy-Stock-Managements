#Requires -Version 5.1
<#
.SYNOPSIS
  Restore the newest backup into a throwaway database to prove it is restorable.

.DESCRIPTION
  Creates a scratch database inside the `db` container, restores the newest
  dump into it with `pg_restore`, runs a sanity query, then drops the scratch
  database. The production database is never touched.

.EXAMPLE
  .\restore-test.ps1
#>
param(
    [string]$Dump = "",
    [string]$ScratchDb = "stock_pos_restore_test"
)

$ErrorActionPreference = "Stop"

$Infra = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $Infra "docker-compose.yml"
$BackupDir = Join-Path $Infra "backups"

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    & docker compose -f $ComposeFile --project-directory $Infra @Args
    if ($LASTEXITCODE -ne 0) { throw "docker compose $($Args -join ' ') failed (exit $LASTEXITCODE)" }
}

function Run-BackupShell {
    param([string]$Command)
    Invoke-Compose --profile tools run --rm backup $Command
}

if (-not $Dump) {
    $newest = Get-ChildItem -Path $BackupDir -Filter "stock_pos_*.dump" -File |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($null -eq $newest) { throw "No dump found in $BackupDir" }
    $Dump = $newest.FullName
}
$dumpPath = (Resolve-Path -LiteralPath $Dump).Path
if (-not $dumpPath.StartsWith($BackupDir)) { throw "Dump must live under $BackupDir." }
$dumpName = Split-Path -Leaf $dumpPath

Write-Host "==> Restore test for $dumpName into '$ScratchDb'..." -ForegroundColor Cyan
Run-BackupShell "psql -h db -U `$PGUSER -d postgres -c 'DROP DATABASE IF EXISTS $ScratchDb'"
Run-BackupShell "psql -h db -U `$PGUSER -d postgres -c 'CREATE DATABASE $ScratchDb'"
Run-BackupShell "pg_restore -h db -U `$PGUSER -d $ScratchDb --no-owner /backups/$dumpName"
Run-BackupShell "psql -h db -U `$PGUSER -d $ScratchDb -tAc `"SELECT count(*) FROM information_schema.tables WHERE table_schema='public'`""
Run-BackupShell "psql -h db -U `$PGUSER -d postgres -c 'DROP DATABASE IF EXISTS $ScratchDb'"
Write-Host "Restore test passed: the backup is restorable." -ForegroundColor Green
