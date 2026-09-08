#Requires -Version 5.1
<#
.SYNOPSIS
  Pull Stock & POS images from GitHub Container Registry and start production.

.DESCRIPTION
  Uses docker-compose.yml + docker-compose.prod.yml. Does not build images locally.
  Requires `.env` (copy from `.env.production.example`) and docker login to ghcr.io.
#>

param(
  [string]$Tag = "",
  [string]$Registry = "",
  [switch]$SkipLogin
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $root

if (-not (Test-Path (Join-Path $root ".env"))) {
  Write-Error "Missing .env in the repository root. Copy .env.production.example to .env and fill every CHANGE_ME value."
}

if ($Tag) { $env:IMAGE_TAG = $Tag }
if ($Registry) { $env:IMAGE_REGISTRY = $Registry }
if (-not $env:IMAGE_TAG) { $env:IMAGE_TAG = "latest" }
if (-not $env:IMAGE_REGISTRY) { $env:IMAGE_REGISTRY = "ghcr.io/kimheang-code-it/stock_pos" }

$compose = @("-f", "docker-compose.yml", "-f", "docker-compose.prod.yml")

if (-not $SkipLogin) {
  Write-Host "Logging in to ghcr.io (GitHub username + PAT with read:packages)..." -ForegroundColor Cyan
  docker login ghcr.io
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "Pulling images from $env:IMAGE_REGISTRY (tag $env:IMAGE_TAG)..." -ForegroundColor Cyan
docker compose @compose pull
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Starting production stack..." -ForegroundColor Cyan
docker compose @compose up -d
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

docker compose @compose ps
Write-Host ""
Write-Host "Done. Frontend is on host port FRONTEND_PORT from .env (default 80)." -ForegroundColor Green
Write-Host "API is only reachable through nginx /api (not published on :8000)."
