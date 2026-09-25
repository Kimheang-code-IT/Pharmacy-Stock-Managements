#Requires -Version 5.1
<#
.SYNOPSIS
  Shared helpers for the local-only Windows deployment of Stock & POS.

.DESCRIPTION
  Thin functions used by the double-clickable .bat wrappers in this folder:
  start / stop / restart / open / wait-and-open / autostart install/remove.
  Everything works without administrator rights; Docker Desktop must be
  installed for the current user.

  The Compose files and `.env` live in the `infrastructure/` folder next to the
  `scripts/` folder. Set STOCKPOS_DIR to that folder to override autodetection.
#>

$ErrorActionPreference = "Stop"

# Deployment folder: the `infrastructure/` folder that contains
# docker-compose.yml and `.env`.
# Autodetected from this script's location; override with STOCKPOS_DIR.
function Get-DeployRoot {
  if ($env:STOCKPOS_DIR) { return $env:STOCKPOS_DIR }
  if ($env:STOCKPOS_HOME) { return $env:STOCKPOS_HOME }
  # This file lives in infrastructure\scripts\stockpos\, so go up two levels.
  return (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

function Assert-Docker([switch]$Quiet) {
  $dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
  if (-not $dockerCmd) {
    if ($Quiet) { return $false }
    Write-Host ""
    Write-Host "Docker is not available yet." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "If Docker Desktop is installed, it is still starting up." -ForegroundColor Yellow
    Write-Host "Please wait a moment and try again, or double-click" -ForegroundColor Yellow
    Write-Host "wait-and-open-system.bat which waits for Docker automatically." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "If this message keeps appearing, start 'Docker Desktop' from" -ForegroundColor Yellow
    Write-Host "the Start menu and make sure it is set to start with Windows:" -ForegroundColor Yellow
    Write-Host "  Docker Desktop > Settings > General > 'Start Docker Desktop when you sign in'" -ForegroundColor Yellow
    Write-Host ""
    return $false
  }
  # The engine may still be starting even though docker.exe exists.
  docker info *> $null
  if ($LASTEXITCODE -ne 0) {
    if ($Quiet) { return $false }
    Write-Host ""
    Write-Host "Docker Desktop is still starting up. Please try again in a minute." -ForegroundColor Yellow
    Write-Host "(Or double-click wait-and-open-system.bat — it waits for you.)" -ForegroundColor Yellow
    Write-Host ""
    return $false
  }
  return $true
}

# Locate the Docker Desktop executable (per-machine or per-user install).
# Returns the full path, or $null when Docker Desktop is not installed.
function Get-DockerDesktopExe {
  $candidates = New-Object System.Collections.Generic.List[string]
  if ($env:ProgramFiles) { $candidates.Add((Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe")) }
  if (${env:ProgramFiles(x86)}) { $candidates.Add((Join-Path ${env:ProgramFiles(x86)} "Docker\Docker\Docker Desktop.exe")) }
  if ($env:LOCALAPPDATA) {
    $candidates.Add((Join-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe"))
    $candidates.Add((Join-Path $env:LOCALAPPDATA "Programs\Docker\Docker\Docker Desktop.exe"))
  }
  foreach ($path in $candidates) {
    if ($path -and (Test-Path -LiteralPath $path)) { return (Resolve-Path -LiteralPath $path).Path }
  }
  # Fall back to the uninstall registry (covers custom install locations).
  foreach ($root in @(
      "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Docker Desktop",
      "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Docker Desktop"
    )) {
    try {
      $props = Get-ItemProperty -Path $root -ErrorAction Stop
      foreach ($value in @($props.InstallLocation, $props.DisplayIcon)) {
        if (-not $value) { continue }
        $exe = ([string]$value).Trim().Trim('"')
        $cut = $exe.IndexOf(".exe", [System.StringComparison]::OrdinalIgnoreCase)
        if ($cut -ge 0) { $exe = $exe.Substring(0, $cut + 4) }
        if ($exe -and (Test-Path -LiteralPath $exe)) { return (Resolve-Path -LiteralPath $exe).Path }
      }
    } catch { }
  }
  return $null
}

# Launch Docker Desktop so the engine starts without the user finding the icon.
function Start-DockerDesktop([switch]$Quiet) {
  $exe = Get-DockerDesktopExe
  if (-not $exe) {
    if (-not $Quiet) {
      Write-Host "Docker Desktop was not found on this computer." -ForegroundColor Yellow
      Write-Host "Install it from https://www.docker.com/products/docker-desktop/ and run"
      Write-Host "install-autostart.bat again."
    }
    return $false
  }
  if (-not $Quiet) { Write-Host "Starting Docker Desktop..." -ForegroundColor Cyan }
  try {
    Start-Process -FilePath $exe -ArgumentList "-Autostart" -WindowStyle Minimized
    return $true
  } catch {
    if (-not $Quiet) { Write-Host "Could not start Docker Desktop: $($_.Exception.Message)" -ForegroundColor Red }
    return $false
  }
}

# Make Docker Desktop launch automatically at Windows sign-in (no admin needed).
# Docker Desktop normally writes its own Startup/Run entry when its in-app
# "Start Docker Desktop when you sign in" toggle is on; this adds the entry when
# it is missing so the whole system comes up unattended.
function Enable-DockerAutostart {
  $exe = Get-DockerDesktopExe
  if (-not $exe) {
    Write-Host "Docker Desktop is not installed - skipping Docker auto-start." -ForegroundColor Yellow
    Write-Host "After installing Docker Desktop, run install-autostart.bat again."
    return $false
  }

  $startup = [Environment]::GetFolderPath("Startup")
  $ownLink = Join-Path $startup "Stock and POS (Docker Desktop).lnk"
  $dockerLink = Join-Path $startup "Docker Desktop.lnk"
  $runValue = $null
  try {
    $runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
    $runValue = (Get-ItemProperty -Path $runKey -Name "Docker Desktop" -ErrorAction Stop)."Docker Desktop"
  } catch { }

  if ((Test-Path -LiteralPath $dockerLink) -or $runValue) {
    Write-Host "Docker Desktop already starts at sign-in." -ForegroundColor Green
    return $true
  }

  $shell = New-Object -ComObject WScript.Shell
  $shortcut = $shell.CreateShortcut($ownLink)
  $shortcut.TargetPath = $exe
  $shortcut.Arguments = "-Autostart"
  $shortcut.WorkingDirectory = Split-Path -Parent $exe
  $shortcut.WindowStyle = 7
  $shortcut.Description = "Start Docker Desktop at sign-in for Stock & POS"
  $icon = Join-Path $PSScriptRoot "stockpos.ico"
  $shortcut.IconLocation = if (Test-Path -LiteralPath $icon) { "$icon,0" } else { "%SystemRoot%\System32\SHELL32.dll,13" }
  $shortcut.Save()
  Write-Host "Docker Desktop will now start at sign-in." -ForegroundColor Green
  return $true
}

function Get-ComposeArgs {
  return @("-f", "docker-compose.yml")
}

function Test-ComposeStack($Root) {
  return (Test-Path (Join-Path $Root "docker-compose.yml")) -and
         (Test-Path (Join-Path $Root ".env"))
}

function Get-FrontendPort($Root) {
  $port = "80"
  $envFile = Join-Path $Root ".env"
  if (Test-Path $envFile) {
    foreach ($line in (Get-Content $envFile)) {
      if ($line -match '^\s*FRONTEND_PORT\s*=\s*(.+)\s*$') { $port = $Matches[1].Trim() }
    }
  }
  return $port
}

function Get-ApiHealthUrl($Root) {
  # Same-origin through the frontend nginx proxy (the API port is not published).
  return "http://localhost:$(Get-FrontendPort $Root)/health/ready"
}

# The PC's usable LAN IPv4 addresses, excluding loopback/link-local and virtual
# adapters (WSL/Hyper-V 172.16-31.x, VirtualBox host-only 192.168.56.x, ICS
# hotspot 192.168.137.x) so only addresses other devices can use remain.
function Get-LanIPv4Addresses {
  return @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
      $_.IPAddress -notmatch '^(127\.|169\.254\.|192\.168\.(56|137)\.|172\.(1[6-9]|2[0-9]|3[01])\.)' -and
      $_.InterfaceAlias -notmatch 'Loopback|vEthernet|WSL|Hyper-V|VirtualBox|VMware'
    } |
    Select-Object -ExpandProperty IPAddress -Unique)
}

# Resolve the URL other devices use to reach the app.
# Order: explicit -Url, then LAN_BASE_URL, then FRONTEND_BASE_URL (unless it is
# localhost), then the first detected LAN IPv4 + FRONTEND_PORT.
function Get-LanBaseUrl {
  param([string]$Url = "")

  if ($Url -and $Url.Trim()) { return $Url.Trim().TrimEnd('/') }

  $root = Get-DeployRoot
  $envFile = Join-Path $root ".env"
  if (Test-Path -LiteralPath $envFile) {
    $lanUrl = $null
    $frontendUrl = $null
    foreach ($line in (Get-Content -LiteralPath $envFile)) {
      if (-not $lanUrl -and $line -match '^\s*LAN_BASE_URL\s*=\s*(.+?)\s*$') { $lanUrl = $Matches[1].Trim() }
      if (-not $frontendUrl -and $line -match '^\s*FRONTEND_BASE_URL\s*=\s*(.+?)\s*$') { $frontendUrl = $Matches[1].Trim() }
    }
    if ($lanUrl) { return $lanUrl.TrimEnd('/') }
    if ($frontendUrl -and $frontendUrl -notmatch '//(localhost|127\.0\.0\.1)(:\d+)?$') {
      return $frontendUrl.TrimEnd('/')
    }
  }

  $ip = Get-LanIPv4Addresses | Select-Object -First 1
  if ($ip) { return "http://${ip}:$(Get-FrontendPort $root)" }
  return $null
}

# Poll any base URL's deep-health endpoint (localhost or a LAN target).
function Test-UrlHealthy {
  param([string]$BaseUrl)
  if (-not $BaseUrl) { return $false }
  try {
    $response = Invoke-WebRequest -Uri "$($BaseUrl.TrimEnd('/'))/health/ready" -UseBasicParsing -TimeoutSec 4
    return ($response.Content -match '"status"\s*:\s*"ok"')
  } catch { }
  return $false
}

function Test-AppHealthy($Root) {
  return Test-UrlHealthy (Get-ApiHealthUrl $Root)
}

# Icon used by every shortcut: the shipped .ico when present, else a stock icon.
function Get-StockPosIconLocation {
  $icon = Join-Path $PSScriptRoot "stockpos.ico"
  if (Test-Path -LiteralPath $icon) { return "$icon,0" }
  return "%SystemRoot%\System32\SHELL32.dll,13"
}

# Create the Desktop + Start Menu shortcuts that run a batch wrapper, and assign
# the global keyboard hotkey to the Desktop one (Windows registers hotkeys for
# Desktop/Start Menu shortcuts). Returns the created paths and hotkey.
function New-StockPosShortcutPair {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$ScriptPath,
    [string]$Description = "Open the Yoeun Sokhon Pharmacy stock & POS system",
    [string]$Hotkey = "",
    [string]$ScriptArguments = ""
  )

  $shell = New-Object -ComObject WScript.Shell
  $iconLocation = Get-StockPosIconLocation
  $target = "$env:SystemRoot\System32\cmd.exe"
  $arguments = "/c `"$ScriptPath`""
  if ($ScriptArguments.Trim()) { $arguments = "$arguments $($ScriptArguments.Trim())" }
  $hotkeyValue = $Hotkey.Trim().ToUpper()

  $desktopLink = Join-Path ([Environment]::GetFolderPath("Desktop")) "$Name.lnk"
  $desktopShortcut = $shell.CreateShortcut($desktopLink)
  $desktopShortcut.TargetPath = $target
  $desktopShortcut.Arguments = $arguments
  $desktopShortcut.WorkingDirectory = $PSScriptRoot
  $desktopShortcut.Description = $Description
  $desktopShortcut.IconLocation = $iconLocation
  if ($hotkeyValue) { $desktopShortcut.Hotkey = $hotkeyValue }
  $desktopShortcut.Save()

  $startMenuLink = Join-Path ([Environment]::GetFolderPath("Programs")) "$Name.lnk"
  $startMenuShortcut = $shell.CreateShortcut($startMenuLink)
  $startMenuShortcut.TargetPath = $target
  $startMenuShortcut.Arguments = $arguments
  $startMenuShortcut.WorkingDirectory = $PSScriptRoot
  $startMenuShortcut.Description = $Description
  $startMenuShortcut.IconLocation = $iconLocation
  $startMenuShortcut.Save()

  return [pscustomobject]@{
    Desktop   = $desktopLink
    StartMenu = $startMenuLink
    Hotkey    = $hotkeyValue
  }
}

# Localhost shortcuts (Ctrl+Alt+S) — the daily shortcut on the server PC.
function New-StockPosShortcuts {
  param([string]$Hotkey = "CTRL+ALT+S")

  return New-StockPosShortcutPair `
    -Name "Yoeun Sokhon Pharmacy" `
    -ScriptPath (Join-Path $PSScriptRoot "open-system.bat") `
    -Description "Open the Yoeun Sokhon Pharmacy stock & POS system" `
    -Hotkey $Hotkey
}

# LAN shortcuts (Ctrl+Alt+L) — open the server's LAN URL, for other devices.
function New-StockPosLanShortcuts {
  param(
    [string]$Hotkey = "CTRL+ALT+L",
    [string]$Url = ""
  )

  $extra = ""
  if ($Url -and $Url.Trim()) { $extra = "-Url `"$($Url.Trim())`"" }
  return New-StockPosShortcutPair `
    -Name "Yoeun Sokhon Pharmacy (LAN)" `
    -ScriptPath (Join-Path $PSScriptRoot "open-lan-system.bat") `
    -Description "Open the Yoeun Sokhon Pharmacy stock & POS system over the LAN" `
    -Hotkey $Hotkey `
    -ScriptArguments $extra
}

function Start-Stack {
  $root = Get-DeployRoot
  if (-not (Test-ComposeStack $root)) {
    Write-Host "Deployment folder $root is not complete." -ForegroundColor Red
    Write-Host "It must contain docker-compose.yml and .env"
    Write-Host "(run infrastructure\scripts\init-env.ps1 to create .env, then see"
    Write-Host " infrastructure\README.md for the first installation)."
    return 1
  }
  Set-Location $root
  if (-not (Assert-Docker)) { return 1 }
  Write-Host "Starting Stock & POS..." -ForegroundColor Cyan
  docker compose (Get-ComposeArgs) up -d 2>&1 | ForEach-Object { "$_" }
  if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker failed to start the stack. Check the message above." -ForegroundColor Red
    return $LASTEXITCODE
  }
  Write-Host "Containers are starting. The app opens automatically when healthy." -ForegroundColor Green
  Write-Host "App address: http://localhost:$(Get-FrontendPort $Root)"
  return 0
}