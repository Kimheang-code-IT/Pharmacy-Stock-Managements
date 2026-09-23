#Requires -Version 5.1
<#
.SYNOPSIS
  Create infrastructure\.env with strong random secrets for a local-only deploy.

.DESCRIPTION
  Copies .env.local.example and replaces every CHANGE_ME placeholder with a
  freshly generated secret, so the production boot checks pass without the user
  having to invent secrets. The generated administrator password is printed at
  the end — save it.

  Safe by default: refuses to overwrite an existing .env unless -Force is used.

.EXAMPLE
  .\infrastructure\scripts\init-env.ps1

.EXAMPLE
  .\infrastructure\scripts\init-env.ps1 -AdminEmail admin@shop.local -AdminPassword 'MyLongPassword123'
#>

param(
  [switch]$Force,
  [string]$AdminEmail = "admin@gmail.com",
  [string]$AdminPassword = "",
  [string]$TelegramBotToken = ""
)

$ErrorActionPreference = "Stop"

$infraDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$template = Join-Path $infraDir ".env.local.example"
$envPath = Join-Path $infraDir ".env"

if (-not (Test-Path $template)) {
  Write-Error "Missing template: $template"
}

if ((Test-Path $envPath) -and -not $Force) {
  Write-Host "A .env already exists at $envPath" -ForegroundColor Yellow
  Write-Host "Nothing changed. Use -Force to overwrite (this rotates all secrets)."
  exit 0
}

function New-Secret([int]$Bytes) {
  $buffer = New-Object byte[] $Bytes
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($buffer) } finally { $rng.Dispose() }
  return [Convert]::ToBase64String($buffer).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

$postgresPassword = New-Secret 24
$jwtSecret = New-Secret 48
$seedPassword = if ($AdminPassword) { $AdminPassword } else { New-Secret 16 }

$content = [System.IO.File]::ReadAllText($template)

$content = [regex]::Replace($content, "(?m)^POSTGRES_PASSWORD=.*$", "POSTGRES_PASSWORD=$postgresPassword")
$content = [regex]::Replace($content, "(?m)^JWT_SECRET_KEY=.*$", "JWT_SECRET_KEY=$jwtSecret")
$content = [regex]::Replace($content, "(?m)^TELEGRAM_BOT_TOKEN=.*$", "TELEGRAM_BOT_TOKEN=$TelegramBotToken")
$content = [regex]::Replace($content, "(?m)^SEED_ADMIN_EMAIL=.*$", "SEED_ADMIN_EMAIL=$AdminEmail")
$content = [regex]::Replace($content, "(?m)^SEED_ADMIN_PASSWORD=.*$", "SEED_ADMIN_PASSWORD=$seedPassword")

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($envPath, $content, $utf8NoBom)

Write-Host ""
Write-Host "Created $envPath with strong random secrets." -ForegroundColor Green
Write-Host ""
Write-Host "No data is seeded on startup. The first administrator is created on the" -ForegroundColor Cyan
Write-Host "Setup page the first time you open the app (http://localhost)." -ForegroundColor Cyan
Write-Host ""
Write-Host "Next: double-click 'Start Stock POS.bat' in the infrastructure folder,"
Write-Host "or run: .\infrastructure\scripts\stockpos\start-system.ps1"
Write-Host ""
Write-Host "To wipe all data later: .\infrastructure\scripts\clear-data.ps1" -ForegroundColor Cyan
exit 0
