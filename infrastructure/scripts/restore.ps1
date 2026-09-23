#Requires -Version 5.1
<#
.SYNOPSIS
  Restore the PostgreSQL database (and optionally media) from a backup dump.

.DESCRIPTION
  Safety-first restore:
    1. verifies the archive (`pg_restore --list`);
    2. takes a fresh safety backup of the CURRENT database;
    3. stops the API + Telegram bot so nothing writes during the restore;
    4. restores with `--clean --if-exists`;
    5. restarts the API (which runs `alembic upgrade head` on start).

  The dump must live in infrastructure\backups (the bind-mounted backup dir).

.EXAMPLE
  .\restore.ps1 -Dump .\backups\stock_pos_20260923T101500Z.dump
  .\restore.ps1 -Dump .\backups\stock_pos_20260923T101500Z.dump -Media .\backups\media_20260923T101500Z.tgz
#>
param(
    [Parameter(Mandatory = $true)][string]$Dump,
    [string]$Media = "",
    [string]$ConfirmPhrase = "",
    [switch]$Force
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

$dumpPath = (Resolve-Path -LiteralPath $Dump).Path
if (-not $dumpPath.StartsWith($BackupDir)) {
    throw "The dump must live under $BackupDir so the container can read it."
}
$dumpName = Split-Path -Leaf $dumpPath

if (-not $Force -and $ConfirmPhrase -ne "RESTORE DATABASE") {
    throw 'Refusing to restore. Re-run with -ConfirmPhrase "RESTORE DATABASE" (or -Force).'
}

Write-Host "==> Verifying archive..." -ForegroundColor Cyan
Invoke-Compose --profile tools run --rm backup "pg_restore --list /backups/$dumpName > /dev/null && echo ARCHIVE_OK"

Write-Host "==> Taking a safety backup of the current database..." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "backup.ps1") -SkipMedia

Write-Host "==> Stopping API and Telegram bot..." -ForegroundColor Cyan
Invoke-Compose stop api telegram-bot

try {
    Write-Host "==> Restoring database..." -ForegroundColor Cyan
    Invoke-Compose --profile tools run --rm backup "pg_restore -h db -U `$PGUSER -d `$PGDATABASE --clean --if-exists --no-owner /backups/$dumpName"

    if ($Media) {
        $mediaPath = (Resolve-Path -LiteralPath $Media).Path
        if (-not $mediaPath.StartsWith($BackupDir)) { throw "Media archive must live under $BackupDir." }
        $mediaName = Split-Path -Leaf $mediaPath
        Write-Host "==> Restoring media volume..." -ForegroundColor Cyan
        Invoke-Compose --profile tools run --rm media-backup "rm -rf /media/* && tar xzf /backups/$mediaName -C /media && echo MEDIA_OK"
    }
}
finally {
    Write-Host "==> Restarting API (runs alembic upgrade head)..." -ForegroundColor Cyan
    Invoke-Compose up -d api telegram-bot
}

Write-Host "Restore complete. Verify the app, then confirm the safety backup can be removed." -ForegroundColor Green
