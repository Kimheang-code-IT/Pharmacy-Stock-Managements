#Requires -Version 5.1
<#
.SYNOPSIS
  Let other devices (iPad, phone, laptop) on the same Wi-Fi/LAN open Stock & POS.

.DESCRIPTION
  Adds (or refreshes) an inbound Windows Firewall rule for the frontend port so
  the Docker-published port is reachable from the LAN, then prints the exact
  URLs to open from the other devices.

  Requires FRONTEND_BIND=0.0.0.0 (or the PC's LAN IP) in infrastructure\.env —
  see README.md, "LAN access". Restart the stack after changing it:
      scripts\stockpos\restart-system.bat

  Needs administrator rights (the script re-launches itself with a UAC prompt).

  Note: some Wi-Fi networks use "AP/client isolation" (common on guest networks
  and phone hotspots), which blocks device-to-device traffic no matter what.
  If a device still cannot connect, disable isolation or join the main network.
#>

$ErrorActionPreference = "Stop"

# Re-launch elevated when not already an administrator.
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
  [Security.Principal.WindowsBuiltInRole]::Administrator
)
if (-not $isAdmin) {
  Write-Host "Requesting administrator rights to add the firewall rule..." -ForegroundColor Yellow
  Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`""
  )
  exit 0
}

. (Join-Path $PSScriptRoot "stockpos-common.ps1")
$root = Get-DeployRoot
$port = Get-FrontendPort $root
$ruleName = "Stock POS (TCP $port)"

if (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue) {
  Write-Host "Firewall rule '$ruleName' already exists - refreshing." -ForegroundColor Cyan
  Remove-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
}

New-NetFirewallRule `
  -DisplayName $ruleName `
  -Direction Inbound `
  -Action Allow `
  -Protocol TCP `
  -LocalPort $port `
  -Profile Any `
  -Description "Stock & POS frontend (Docker published port $port) - LAN/Wi-Fi access" | Out-Null

Write-Host "Firewall rule '$ruleName' created (all profiles)." -ForegroundColor Green
Write-Host ""

# Real LAN IPv4 addresses, excluding loopback/link-local and virtual adapters
# (WSL/Hyper-V 172.16-31.x, VirtualBox host-only 192.168.56.x, ICS hotspot
# 192.168.137.x) so only addresses other devices can actually use are printed.
$ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object {
    $_.IPAddress -notmatch '^(127\.|169\.254\.|192\.168\.(56|137)\.|172\.(1[6-9]|2[0-9]|3[01])\.)' -and
    $_.InterfaceAlias -notmatch 'Loopback|vEthernet|WSL|Hyper-V|VirtualBox|VMware'
  } |
  Select-Object -ExpandProperty IPAddress -Unique

Write-Host "Open the app from your iPad / phone (connected to the same Wi-Fi):" -ForegroundColor Cyan
if ($ips) {
  foreach ($ip in $ips) {
    Write-Host ("  http://{0}:{1}/" -f $ip, $port)
  }
} else {
  Write-Host "  (No LAN IP detected - check that Wi-Fi or Ethernet is connected.)" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "If a device still cannot connect, the Wi-Fi router is likely using" -ForegroundColor Yellow
Write-Host "'AP/client isolation'. Disable it, or join a network without isolation." -ForegroundColor Yellow
