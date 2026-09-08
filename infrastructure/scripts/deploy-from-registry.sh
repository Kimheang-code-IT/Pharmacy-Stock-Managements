#!/usr/bin/env bash
# Pull Stock & POS images from GitHub Container Registry and start production.
set -euo pipefail
root="$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)"
cd "$root"

if [[ ! -f .env ]]; then
  echo "Missing .env in the repository root. Copy .env.production.example to .env and fill every CHANGE_ME value." >&2
  exit 1
fi

export IMAGE_TAG="${IMAGE_TAG:-latest}"
export IMAGE_REGISTRY="${IMAGE_REGISTRY:-ghcr.io/kimheang-code-it/stock_pos}"

compose=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

if [[ "${SKIP_LOGIN:-}" != "1" ]]; then
  echo "Logging in to ghcr.io (GitHub username + PAT with read:packages)..."
  docker login ghcr.io
fi

echo "Pulling images from ${IMAGE_REGISTRY} (tag ${IMAGE_TAG})..."
"${compose[@]}" pull
echo "Starting production stack..."
"${compose[@]}" up -d
"${compose[@]}" ps
echo
echo "Done. Frontend is on port \$FRONTEND_PORT (default 80)."
echo "API is only reachable through nginx /api (not published on :8000)."
