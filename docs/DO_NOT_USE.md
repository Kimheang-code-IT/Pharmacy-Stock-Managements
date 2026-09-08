# DO NOT USE — Stock & POS filter

Use this as a hard filter for agents and prompts. Anything listed here is **out of scope** for the finished Stock & POS product unless the user explicitly approves it later.

Canonical allowlists: `docs/PAGE_ROUTE_MAP.md`, `docs/stock_pos_ai_agent_project_spec.md`. Do not add `docs/prompts/` — all agent rules live in those five docs plus `AGENTS.md`.

## 1. Legacy domain — do not keep or expose

Do not build, extend, or leave user-facing:

- HollyWing branding as product identity (shop brand is **Yoeun Sokhon Pharmacy**)
- Rentals / rental agreements
- Motorcycles / fleet / maintenance
- Rental charges / rental pricing
- Rental reports / income-expense rental flows
- Rental Telegram workflows (Stock & POS Telegram is allowed only for password-reset, expiry alerts, and view-only inquiry — see spec §3.6)
- Legacy API surface `/api/v2` for new Stock & POS features

Ignore or replace rental modules/pages such as:

- `/rentals`, `/motorcycles`, `/rental-reports`, `/income-expense`
- frontend `rental/` components, `rental-modules`, rental repositories/types
- backend rental models/routes/tests named for motorcycles/rentals/charges

Reusable generics are OK (Nuxt UI, tables, auth helpers, Docker base, Redis utilities) only when they fit Stock & POS rules.

## 2. Pages / routes — do not create

Do not add sidebar or standalone routes for:

| Forbidden route idea | Put it here instead |
|---|---|
| `/sales` | POS history / Sales Report |
| `/purchases` | Purchase Report |
| `/returns` | Sales Report / Purchase Report row **Return** actions |
| `/customer-debts` | Customer Debt Report |
| `/supplier-debts` | Supplier Debt Report |
| `/stock-in` | Stock or Supplier action |
| `/stock-adjustments` | Stock action |
| `/stock-damage` | Stock action |
| `/stock-expire` | Stock action |
| `/expenses` | Finance Report table + Add Expense modal only (no Expense page) |
| `/income-expense` | Finance Report |
| `/rentals`, `/motorcycles`, `/rental-reports` | Remove |

Sidebar may only contain:

Dashboard · Stock · POS · Delivery Notes · Setup (Categories, UOM, Brands, Suppliers, Customers) · Reports (5) · Administration (5)

Do not keep Categories, UOM, Brands, Suppliers, or Customers as top-level sidebar items.

A Delivery Notes **detail page is optional**. List **Update Status** + **Delivery OK** + **Print** is enough. Create allows **phone + location** and **multi-select invoices**. Do **not** add a driver/vehicle/courier schedule form.

## 3. Product features — do not add

Unless the user explicitly asks:

- ERP / general ledger accounting
- Payroll / HR
- CRM / ecommerce
- Multi-company / multi-warehouse
- Purchase-order workflow / procurement approvals
- Microservices
- Remember Me on login
- Direct edit of `current_stock` via CRUD
- Editable audit logs
- Report editing forms
- Exposing bot tokens, DB, Redis, RabbitMQ, or MinIO publicly
- **Invoice / receipt PDF generation, storage, or download** (`GET /pos/sales/{id}/invoice.pdf`, `sales.invoice_pdf_object_key`, Celery PDF jobs, MinIO invoice keys)
- **Telegram payment or invoice notifications** (text or file)
- **S3 / MinIO / R2 / Google Drive** as product storage (use local disk)
- **MinIO or S3 containers**
- Clickable Current Stock (Current Stock is a number only)
- Finance Report chart or a standalone `/expenses` page

Invoices and delivery notes are **browser/OS print of HTML only**.

## 4. Local frontend mock session — do not use yet

When the task is **frontend + mock data on local computer**:

- Do **not** require Docker / Compose
- Do **not** require live FastAPI, PostgreSQL, Redis, MinIO, RabbitMQ, Telegram containers
- Do **not** call real `/api/v1` or `/api/v2` as the primary data path
- Do **not** implement production deploy / GHCR pull as part of that session

Use:

```env
NUXT_PUBLIC_USE_MOCK_DATA=true
```

and `frontend/app/mocks/` seed/query helpers.

## 5. Data / architecture anti-patterns — do not use

- Float for money or stock quantities (use decimal)
- Redis as source of truth for stock/money/files
- PostgreSQL BYTEA/blob for product images (images are optional while MinIO is off)
- Storing invoice PDFs anywhere (MinIO, disk, BYTEA)
- Celery/RabbitMQ as a second stock/money write path, invoice-PDF pipeline, or Docker scheduler
- A Compose `scheduler` / Celery beat service (scheduler lives in the API process)
- Requiring MinIO, RabbitMQ, or extra workers for the default stack
- New Stock & POS endpoints under `/api/v2`
- Importing legacy rental types into new Stock & POS code (`types/stock-pos/` only)

## 6. Paste block for OpenCode / GLM

```text
FILTER — DO NOT USE FOR THIS PROJECT:
- No rental/motorcycle/fleet/HollyWing product UX
- No /api/v2 for new Stock & POS work
- No standalone pages: sales, purchases, returns, debts, stock-in/adjust/damage/expire, expenses (Add Expense lives on Finance Report only)
- No ERP accounting, payroll, HR, CRM, ecommerce, multi-company, multi-warehouse, PO workflow, microservices
- No Remember Me; no direct current_stock CRUD; no editable audit logs
- No invoice PDF generate/store/download; print HTML in the browser only
- No S3/MinIO/cloud object storage; images = local disk
- No Telegram payment/invoice send; Telegram = password-reset + expiry alerts + view-only inquiry
- For local mock frontend: no Docker, no live backend/RabbitMQ/Telegram required
- Money/qty = Decimal only; Redis = transient only
- No Docker scheduler (in-process API scheduler only)
Follow docs/stock_pos_ai_agent_project_spec.md, docs/PAGE_ROUTE_MAP.md, and docs/DO_NOT_USE.md.
```
