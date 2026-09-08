#!/usr/bin/env sh
set -eu
cd "$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)"
docker compose up -d --build
FRONTEND_PORT="${FRONTEND_PORT:-80}"
API_HOST_PORT="${API_HOST_PORT:-8100}"
printf '\nStock & POS is starting (lean Docker stack: db, redis, api, frontend).\n'
printf '  Frontend (nginx): http://localhost:%s\n' "$FRONTEND_PORT"
printf '  API docs:         http://localhost:%s/docs\n\n' "$API_HOST_PORT"
printf 'Check status: docker compose ps\n'
printf 'View logs:    docker compose logs -f frontend api\n'
