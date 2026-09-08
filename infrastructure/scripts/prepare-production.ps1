#Requires -Version 5.1
<#
.SYNOPSIS
  Prepare Stock & POS for a clean production-ready local/prod start.

.DESCRIPTION
  - Resets PostgreSQL business data (keeps SuperAdmin bootstrap)
  - Clears objects in the MinIO files bucket
  - Removes local Python/Node/tooling caches

  Does NOT rewrite .env secrets. Fill .env.production.example manually before a real deploy.
#>

param(
  [switch]$SkipMinio,
  [switch]$SkipDbReset,
  [switch]$SkipCacheClean
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $root

Write-Host "== Stock & POS production prepare ==" -ForegroundColor Cyan

if (-not $SkipDbReset) {
  Write-Host "Resetting database to bootstrap-only..." -ForegroundColor Yellow
  docker compose exec -T api python scripts/reset_db.py
}

if (-not $SkipMinio) {
  Write-Host "Clearing MinIO objects..." -ForegroundColor Yellow
  $user = if ($env:MINIO_ROOT_USER) { $env:MINIO_ROOT_USER } else { "minioadmin" }
  $pass = if ($env:MINIO_ROOT_PASSWORD) { $env:MINIO_ROOT_PASSWORD } else { "minioadmin123" }
  $bucket = if ($env:MINIO_BUCKET) { $env:MINIO_BUCKET } else { "stock-pos-files" }
  docker run --rm --entrypoint /bin/sh --network stockmanagement_default `
    minio/mc:RELEASE.2025-08-13T08-35-41Z `
    -c "mc alias set local http://minio:9000 $user $pass >/dev/null; mc rm --recursive --force --dangerous local/$bucket/ >/dev/null 2>&1; echo MinIO cleared"
}

if (-not $SkipCacheClean) {
  Write-Host "Cleaning local caches..." -ForegroundColor Yellow
  $paths = @(
    "tmp",
    "backend/.pytest_cache",
    "backend/.ruff_cache",
    "frontend/.nuxt",
    "frontend/.output",
    "frontend/.cache",
    ".ruff_cache",
    ".pytest_cache"
  )
  foreach ($path in $paths) {
    $full = Join-Path $root $path
    if (Test-Path $full) {
      Remove-Item -Recurse -Force $full
      Write-Host "  removed $path"
    }
  }
  Get-ChildItem -Path (Join-Path $root "backend") -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "Next:"
Write-Host "  1. Copy .env.production.example -> .env and set strong secrets"
Write-Host "  2. docker login ghcr.io"
Write-Host "  3. .\infrastructure\scripts\deploy-from-registry.ps1"
Write-Host "  4. Follow docs/PRODUCTION_CHECKLIST.md when available"
Write-Host "Login after reset uses SEED_ADMIN_EMAIL / SEED_ADMIN_PASSWORD from .env"
