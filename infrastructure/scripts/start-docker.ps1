# Start the full Stock & POS stack in Docker (build + detach).
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $Root
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$FrontendPort = if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { '80' }
$ApiPort = if ($env:API_HOST_PORT) { $env:API_HOST_PORT } else { '8100' }
Write-Host ""
Write-Host "Stock & POS is starting (lean Docker stack: db, redis, api, frontend)."
Write-Host "  Frontend (nginx): http://localhost:$FrontendPort"
Write-Host "  API docs:         http://localhost:$ApiPort/docs"
Write-Host ""
Write-Host "Check status: docker compose ps"
Write-Host "View logs:    docker compose logs -f frontend api"
