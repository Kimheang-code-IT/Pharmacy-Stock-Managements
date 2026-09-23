#Requires -Version 5.1
<#
.SYNOPSIS
  Clone the repository from GitHub and build it on this computer (no GHCR image pull).

.DESCRIPTION
  Builds the local-only production stack (docker-compose.yml)
  from source, so no GitHub Container Registry account is required. Creates
  infrastructure\.env with strong random secrets when it is missing.

.EXAMPLE
  # After cloning:
  .\infrastructure\scripts\install-client.ps1
#>

param(
  [string]$RepoUrl = "https://github.com/Kimheang-code-IT/stock_pos.git",
  [string]$InstallDir = "",
  [switch]$SkipGitPull,
  # By default a failed pre-upgrade backup ABORTS the upgrade (never migrate a
  # database you could not snapshot). Pass -AllowBackupFailure to override.
  [switch]$AllowBackupFailure
)

$ErrorActionPreference = "Stop"

function Assert-Command($Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    Write-Error "$Name is not installed. Install Git and Docker Desktop, then run this script again."
  }
}

Assert-Command git
Assert-Command docker

# This script lives in infrastructure\scripts\ -> repo root is two levels up.
$inRepo = Test-Path (Join-Path $PSScriptRoot "..\..\backend")
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if ($InstallDir) {
  $root = $InstallDir
} elseif ($inRepo) {
  $root = $repoRoot
} else {
  $root = Join-Path $HOME "stock_pos"
}

if (-not (Test-Path (Join-Path $root "infrastructure\docker-compose.yml"))) {
  Write-Host "Cloning $RepoUrl -> $root" -ForegroundColor Cyan
  git clone $RepoUrl $root
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} elseif (-not $SkipGitPull) {
  Write-Host "Updating $root" -ForegroundColor Cyan
  git -C $root pull --ff-only
}

$infra = Join-Path $root "infrastructure"
Set-Location $infra

if (-not (Test-Path (Join-Path $infra ".env"))) {
  Write-Host "Creating infrastructure\.env with strong random secrets..." -ForegroundColor Cyan
  & (Join-Path $infra "scripts\init-env.ps1")
}

$env:IMAGE_TAG = "local"
$env:PULL_POLICY = "build"

# Pre-upgrade safety backup: if the stack is already running, snapshot the
# database before rebuilding. Best effort so a first-time install still works.
$runningServices = docker compose -f docker-compose.yml ps --status running --services 2>$null
if ($runningServices -contains "db") {
  Write-Host "Taking a pre-upgrade database backup..." -ForegroundColor Cyan
  try {
    & (Join-Path $infra "scripts\backup.ps1") -SkipMedia
  }
  catch {
    if (-not $AllowBackupFailure) {
      Write-Host ""
      Write-Host "ABORTING upgrade: the pre-upgrade backup failed." -ForegroundColor Red
      Write-Host "  $($_.Exception.Message)" -ForegroundColor Red
      Write-Host "Fix the backup (see infrastructure\README.md section 4), then re-run." -ForegroundColor Red
      Write-Host "To upgrade anyway (not recommended): .\scripts\install-client.ps1 -AllowBackupFailure" -ForegroundColor Yellow
      exit 1
    }
    Write-Warning "Pre-upgrade backup failed: $($_.Exception.Message). Continuing because -AllowBackupFailure was set."
  }
}

Write-Host "Building and starting from source (no app image pull)..." -ForegroundColor Cyan
docker compose -f docker-compose.yml up -d --build --pull missing
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$frontendPort = "80"
Get-Content (Join-Path $infra ".env") | ForEach-Object {
  if ($_ -match '^\s*FRONTEND_PORT\s*=\s*(.+)\s*$') { $frontendPort = $Matches[1].Trim() }
}

docker compose -f docker-compose.yml ps
Write-Host ""
Write-Host "Stock & POS is starting on this computer." -ForegroundColor Green
Write-Host "  App:  http://localhost:$frontendPort"
Write-Host "  No data is seeded: create the first administrator on the Setup page."
Write-Host ""
Write-Host "Daily use: double-click 'Start Stock POS.bat' in the infrastructure folder."
Write-Host "Logs: docker compose logs -f frontend api"
