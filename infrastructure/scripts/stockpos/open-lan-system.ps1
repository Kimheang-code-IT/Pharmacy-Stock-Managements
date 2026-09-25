#Requires -Version 5.1
<#
.SYNOPSIS
  Open the app over the LAN (server's IP/hostname) in the default browser.

.DESCRIPTION
  Resolves the URL other devices use — the -Url parameter, then LAN_BASE_URL /
  FRONTEND_BASE_URL in infrastructure\.env, then the PC's detected LAN IPv4 +
  FRONTEND_PORT — waits until /health/ready reports ok, then opens the browser
  once. Works from a client device too: install-lan-shortcut.bat embeds the URL
  in the shortcut, so no .env or Docker is needed there.
#>

param(
  [string]$Url = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "stockpos-common.ps1")

$target = Get-LanBaseUrl -Url $Url
if (-not $target) {
  Write-Host "Could not determine the LAN URL for this system." -ForegroundColor Yellow
  Write-Host "Run install-lan-shortcut.bat -Url 'http://<server-ip>' (see infrastructure\README.md, 'LAN access')."
  exit 1
}

if (-not (Test-UrlHealthy $target)) {
  Write-Host "The system at $target is still starting up. The browser will open shortly..." -ForegroundColor Cyan
  $deadline = (Get-Date).AddSeconds(90)
  while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 3
    if (Test-UrlHealthy $target) { break }
  }
  if (-not (Test-UrlHealthy $target)) {
    Write-Host "The system did not become healthy within 90 seconds." -ForegroundColor Yellow
    Write-Host "On the server PC, run Start Stock POS.bat, or see infrastructure\README.md > Troubleshooting."
    # Still open so the user sees the browser's own connection error.
    Start-Process $target
    exit 1
  }
}

# Invoke-Item/$url opens exactly one default-browser window per call.
Start-Process $target
exit 0
