#Requires -Version 5.1
<#
.SYNOPSIS
  Create a "Pharmacy" shortcut that opens the system over Wi-Fi (LAN) and copies
  its address so another device can open the system too.

.DESCRIPTION
  - Desktop + Start Menu shortcut named "Pharmacy", plus the global hotkey
    Ctrl+Alt+P (change it with -Hotkey, e.g. -Hotkey "CTRL+ALT+P").
  - Clicking it resolves this PC's Wi-Fi/LAN address, opens it in the browser and
    copies it to the clipboard, ready to paste into a message for a phone, iPad
    or laptop on the same Wi-Fi.
  - The URL is resolved now (parameter -Url, then LAN_BASE_URL / FRONTEND_BASE_URL
    in .env, then the detected LAN IPv4) and embedded in the shortcut.
  - On the server, FRONTEND_BIND must be 0.0.0.0 (or a LAN IP) and the firewall
    rule must exist; run scripts\allow-lan-access.ps1 once.

  Example:
    scripts\stockpos\install-pharmacy-shortcut.bat -Url "http://192.168.1.50" -Hotkey "CTRL+ALT+P"
#>

param(
  [string]$Url = "",
  [string]$Hotkey = "CTRL+ALT+P"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "stockpos-common.ps1")

$target = Get-LanBaseUrl -Url $Url
if (-not $target) {
  Write-Host "Could not determine the Wi-Fi/LAN URL for this system." -ForegroundColor Yellow
  Write-Host "Set FRONTEND_BIND=0.0.0.0 in infrastructure\.env, or pass -Url explicitly."
  exit 1
}

$created = New-PharmacyShortcuts -Hotkey $Hotkey -Url $target

Write-Host ""
Write-Host "Pharmacy shortcut created:" -ForegroundColor Green
Write-Host "  Name       : Pharmacy"
Write-Host "  URL        : $target"
Write-Host "  Desktop    : $($created.Desktop)"
Write-Host "  Start Menu : $($created.StartMenu)"
if ($created.Hotkey) {
  Write-Host ""
  Write-Host "Keyboard shortcut: press $($created.Hotkey) to open the system over Wi-Fi." -ForegroundColor Green
}
Write-Host ""
Write-Host "Clicking it opens the system and copies the address to the clipboard." -ForegroundColor Cyan
Write-Host "Paste that address on any phone/tablet/laptop on the same Wi-Fi." -ForegroundColor Cyan
Write-Host ""
exit 0
