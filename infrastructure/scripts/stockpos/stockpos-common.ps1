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

function Test-AppHealthy($Root) {
  try {
    $response = Invoke-WebRequest -Uri (Get-ApiHealthUrl $Root) -UseBasicParsing -TimeoutSec 4
    $ok = $response.Content -match '"status"\s*:\s*"ok"'
    if ($ok) { return $true }
  } catch { }
  return $false
}

# Create the Desktop + Start Menu shortcuts that open the app, and assign the
# global keyboard hotkey to the Desktop one (Windows registers hotkeys for
# Desktop/Start Menu shortcuts). Returns the created paths and hotkey.
function New-StockPosShortcuts {
  param([string]$Hotkey = "CTRL+ALT+S")

  $shell = New-Object -ComObject WScript.Shell
  $icon = Join-Path $PSScriptRoot "stockpos.ico"
  $iconLocation = if (Test-Path -LiteralPath $icon) { "$icon,0" } else { "%SystemRoot%\System32\SHELL32.dll,13" }
  $target = "$env:SystemRoot\System32\cmd.exe"
  $arguments = "/c `"$PSScriptRoot\open-system.bat`""

  $desktopLink = Join-Path ([Environment]::GetFolderPath("Desktop")) "Yoeun Sokhon Pharmacy.lnk"
  $desktopShortcut = $shell.CreateShortcut($desktopLink)
  $desktopShortcut.TargetPath = $target
  $desktopShortcut.Arguments = $arguments
  $desktopShortcut.WorkingDirectory = $PSScriptRoot
  $desktopShortcut.Description = "Open the Yoeun Sokhon Pharmacy stock & POS system"
  $desktopShortcut.IconLocation = $iconLocation
  $hotkeyValue = $Hotkey.Trim().ToUpper()
  if ($hotkeyValue) { $desktopShortcut.Hotkey = $hotkeyValue }
  $desktopShortcut.Save()

  $startMenuLink = Join-Path ([Environment]::GetFolderPath("Programs")) "Yoeun Sokhon Pharmacy.lnk"
  $startMenuShortcut = $shell.CreateShortcut($startMenuLink)
  $startMenuShortcut.TargetPath = $target
  $startMenuShortcut.Arguments = $arguments
  $startMenuShortcut.WorkingDirectory = $PSScriptRoot
  $startMenuShortcut.Description = "Open the Yoeun Sokhon Pharmacy stock & POS system"
  $startMenuShortcut.IconLocation = $iconLocation
  $startMenuShortcut.Save()

  return [pscustomobject]@{
    Desktop   = $desktopLink
    StartMenu = $startMenuLink
    Hotkey    = $hotkeyValue
  }
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