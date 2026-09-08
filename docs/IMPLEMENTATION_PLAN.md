# Stock & POS replacement plan

This plan guides replacement of the legacy motorcycle-rental application. Product behavior remains defined by `docs/stock_pos_ai_agent_project_spec.md`.

## Replacement policy

- Treat this as a domain replacement, not an in-place terminology rename.
- Work in complete vertical slices so the frontend, API, persistence, permissions, audit behavior, migrations, and tests agree.
- A slice is complete only when its legacy route is removed or disconnected, its new route is usable, and relevant checks pass.
- Do not expose half-migrated legacy/new records through one UI or API.
- During development, temporary internal compatibility code is allowed only when it has an identified removal point and cannot expose legacy product behavior.

## Phase 1: foundation and contracts

- Change product branding, configuration, environment examples, container metadata, README/status documentation, and seed data to Stock & POS.
- Establish `/api/v1`, common errors, pagination, authentication, authorization, audit plumbing, database/Redis connections, in-process scheduler, and health checks.
- Default Docker stack is **lean**: `api`, `db`, `redis`, `frontend`. Do not start MinIO, RabbitMQ, Celery workers, or a scheduler container.
- Implement one-time Administrator setup and the Telegram password-reset flow.
- Replace rental permissions with the permission codes from specification section 2.1.8.
- Create a fresh Stock & POS Alembic baseline or explicit migration chain; do not mutate the old rental schema into misleading table names.

## Phase 2: administration and master data

- Users, roles/permissions, document sequences, audit logs, and settings.
- Categories, Units of Measure (UOM), Brands, products/stock list (including product image thumbnails from local storage, Stock In/Out/Damage history dialogs via `AppListTable`; Current Stock is a number only; Cost and Sale Price cells open version dialogs), suppliers, and customers — with Categories/UOM/Brands/Suppliers/Customers nested under frontend **Setup** (`/setup/*`).
- Products require `uom_id` (base UOM); free-text unit is not the source of truth. Products may optionally set `brand_id`.
- Product form tabs: **General** | **Pricing** | **Expire**. Pricing table: No, Original UOM, Convert UOM, Conversion qty, Sale price, Default sale (exactly one), delete. Expire: Track Expiry + read-only Expire Date.
- Replace shared frontend navigation, route middleware, API client types, repositories, page chrome, forms, and table schemas.

## Phase 3: inventory transactions

- Implement the canonical stock mutation service and immutable stock movements.
- Add Stock In, Adjustment, Damage, Expiry, product/batch history, locking, validation, audit, and rollback tests.
- Supplier purchases and supplier debts are created from confirmed Stock In transactions. Stock In history dialog exposes **Add Stock In** (product prefilled) using the same purchase form.
- Sales Report / Purchase Report include row **Actions (`...`) → Return** (customer return / return to supplier). No `/returns` page.

## Phase 4: POS, payments, and returns

- Implement indexed name/barcode search and scanner behavior.
- Implement two-step POS UI: product card grid + cart (Next), then customer/summary/payment checkout, then auto-print bilingual invoice (no invoice dialog).
- Cart UOM select is **per product** from Pricing **Original UOM** rows; Default sale pre-selects on add; changing UOM updates unit price and remaining stock; sale stocks out `qty × factor_to_base` in base/Convert UOM.
- Implement cart rules, per-line unit price/discount, discount permissions/settings, customer selection, cash/Bank-QR/customer-debt payments, receipt numbering, and printing.
- Complete sales atomically and use the canonical stock service.
- Return a JSON receipt/print payload. The frontend prints bilingual HTML through the browser/OS print dialog (`frontend/app/utils/print/`). Do **not** generate, store, or download invoice PDFs; do not add `GET /pos/sales/{id}/invoice.pdf`.
- Add optional post-sale **Create Delivery Note** auto-open (invoice preselected; same customer may add more invoices). Fulfillment only — no second stock-out.
- Add sale-return (restock) and purchase-return (supplier) behavior without a standalone Returns page; wire from Sales/Purchase Report row actions.
- Implement immutable customer and supplier debt payments with partial/full settlement.

## Phase 4b: Delivery Notes

- Delivery Notes page (`/delivery-notes`) with list (`AppListTable`), **Update Status**, Delivery OK, Print. Create supports **multi-select invoices** (search on table), phone + location inputs, and **auto from POS**. Nested detail optional.
- Store linked POS invoice(s) + customer; editable **phone** and **location** on create. **No** driver, vehicle, or courier schedule form.
- Print is HTML / browser print only (no stored PDF). No second stock-out.
- Document sequence `DN-000001`.
- Permissions: delivery.view/create/update/confirm/deliver/cancel.

## Phase 5: dashboard and reports

- Dashboard: exactly four desktop KPI cards in one row (no Sales This Month card), Income/Expense chart with auto-fit height on all devices, and a complete Business Summary panel (system-wide metrics).
- Implement the five and only five reports with server-side filtering, print, and **HTTP CSV export** (no MinIO export artifacts).
- Customer Debt Report and Supplier Debt Report use **document-level rows** with required **Date** and **Invoice No.** / Purchase No. columns (not party-only aggregates that hide those fields). Party totals may be summary cards above the table.
- Finance Report: **no chart**; income/expense **table** with Add Expense modal; AppHeader has no date filter/refresh — filters stay on the table toolbar.
- Verify cost of goods sold, gross profit, damage loss, expiry loss, debts, and net result against transaction data.

## Phase 6: cleanup and production readiness

- Remove remaining rental/motorcycle models, schemas, routes, services, repositories, UI, translations, tests, migrations/bootstrap assumptions, rental Telegram bot flows, task names, and container labels.
- Keep the lean Compose stack (API + db + redis + frontend). Images are local disk. Do not require S3/MinIO, RabbitMQ, Celery, or a scheduler container. Invoices stay print-only.
- Confirm the page allowlist in `docs/PAGE_ROUTE_MAP.md` and search the repository for legacy terminology.
- Run frontend tests/typecheck/lint/build, backend tests, migration checks, Compose validation, security review, and backup/restore documentation checks (PostgreSQL).

## Phase 7: backend completion for newly approved modules

Backend-only (or backend-first) vertical slices for everything newly approved after the original plan. Follow modular monolith layout under `backend/app/modules/` and register routers in `api/v1/router.py`. Frontend Setup nesting (`/setup/*`) does not change API paths.

Must complete on `/api/v1`:

1. **Units of Measure (`modules/uoms/`)** — full CRUD, unique codes, inactive filter, safe delete, seed defaults, permissions `uom.*`, product `uom_id` required FK.
2. **Brands (`modules/brands/`)** — finish CRUD if incomplete; optional logo_object_key; permissions `brand.*`; product optional `brand_id`.
3. **Product image contract** — `image_object_key` on products; upload via `modules/image/`; list/detail responses expose resolved `imageUrl` when possible; no blobs in PostgreSQL.
4. **Stock read aggregates + history** — product list fields/endpoints for Stock In, Stock Out, Current Stock, Damage Stock derived from movements; `GET /stock/products/{id}/history` (and type-filtered variants) for dialog data; no direct current-stock edit.
5. **Delivery Notes (`modules/delivery_notes/`)** — headers/lines + `delivery_note_sales` (multi-invoice), sequence `DN-`, status workflow + **Update Status** transitions, deliverable-qty rules, phone/location fields, **JSON print payload**, POS auto-create entry, invoice multi-select search on create table; **no stock mutation**; **no driver/vehicle form**.
6. **Permissions + sequences + audit** — catalog includes uom/brand/delivery permissions; document sequence types include Delivery Note; audit critical delivery status changes.
7. **Alembic + tests** — migrations for `units_of_measure`, product.uom_id, delivery_notes tables/indexes; API/service tests for CRUD, safe delete, deliverable qty, status transitions, rollback.

Phase 7 is done when OpenAPI `/api/v1` exposes the above, focused pytest passes, and Compose/API health still works.

## Phase 8: Telegram expiry alerts and view-only inquiry

Backend-first (Settings UI fields as needed). Spec section 3.6 is the source of truth. **Do not send invoices or payment summaries to Telegram.**

1. **Settings** — `stock.expiry_alert_1_days`, `stock.expiry_alert_2_days` (examples 90 / 7), toggles for expiry alerts and stock inquiry; Administration Settings Stock + Telegram tabs. Do not persist `telegram.payment_invoice_notify_enabled`.
2. **Expiry alert scheduler** — FastAPI in-process job (`app.core.scheduler`) scans expiry-tracked lots with qty > 0; send Telegram once per lot per alert level; persist `telegram_expiry_alert_state`. **No Docker scheduler / Celery beat.**
3. **View-only Telegram bot** — Reply/inline keyboard: Menu → tool (Current Stock / Low Stock / Expiring Soon / Sales Summary) → period (Today / 7 days / This month) → paginated text results. Unlinked chats get link instructions only. **No** create/edit/delete/mutate via bot.
4. **Tests** — alert dedupe, settings lead times, inquiry handlers refuse writes, unauthorized chat denied. No payment-notify tests.

Phase 8 is done when the API process covers **password-reset send** and **expiry alerts**, Settings persist the two alert windows, and focused pytest passes. View-only inquiry may use the optional `telegram-bot` profile.

## Definition of a clean replacement

The replacement is clean when:

- no user-visible HollyWing, motorcycle, rental, fleet, rental-charge, or rental-report behavior remains;
- frontend navigation and routes match the approved page map;
- backend route registration contains only Stock & POS and shared operational endpoints;
- current stock can change only through the canonical movement service;
- sales, returns, debts, payments, and sequences are transactionally safe;
- legacy tests have been replaced by meaningful Stock & POS tests rather than simply deleted;
- deployment files start only services required by the approved architecture;
- the specification's definition of done is satisfied.
