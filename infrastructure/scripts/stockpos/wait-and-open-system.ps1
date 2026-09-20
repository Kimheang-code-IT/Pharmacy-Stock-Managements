#Requires -Version 5.1
<#
.SYNOPSIS
  Wait for Docker and the app health endpoint, then open the browser once.

.DESCRIPTION
  Used by the Windows Startup shortcut (see install-autostart.bat):
    1. start Docker Desktop when the engine is not up yet, then poll
       `docker info` until it answers (default 10 minutes)
    2. start the stack if it is not running (no rebuild)
    3. poll GET http://localhost:<port>/health/ready every 3 seconds
       until it reports ok (default 10 minutes)
    4. open http://localhost in the default browser — exactly once
  Health-based, not a fixed sleep. Skips the browser when an instance is
  already open (single-instance guard via a named mutex).
#>

param(
  [int]$DockerTimeoutMinutes = 10,
  [int]$AppTimeoutMinutes = 10
)

$ErrorActionPreference = "SilentlyContinue"
. (Join-Path $PSScriptRoot "stockpos-common.ps1")

$root = Get-DeployRoot
$url = "http://localhost:$(Get-FrontendPort $root)"

# Single-instance guard: a second run (e.g. autostart + manual) exits quietly.
$opened = $false
$mutex = [System.Threading.Mutex]::new($false, "Global\StockPosWaitAndOpen")
try {
  $ownsMutex = $false
  try { $ownsMutex = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $ownsMutex = $true }
  if (-not $ownsMutex) { exit 0 }
} catch {
  # Mutex creation failed (e.g. restricted session) — proceed without the guard.
}

try {
  # 1. Wait for Docker. If the engine is not up yet, start Docker Desktop
  #    ourselves so sign-in is fully unattended (works even when the in-app
  #    "Start Docker Desktop when you sign in" toggle is off).
  if (-not (Assert-Docker -Quiet)) {
    Start-DockerDesktop -Quiet | Out-Null
  }
  $deadline = (Get-Date).AddMinutes($DockerTimeoutMinutes)
  while ((Get-Date) -lt $deadline) {
    if (Assert-Docker -Quiet) { break }
    Start-Sleep -Seconds 5
  }
  if (-not (Assert-Docker -Quiet)) {
    Write-Host "Docker did not become ready within $DockerTimeoutMinutes minutes; not opening the app."
    exit 1
  }

  # 2. Make sure the stack is running (no rebuild; keeps volumes).
  if (-not (Test-ComposeStack $root)) {
    Write-Host "Deployment folder $root is not complete; cannot auto-start the app."
    exit 1
  }
  Set-Location $root
  docker compose (Get-ComposeArgs) up -d | Out-Null

  # 3. Wait for the health endpoint (postgres + redis + api all checked).
  $deadline = (Get-Date).AddMinutes($AppTimeoutMinutes)
  $healthy = $false
  while ((Get-Date) -lt $deadline) {
    if (Test-AppHealthy $root) { $healthy = $true; break }
    Start-Sleep -Seconds 3
  }

  # 4. Open the browser once, when healthy.
  if ($healthy) {
    Start-Process $url
    $opened = $true
    Write-Host "Stock & POS is ready: $url"
    exit 0
  }

  Write-Host "Stock & POS did not become healthy within $AppTimeoutMinutes minutes."
  # Open once anyway so the user sees the app's own error page instead of nothing.
  if (-not $opened) { Start-Process $url }
  exit 1
}
finally {
  if ($opened) {
    # Only the owner releases; ReleaseMutex throws when we never owned it.
    try { $mutex.ReleaseMutex() | Out-Null } catch { }
  }
  $mutex.Dispose()
}