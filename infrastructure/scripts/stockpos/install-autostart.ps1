#Requires -Version 5.1
<#
.SYNOPSIS
  Add Stock & POS to the current user's Windows Startup folder (no admin needed)
  and make sure Docker Desktop also starts at sign-in.

.DESCRIPTION
  Creates wait-and-open-system.lnk in:
    %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
  The shortcut runs the wait-and-open script minimized. Windows runs Startup
  shortcuts at sign-in; Docker Desktop is enabled to start at sign-in too, the
  compose services restart automatically (restart: unless-stopped), the script
  waits for health, then the browser opens once.
#>

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "stockpos-common.ps1")

# 1. Desktop + Start Menu shortcuts with the global open hotkey.
$created = New-StockPosShortcuts -Hotkey "CTRL+ALT+S"

# 2. App auto-start at sign-in.
$startup = [Environment]::GetFolderPath("Startup")
$linkPath = Join-Path $startup "Stock and POS (wait and open).lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($linkPath)
$shortcut.TargetPath = "$env:SystemRoot\System32\cmd.exe"
$shortcut.Arguments = "/c `"$PSScriptRoot\wait-and-open-system.bat`" >> `"$env:TEMP\stockpos-autostart.log`" 2>&1"
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.WindowStyle = 7
$shortcut.Description = "Stock & POS: start containers, wait for health, open the app"
$shortcut.IconLocation = Join-Path $PSScriptRoot "stockpos.ico,0"
if (-not (Test-Path (Join-Path $PSScriptRoot "stockpos.ico"))) {
  # No .ico shipped — fall back to a stock icon; never invent binary assets.
  $shortcut.IconLocation = "%SystemRoot%\System32\SHELL32.dll,13"
}
$shortcut.Save()

# 3. Docker Desktop auto-start at sign-in.
Enable-DockerAutostart | Out-Null

Write-Host ""
Write-Host "Auto-start installed (current user only)." -ForegroundColor Green
Write-Host "Desktop shortcut : $($created.Desktop)"
Write-Host "Start Menu       : $($created.StartMenu)"
Write-Host "Startup shortcut : $linkPath"
if ($created.Hotkey) {
  Write-Host ""
  Write-Host "Open the system anytime with $($created.Hotkey)." -ForegroundColor Green
}
Write-Host ""
Write-Host "Docker Desktop starts at sign-in, the containers come back up, and the"
Write-Host "app opens automatically in the browser."
Write-Host ""
Write-Host "To undo, run remove-autostart.bat (or delete the shortcuts above)."
exit 0