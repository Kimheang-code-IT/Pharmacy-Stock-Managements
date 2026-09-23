# AGENTS.md

Stock & POS management system ("Yoeun Sokhon Pharmacy"). Monorepo, no root README —
the primary setup/ops doc is `infrastructure/README.md`.

- `backend/` — FastAPI (Python 3.12), async SQLAlchemy 2 + asyncpg, PostgreSQL, Redis.
- `frontend/` — Nuxt 4 SPA (`ssr: false`, built with `nuxt generate`), pnpm.
- `infrastructure/` — the single Docker Compose stack, `.env` templates, Windows launchers.

## Commands

Backend (run from `backend/`; install `pip install -r requirements-dev.txt`):

```powershell
docker compose -f ../infrastructure/docker-compose.yml up -d db redis  # tests need PG:55432 + Redis:56379
python -m pytest tests -q                       # full suite
python -m pytest tests/modules/auth/test_login.py -q   # single file (or -k <name>)
ruff check app                                  # lint
```

Frontend (pnpm@10.30.3; run from `frontend/` or `pnpm --dir frontend ...`):

```powershell
pnpm install
pnpm prepare:nuxt        # generates .nuxt/ — required before typecheck/lint on a clean checkout
pnpm test                # vitest, node env, tests/**/*.spec.ts
pnpm typecheck           # nuxt typecheck
pnpm lint                # eslint (reads .nuxt/eslint.config.mjs, needs prepare:nuxt first)
pnpm build               # nuxt generate -> frontend/.output/public
```

Docker (run from `infrastructure/`, where `.env` lives): `docker compose up -d --build`.

## Non-obvious facts

- `backend/tests/conftest.py` derives `DATABASE_URL` from `infrastructure/.env` and appends
  `_test` to the DB name, then drops/recreates the schema and seeds. Don't export
  `DATABASE_URL` unless you need a different database.
- Alembic migrations are hand-sequenced `alembic/versions/0001…0029`. The `api` container
  runs `alembic upgrade head` on start (compose `command`), not the Dockerfile CMD.
- Despite `celery`/`celery_broker_url` in config, there is no Celery/RabbitMQ at runtime:
  scheduled jobs run in the API process (`SCHEDULER_ENABLED`); Telegram runs in-process plus
  a separate `telegram-bot` container.
- `app/core/config.py:assert_safe_for_production` refuses to boot with dev secrets when
  `ENVIRONMENT=production`; `/docs` is disabled in production.
- No seeded admin by default — the first admin is created on the SPA Setup page.
  `python -m app.seed` only creates one when `SEED_ADMIN_ENABLED=true`.
- Backend module pattern: `app/modules/<domain>/{router,service,repository,models,schemas}.py`;
  register routers in `app/api/v1/router.py` (prefix `/api/v1`). Shared code lives in `app/shared/`.
- `frontend` API base: `same-origin` in Docker/Vercel (nginx proxies `/api` to `api:8000`);
  local dev defaults to `auto` (page hostname :8000). Auth is bearer JWT only — no cookies/CSRF.
- i18n `en` + `km` must keep exact key parity; a test (`tests/i18n-locales.spec.ts`) enforces it.
  Add every string to both `frontend/i18n/locales/*.json`.
- Frontend repositories (`app/repositories/`) are HTTP-only; the mock repositories live only under
  `tests/support/` for unit tests.
- E2E is not in CI. It needs the running Docker stack and a real API: `pnpm e2e:install` then
  `E2E_BASE_URL=http://localhost:80 pnpm e2e`. Credentials default to `admin@gmail.com` / `123456`.
- No CI/CD pipeline is configured. Run the backend, frontend, and Compose checks locally
  with the commands above before committing or deploying.

## Repo conventions

- Single `main` branch; commits are short freeform messages (e.g. `update pos version 2.0`).
- Production safety: bind frontend/db/redis to loopback by default; never commit `infrastructure/.env`.
- `ruff` reads no config (there is no `pyproject.toml`), so it uses defaults; `ruff check app` passes.
