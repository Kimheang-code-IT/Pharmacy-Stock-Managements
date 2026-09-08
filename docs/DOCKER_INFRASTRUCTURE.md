# Docker infrastructure — Stock & POS

This document describes the **lean** Docker Compose stack. Product rules remain in `docs/stock_pos_ai_agent_project_spec.md`. Page routes remain in `docs/PAGE_ROUTE_MAP.md`.

Goal: **few processes, low RAM/CPU, high request performance.** Do not start extra containers “just in case.”

## Default services (always on)

| Service | Role |
|---|---|
| `frontend` | Nuxt static UI behind container nginx; proxies `/api` to the API |
| `api` | FastAPI Stock & POS API (`/api/v1`). **Also runs the daily expiry-alert scheduler in-process.** |
| `db` | PostgreSQL — authoritative stock, sales, debts, sequences, settings, audit |
| `redis` | Reset codes, rate limits, short-lived cache (small memory footprint) |

Telegram password-reset **send** also runs in the API process (HTTP to Telegram). Invoices print in the browser only.

Local mock frontend (`NUXT_PUBLIC_USE_MOCK_DATA=true`) does **not** require this stack. Leanest live-API loop: `docker compose up -d db redis` and run uvicorn on the host.

## Do not start by default

These cost RAM/CPU and are **off** unless you pass a Compose profile later:

| Profile | Services | When |
|---|---|---|
| *(none — removed)* | Celery `scheduler` / beat | **Never.** Scheduler lives in the API process. |
| *(removed)* | `minio`, S3 | **Never.** Images are local disk on the API. |
| `queue` | `rabbitmq`, `worker-*` | Not needed now. No invoice PDFs, no MinIO exports, no Celery beat. |
| `telegram` | `telegram-bot` | Only if you want the **view-only inquiry** polling bot as a separate process. Reset codes and expiry alerts do not need this container. |

```bash
# Default lean stack
docker compose up -d --build

# Optional later (uses more RAM)
docker compose --profile object-store --profile queue --profile telegram up -d
```

## Architecture

```text
Internet
   |
Host Nginx / Caddy (optional) or frontend:80
   |
   +---- Frontend (Nuxt)  ---> browser/OS print for invoices and delivery notes
   |
   +---- Backend API (FastAPI)
            |  in-process: expiry-alert scheduler + Telegram reset-code send
            +---- PostgreSQL
            +---- Redis
```

## Scheduler (backend only)

- Implemented in `backend/app/core/scheduler.py`, started from the FastAPI lifespan.
- Sleeps until `EXPIRY_ALERT_SCAN_HOUR` (UTC), then runs `ExpiryAlertService.scan_and_send()`.
- Uses a short Redis lock so two API workers cannot double-send the same daily scan.
- `SCHEDULER_ENABLED=true` in Docker API; tests set it `false`.
- Do **not** add a Compose `scheduler` service or Celery beat container.

## Local image storage (no S3 / MinIO)

Product images, optional shop logo uploads, and brand logos are files on the API machine.

| Location | Path |
|---|---|
| Host / uvicorn | `LOCAL_STORAGE_DIR` (default `var/media`) |
| Docker API | `/srv/data/media` (volume `mediadata`) |

PostgreSQL stores object keys only. The UI uses `GET /api/v1/images/{object_key}` (auth required). Max 5 MB; jpeg/png/webp/gif. Never store invoice PDFs or CSV exports here.

The sidebar/login logo can stay the bundled file `frontend/app/assets/images/logo.png`.

Do **not** add MinIO, AWS S3, R2, or Google Drive.

## RabbitMQ / Celery — not used for now

Do not run RabbitMQ or Celery workers in the default stack. They do not make POS or stock faster; they add processes and RAM.

Forbidden even if a queue profile is turned on later:

- PDF invoice generation
- Storing report exports in MinIO
- Celery beat as a substitute for the in-process scheduler

## Telegram bot

Approved uses (spec §3.6):

1. Forgot-password verification codes (sent **from the API process**)
2. Two configurable product expiry alerts (scanned **by the API scheduler**)
3. View-only stock inquiry keyboards (optional `telegram-bot` profile)

Do **not** send payment or invoice text, and do **not** send invoice files.

```env
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=CHANGE_ME
TELEGRAM_BOT_MODE=polling
PASSWORD_RESET_CODE_EXPIRY_SECONDS=300
PASSWORD_RESET_MAX_ATTEMPTS=5
SCHEDULER_ENABLED=true
EXPIRY_ALERT_SCAN_HOUR=7
LOCAL_STORAGE_DIR=/srv/data/media
```

## Compose commands

```bash
docker compose up -d --build
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
```

## Production exposure rules

| Service | Public? |
|---|---|
| Frontend / reverse proxy | Yes (HTTPS) |
| API | Only via reverse proxy `/api` |
| PostgreSQL | No |
| Redis | No |
| RabbitMQ / telegram-bot | Not running in the default stack |

## Related docs

- Product rules: `docs/stock_pos_ai_agent_project_spec.md` §1.2.1, §3.5–3.8, §6
- Replacement sequence: `docs/IMPLEMENTATION_PLAN.md`
- Ops folder: `infrastructure/README.md`
