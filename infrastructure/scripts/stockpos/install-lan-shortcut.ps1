#Requires -Version 5.1
<#
.SYNOPSIS
  Create "Yoeun Sokhon Pharmacy (LAN)" shortcuts that open the server's LAN URL.

.DESCRIPTION
  - Desktop + Start Menu shortcuts, plus the global hotkey Ctrl+Alt+L.
  - The URL is resolved now (parameter -Url, then LAN_BASE_URL / FRONTEND_BASE_URL
    in .env, then the detected LAN IPv4) and embedded in the shortcut, so the
    shortcut also works on a client device where the repo/.env does not exist.
  - On the server, FRONTEND_BIND must be 0.0.0.0 (or a LAN IP) and the firewall
    rule must exist; run scripts\allow-lan-access.ps1 once.

  Example:
    scripts\stockpos\install-lan-shortcut.bat -Url "http://192.168.1.50" -Hotkey "CTRL+ALT+L"
#>

param(
  [string]$Url = "",
  [string]$Hotkey = "CTRL+ALT+L"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "stockpos-common.ps1")

$target = Get-LanBaseUrl -Url $Url
if (-not $target) {
  Write-Host "Could not determine the LAN URL." -ForegroundColor Yellow
  Write-Host "Set FRONTEND_BIND=0.0.0.0 in infrastructure\.env, or pass -Url explicitly."
  exit 1
}

$created = New-StockPosLanShortcuts -Hotkey $Hotkey -Url $target

Write-Host ""
Write-Host "LAN shortcuts created:" -ForegroundColor Green
Write-Host "  URL        : $target"
Write-Host "  Desktop    : $($created.Desktop)"
Write-Host "  Start Menu : $($created.StartMenu)"
if ($created.Hotkey) {
  Write-Host ""
  Write-Host "Keyboard shortcut: press $($created.Hotkey) to open the system over the LAN." -ForegroundColor Green
}
Write-Host ""
Write-Host "On the server PC, make sure the app is exposed to the LAN:" -ForegroundColor Cyan
Write-Host "  1. FRONTEND_BIND=0.0.0.0 in infrastructure\.env (then restart-system.bat)"
Write-Host "  2. run scripts\allow-lan-access.ps1 once (adds the firewall rule)"
Write-Host ""
Write-Host "Copy the Desktop shortcut to other devices on the same Wi-Fi to open the app there."
exit 0
