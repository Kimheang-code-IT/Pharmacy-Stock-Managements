# Stock & POS Backend

FastAPI + PostgreSQL + Redis modular monolith for the Stock & POS Management System.
API surface is `/api/v1`.

## Layout

```text
backend/
├── app/
│   ├── main.py
│   ├── core/           # config, security, database, redis, exceptions
│   ├── modules/        # auth, dashboard, categories, stock, suppliers,
│   │                   # pos, customers, reports, administration, image
│   ├── shared/         # audit, documents, telegram, pagination
│   └── api/v1/         # versioned route registration
├── tests/
├── alembic/
└── requirements.txt
```

Each business area lives under `app/modules/<name>/`. Shared cross-cutting helpers
live under `app/shared/`. Routers are registered from `app/api/v1/router.py`.

## API surface (Stock & POS only)

All business endpoints live under `/api/v1` — there is no other API version.

| Family | Endpoints |
|---|---|
| Auth | `/api/v1/auth/*` (setup, login, refresh, me, logout, Telegram password reset) |
| Dashboard | `/api/v1/dashboard/summary` |
| Master data | `/api/v1/categories`, `/uoms`, `/brands`, `/products`, `/suppliers`, `/customers` |
| Stock | `/api/v1/stock/*` (in/adjust/damage/expire, movements, product history) |
| POS | `/api/v1/pos/*` (search, barcode, sales, returns, JSON receipt for HTML print — no invoice PDF) |
| Debts | `/customers/{id}/debts/*`, `/suppliers/{id}/debts/*` (immutable payments) |
| Delivery notes | `/api/v1/delivery-notes/*` |
| Reports | `/api/v1/reports/*` (sales, purchase, customer-debts, supplier-debts, finance + CSV exports) |
| Administration | `/api/v1/admin/*` (users, roles, permissions, sequences, audit, settings) |
| Images | `/api/v1/images/*` (local-disk uploads) |

### Response envelope

Success responses use `{ "data": ..., "meta": { ... } }` (list endpoints return
`meta.page`, `meta.limit`, `meta.total`). Errors use
`{ "detail": { "code", "message", "field_errors?" } }` with meaningful HTTP
status codes (401/403/404/409/422/429).

### How the frontend will consume this API

The Nuxt app is wired exclusively through the `NUXT_PUBLIC_API_BASE` build
variable (see root `docker-compose.yml`); no frontend code exists yet by design.
The contract:

- **Base URL** — all calls are `{NUXT_PUBLIC_API_BASE}/api/v1/...`. In Docker the
  default is `same-origin` and the host reverse proxy forwards `/api` to this
  service; in development the frontend can point directly at
  `http://localhost:8100/api/v1` (compose publishes the API on
  `${API_HOST_PORT:-8100}`).
- **Auth** — `POST /api/v1/auth/login` returns JWT access + refresh tokens; send
  the access token as `Authorization: Bearer <token>` on every call. Refresh via
  `POST /api/v1/auth/refresh`. Every protected endpoint enforces the permission
  catalog server-side (spec section 2.1.8); UI checks are UX only.
- **Pagination / filters** — list endpoints accept `q`, `page`, `limit`,
  `status`, `startDate`, `endDate` query parameters and return `meta.total`.
- **Health probes** — `GET /health`, `/health/live`, `/health/ready` (outside the
  versioned API; used by the Compose healthchecks).

## Local run

```bash
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health: `GET /health`  
Image upload: `POST /api/v1/images/upload`  
Docs: http://localhost:8000/docs

## Tests

```bash
python -m pytest backend/tests
```

Focused image tests do not require Postgres/Redis when run alone if you import
the service directly; API health tests need the test database and Redis from
`tests/conftest.py`.
