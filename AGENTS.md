# Stock & POS Management System agent instructions

These instructions apply to every file in this repository.

## Canonical product source

- `docs/stock_pos_ai_agent_project_spec.md` is the single source of truth for product scope, business rules, data design, UI behavior, deployment, and definition of done.
- Read only the sections relevant to the current task before editing.
- Use `docs/PAGE_ROUTE_MAP.md` for the exact frontend page allowlist and API ownership map.
- Use `docs/IMPLEMENTATION_PLAN.md` to sequence the replacement of the legacy motorcycle-rental application.
- Use `docs/DOCKER_INFRASTRUCTURE.md` for the lean Compose stack (API + db + redis + frontend). Images are local disk. RabbitMQ, Celery beat, and a Docker scheduler are off by default.
- Use `docs/DO_NOT_USE.md` as the hard exclusion filter (legacy domain, forbidden pages, out-of-scope features).
- If code, tests, migrations, environment files, or deployment configuration conflict with the specification, migrate them toward the Stock & POS specification. Do not preserve a legacy contract merely because it exists. Do not keep `docs/prompts/` as a source of truth.
- Do not add a page, module, table, workflow, infrastructure service, or major dependency outside the specification without explicit user approval.

## Repository migration state

- `frontend/` and `backend/` currently contain legacy HollyWing motorcycle-rental code. It is migration input, not product truth.
- The target product is only the Stock & POS Management System. Do not expose or extend rentals, motorcycles, rental charges, rental pricing, rental reports, fleet status, or rental Telegram workflows.
- Replace legacy domain code and tests as the corresponding Stock & POS vertical slice is implemented. Do not retain dead compatibility layers or mixed-domain navigation.
- Reuse generic, verified infrastructure when it fits the new specification: Nuxt UI primitives, table/form patterns, authentication security utilities, PostgreSQL/Redis setup, logging, pagination, Docker, and CI.
- Do not mechanically rename rental entities into stock entities. Implement the stock, sales, debt, sequence, and audit rules from the specification.
- Preserve unrelated user edits. Before deleting or replacing a file, confirm that it belongs to the legacy domain or is superseded by the target architecture.

## Target architecture

- `frontend/`: Nuxt 4/current stable Nuxt, Vue 3, strict TypeScript, Nuxt UI, ECharts, and Pinia only for genuinely shared client state.
- `backend/`: Python 3.12+, FastAPI, SQLAlchemy 2, Pydantic 2, Alembic, PostgreSQL, Redis, optional Telegram HTTP client. Local disk for images. Celery/RabbitMQ are off by default.
- Build a modular monolith. Do not introduce microservices.
- Use `/api/v1` for the new Stock & POS API. Do not add new Stock & POS endpoints under the legacy `/api/v2` rental surface.
- PostgreSQL is authoritative for stock, sales, payments, debts, sequences, settings, and audit data.
- Redis is limited to reset-code state, rate limits, short-lived cache, revocation/session state, and other transient data.
- Store product/shop/brand images on local disk (`LOCAL_STORAGE_DIR`). Do not use S3 or MinIO. Do not store invoice PDFs or report exports.
- Daily expiry-alert scans run **inside the FastAPI process**. Do not add a Docker scheduler or Celery beat container.
- Telegram bot secrets stay server-side. Password-reset send and expiry alerts run in the API process. View-only inquiry may use an optional `telegram-bot` profile. Never send invoices or payment text.
- Use `NUMERIC`/Python `Decimal` for money and quantities as defined in the specification; never persist binary floating-point calculations.
- Store timestamps in UTC and format them with the configured application timezone.

## Approved frontend surface

The sidebar contains only:

- Dashboard
- Stock
- POS
- Delivery Notes
- Setup: Categories, Units of Measure (UOM), Brands, Suppliers, Customers
- Reports: Sales, Purchase, Customer Debt, Supplier Debt, Finance
- Administration: Users, Roles & Permissions, Document Sequence, Audit Log, Settings

Authentication pages are outside the sidebar: Initial Setup, Login, Forgot Password, Verify Reset Code, and Reset Password. Verify Reset Code may be a step within Forgot Password rather than a separate route.

Do not create separate pages or sidebar entries for sales, purchases, returns, customer debts, supplier debts, stock in, stock adjustment, stock damage, stock expiry, or expenses. Implement those as actions, tabs, drawers, modals, detail sections, or approved reports as specified in `docs/PAGE_ROUTE_MAP.md`. Finance Report (`/reports/finance`) uses an income/expense table (no chart) with Add Expense modal; do not add `/expenses`. Delivery Notes is an approved sidebar page for tracking delivery of sold products (it does not replace POS and does not stock-out again). Categories, UOM, Brands, Suppliers, and Customers are Setup sub-pages under `/setup/*`, not top-level sidebar items.

## Frontend rules

- Replace the legacy frontend experience with the approved Stock & POS pages; no rental or motorcycle route may remain user-accessible when its replacement slice is complete.
- Prefer Nuxt UI components and existing generic components that match the required compact ERPNext-inspired design.
- Keep the interface desktop-first, information-dense, responsive for laptop/tablet, and usable for POS barcode workflows.
- Use the shared sticky top header (`AppHeader` / `useAppHeader` / `AppHeaderPageActions`) for title, breadcrumbs, and page actions — not a separate in-page title + description block. Keep compact-table, server-side search/filter, pagination, loading, empty, error, and permission-denied patterns consistent.
- UI permission checks improve UX; backend permission checks provide security.
- Search for existing generic types, components, utilities, repositories, and tests before adding parallel abstractions.
- Keep user-facing strings centralized. Do not invent additional language requirements beyond configured system-language support.

## Backend rules

- Keep route handlers thin. Put transactions and business rules in application/services and database access in repositories.
- Implement one canonical stock mutation service used by stock in, adjustment, damage, expiry, POS sale, and sale return.
- Every stock mutation creates an immutable movement record. Never edit `current_stock` directly from a generic CRUD endpoint.
- Lock affected stock/batch and document-sequence rows during transactions. Prevent overselling unless `allow_negative_stock` is enabled.
- POS completion must atomically create the sale, items, payment or customer debt, stock movements, sequence number, and required audit entry.
- Debt payments are immutable transactions, reject overpayment, and atomically update remaining amount and status.
- Document sequence generation must be transaction-safe and collision-free.
- Enforce permissions server-side for every protected operation and guard against IDOR.
- Initial administrator setup is allowed once only. Password-reset codes must be hashed, short-lived, single-use, attempt-limited, rate-limited, and delivered only through the configured Telegram flow.
- Telegram bot secrets stay server-side and come from environment/secrets.
- Expiry alerts use two Settings lead times (e.g. 90 days and 7 days) and run from the in-process API scheduler. Telegram inquiry is view-only. Do not send invoice or payment text via Telegram. POS invoices are browser/OS print of HTML only.
- Every schema change requires an Alembic migration. Do not edit a production database manually.

## Testing and verification

- Replace legacy tests with tests for the new behavior as each slice is replaced. Do not weaken or delete a meaningful generic security/contract test without a Stock & POS equivalent.
- Cover specification section 9.4, especially transaction rollback, oversell prevention, debt payments, permissions, reset-code abuse, and concurrent sequences.
- Prefer focused checks while iterating, then run the relevant full checks from the repository root.

```text
pnpm --dir frontend test
pnpm --dir frontend typecheck
pnpm --dir frontend lint
pnpm --dir frontend build
python -m pytest backend/tests
docker compose config --quiet
```

Never report a check as passing unless it was run successfully. If verification is blocked, report the exact command and reason.
