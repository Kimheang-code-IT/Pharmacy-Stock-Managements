#Requires -Version 5.1
<#
.SYNOPSIS
  Clone the repository from GitHub and build it on this computer (no GHCR image pull).

.EXAMPLE
  # After cloning:
  .\infrastructure\scripts\install-client.ps1
#>

param(
  [string]$RepoUrl = "https://github.com/Kimheang-code-IT/stock_pos.git",
  [string]$InstallDir = "",
  [switch]$SkipGitPull
)

$ErrorActionPreference = "Stop"

function Assert-Command($Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    Write-Error "$Name is not installed. Install Git and Docker Desktop, then run this script again."
  }
}

Assert-Command git
Assert-Command docker

$repoRootCandidate = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$inRepo = Test-Path (Join-Path $repoRootCandidate "docker-compose.yml")
if ($InstallDir) {
  $root = $InstallDir
} elseif ($inRepo) {
  $root = $repoRootCandidate
} else {
  $root = Join-Path $HOME "stock_pos"
}

if (-not (Test-Path (Join-Path $root "docker-compose.yml"))) {
  Write-Host "Cloning $RepoUrl -> $root" -ForegroundColor Cyan
  git clone $RepoUrl $root
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} elseif (-not $SkipGitPull) {
  Write-Host "Updating $root" -ForegroundColor Cyan
  git -C $root pull --ff-only
}

Set-Location $root

if (-not (Test-Path (Join-Path $root ".env"))) {
  Copy-Item (Join-Path $root ".env.example") (Join-Path $root ".env")
  Write-Host "Created .env from .env.example. Edit TELEGRAM_BOT_TOKEN if you need Telegram." -ForegroundColor Yellow
}

$env:IMAGE_TAG = "local"
$env:PULL_POLICY = "build"

Write-Host "Building and starting from source (no app image pull)..." -ForegroundColor Cyan
docker compose -f docker-compose.yml up -d --build --pull missing
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$frontendPort = "80"
Get-Content (Join-Path $root ".env") | ForEach-Object {
  if ($_ -match '^\s*FRONTEND_PORT\s*=\s*(.+)\s*$') { $frontendPort = $Matches[1].Trim() }
}

docker compose -f docker-compose.yml ps
Write-Host ""
Write-Host "Stock & POS is starting on this computer." -ForegroundColor Green
Write-Host "  App:  http://localhost:$frontendPort"
Write-Host "  API:  http://localhost:8000/docs"
Write-Host "  Login: admin@gmail.com / 123456  (from .env SEED_ADMIN_*)"
Write-Host ""
Write-Host "Logs: docker compose logs -f frontend api"
