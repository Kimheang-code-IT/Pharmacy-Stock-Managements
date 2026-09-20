#Requires -Version 5.1
<#
.SYNOPSIS
  Create "Yoeun Sokhon Pharmacy" shortcuts that open the app, plus a global
  keyboard shortcut.

.DESCRIPTION
  - Desktop shortcut   : double-click to open http://localhost.
  - Start Menu shortcut : same shortcut, searchable from the Start menu.
  - Keyboard hotkey    : press Ctrl+Alt+S from anywhere to open the app
    (Windows registers the hotkey from the Desktop shortcut; change it with
    -Hotkey, e.g. -Hotkey "CTRL+ALT+P").

  Reuses stockpos.ico in this folder when present; never invents binary assets.
#>

param(
  [string]$Hotkey = "CTRL+ALT+S"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "stockpos-common.ps1")

$created = New-StockPosShortcuts -Hotkey $Hotkey

Write-Host ""
Write-Host "Shortcuts created:" -ForegroundColor Green
Write-Host "  Desktop    : $($created.Desktop)"
Write-Host "  Start Menu : $($created.StartMenu)"
if ($created.Hotkey) {
  Write-Host ""
  Write-Host "Keyboard shortcut: press $($created.Hotkey) to open the system." -ForegroundColor Green
  Write-Host "(You can also pin the Start Menu shortcut to the taskbar.)"
}
exit 0
