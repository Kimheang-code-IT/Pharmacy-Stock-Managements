#Requires -Version 5.1
<#
.SYNOPSIS
  Prepare Stock & POS for a clean local-only start on this PC.

.DESCRIPTION
  - Creates infrastructure\.env with strong random secrets when missing
  - Removes local Python/Node/tooling caches and build output
  - Prints the image-build / start steps

  Does NOT touch database volumes or rewrite an existing `.env`.
#>

param(
  [switch]$SkipEnv,
  [switch]$SkipCacheClean
)

$ErrorActionPreference = "Stop"
$infra = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$repoRoot = (Resolve-Path (Join-Path $infra "..")).Path

Write-Host "== Stock & POS local prepare ==" -ForegroundColor Cyan

if (-not $SkipEnv) {
  if (Test-Path (Join-Path $infra ".env")) {
    Write-Host "infrastructure\.env already exists — leaving it unchanged." -ForegroundColor Yellow
  } else {
    & (Join-Path $infra "scripts\init-env.ps1")
  }
}

if (-not $SkipCacheClean) {
  Write-Host "Cleaning local caches..." -ForegroundColor Yellow
  $paths = @(
    "tmp",
    "backend\.pytest_cache",
    "backend\.ruff_cache",
    "frontend\.nuxt",
    "frontend\.output",
    "frontend\.cache",
    ".ruff_cache",
    ".pytest_cache"
  )
  foreach ($path in $paths) {
    $full = Join-Path $repoRoot $path
    if (Test-Path $full) {
      Remove-Item -Recurse -Force $full
      Write-Host "  removed $path"
    }
  }
  Get-ChildItem -Path (Join-Path $repoRoot "backend") -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "Next:"
Write-Host "  1. (Optional) configure Telegram in Administration > Settings after first login"
Write-Host "  2. Build and start: .\infrastructure\scripts\install-client.ps1"
Write-Host "     or for GHCR images: .\infrastructure\scripts\deploy-from-registry.ps1"
Write-Host "  3. Daily use: double-click infrastructure\Start Stock POS.bat"
Write-Host "No data is seeded: create the first administrator on the Setup page."
