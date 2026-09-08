# Infrastructure

Deployment and host-level ops files for the Stock & POS Management System.

## Layout

```text
infrastructure/
├── nginx/      # Host reverse-proxy configs (Nginx / Caddy examples)
├── scripts/    # Install, start, and production deploy helpers
└── README.md
```

## Compose services (approved)

Root `docker compose up` runs the **lean** stack:

| Service | Purpose |
|---|---|
| `frontend` / `api` | Nuxt UI + FastAPI (**API also runs the expiry scheduler**) |
| `db` / `redis` | Authoritative data + transient state |

MinIO, RabbitMQ, Celery workers, `telegram-bot`, and a scheduler container are **not** started. Product images use a local volume on `api`. See `docs/DOCKER_INFRASTRUCTURE.md`.

Details: `docs/DOCKER_INFRASTRUCTURE.md`.

## What stays at the repository root

Per the product spec, these remain at the project root so Compose and CI keep simple paths:

- `docker-compose.yml`
- `docker-compose.prod.yml`
- `.env.example`
- `.env.production.example`

## What stays with each service

Service image configs stay next to their build context:

- `frontend/Dockerfile`, `frontend/nginx.conf` — Nuxt static site + `/api` proxy inside the frontend container
- `backend/Dockerfile`, `backend/Dockerfile.telegram` — API and Telegram bot images

Put **host** reverse-proxy configs under `infrastructure/nginx/`, not inside `frontend/`.

## Common commands

From the repository root:

```bash
# Local lean stack (db, redis, api, frontend — no MinIO, no scheduler container)
./infrastructure/scripts/start-docker.sh
# or
.\infrastructure\scripts\start-docker.ps1

# Production pull from registry
./infrastructure/scripts/deploy-from-registry.sh
# or
.\infrastructure\scripts\deploy-from-registry.ps1
```

Thin wrappers under `scripts/` forward to these paths for older docs and bookmarks.
