#Requires -Version 5.1
<#
.SYNOPSIS
  Remove the current-user Startup shortcuts created by install-autostart.ps1.

.DESCRIPTION
  Removes the Stock & POS app shortcut and the Docker Desktop shortcut added by
  this toolkit. Docker Desktop's own startup entry (created by its settings
  toggle) is left untouched.
#>

$ErrorActionPreference = "Stop"
$startup = [Environment]::GetFolderPath("Startup")
$linkPaths = @(
  (Join-Path $startup "Stock and POS (wait and open).lnk"),
  (Join-Path $startup "Stock and POS (Docker Desktop).lnk")
)

$removed = 0
foreach ($linkPath in $linkPaths) {
  if (Test-Path -LiteralPath $linkPath) {
    Remove-Item -LiteralPath $linkPath -Force
    Write-Host "Removed: $linkPath"
    $removed++
  }
}

if ($removed -gt 0) {
  Write-Host "Auto-start removed (current user only)." -ForegroundColor Green
} else {
  Write-Host "No auto-start shortcuts found - nothing to remove."
}
exit 0