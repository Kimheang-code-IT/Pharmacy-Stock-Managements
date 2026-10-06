# Stock & POS — Pharmacy Stock Management

A stock, point-of-sale and administration platform for a pharmacy business. A modular
FastAPI backend runs behind a Nuxt frontend, with PostgreSQL and Redis, packaged for
one-click deployment on Windows with Docker Compose.

> The Compose stack is called **Stock & POS**. This repository holds the pharmacy
> deployment of that stack.

## Stack

| Area | Technology |
| --- | --- |
| API | FastAPI, Uvicorn, Pydantic v2, pydantic-settings |
| Data | PostgreSQL (asyncpg), SQLAlchemy 2, Alembic, Redis |
| Auth | JWT (PyJWT), Argon2 password hashing |
| Frontend | Nuxt, Vue 3, Nuxt UI, Tailwind CSS, Pinia |
| Tables / charts | TanStack Table, Apache ECharts |
| Integrations | Telegram bot, Google Sheets, OpenPyXL, FPDF2 |
| Infrastructure | Docker Compose, nginx, PowerShell / batch launchers |
| Tests | pytest, Vitest, Playwright |

## Repository layout

```text
backend/           FastAPI application (modular monolith)
frontend/          Nuxt application
infrastructure/    Compose files, .env templates, Windows launchers, nginx config
AGENTS.md          Agent/contributor guidance for this codebase
```

## Modules

Each business area lives under `backend/app/modules/<name>/`. Shared cross-cutting
helpers live under `backend/app/shared/`, and routers are registered from
`backend/app/api/v1/`.

`administration`, `auth`, `backup`, `brands`, `categories`, `customers`,
`dashboard`, `image`, `pos`, `products`, `reports`, `stock`, `suppliers`,
`uoms`

## Running it

The quickest path on Windows is the launcher scripts in `infrastructure/`:

| Script | Purpose |
| --- | --- |
| `First Time Setup.bat` | Creates `.env`, builds images, starts the stack, prints the admin credentials |
| `Start Stock POS.bat` | Starts the stack for daily use |
| `Stop Stock POS.bat` | Stops the stack |

In local-only mode the app binds to `127.0.0.1:80`. PostgreSQL, Redis and the API
are **not** published to the host — they stay on the internal Docker network.
`infrastructure/nginx/stock-pos.conf` is a ready-made HTTPS reverse-proxy example
for production.

See `infrastructure/README.md` for the full deployment guide.

## Development

```bash
# API
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload

# Frontend
cd ../frontend
pnpm install
pnpm dev
```

## Tests

```bash
cd backend && python -m pytest -q     # API
cd frontend && pnpm test              # unit tests
cd frontend && pnpm e2e               # Playwright end-to-end
```
