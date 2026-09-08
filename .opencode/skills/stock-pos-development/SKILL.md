---
name: stock-pos-development
description: Implement, debug, review, or migrate this repository's Stock & POS frontend and backend while enforcing its approved pages, inventory transactions, debts, permissions, and API boundaries. Use for code work in this repository; do not use for unrelated generic questions.
metadata:
  project: stock-pos
  primary-model: glm-5.3-flash
---

# Stock & POS development

Use `docs/stock_pos_ai_agent_project_spec.md` as product truth. Read only its sections relevant to the task. Follow `AGENTS.md` for repository-wide invariants, `docs/PAGE_ROUTE_MAP.md` for allowed pages and endpoint ownership, `docs/IMPLEMENTATION_PLAN.md` for migration order, and `docs/DOCKER_INFRASTRUCTURE.md` for MinIO/RabbitMQ/Telegram Compose rules.

## Current state

The repository began as a HollyWing motorcycle-rental application. Its domain pages, APIs, models, migrations, tests, jobs, and naming are legacy migration input, not contracts to preserve. Build only the Stock & POS product. Reuse generic infrastructure only after verifying it fits the target design.

## Workflow

1. Identify the smallest complete Stock & POS vertical slice and read the relevant specification sections.
2. Inspect affected frontend, backend, tests, migrations, translations/configuration, Docker, and environment contracts before editing.
3. Search for generic utilities and patterns worth retaining; do not mechanically rename rental domain objects.
4. Implement the slice end to end, remove or disconnect its superseded legacy surface, and add business, permission, rollback, and API tests.
5. Run focused checks, then the relevant full verification commands. Report exact blocked checks.

When a requested page, module, table, workflow, infrastructure service, or dependency is not in the specification, stop and request approval before adding it.

## Non-negotiable decisions

- Target: compact ERPNext-inspired Nuxt UI frontend plus a FastAPI/PostgreSQL/Redis modular monolith.
- API: new Stock & POS routes live under `/api/v1`; do not extend the legacy rental `/api/v2` surface.
- Pages: use only the allowlist in `docs/PAGE_ROUTE_MAP.md`. Top-level sidebar: Dashboard, Stock, POS, Delivery Notes, Setup, Reports, Administration. Setup children (Categories, UOM, Brands, Suppliers, Customers) live under `/setup/*`. Operational flows such as stock in, adjustment, damage, expiry, returns, and debt payments belong inside approved parent pages.
- Data: PostgreSQL is authoritative. Redis is transient only. Money and quantity calculations are decimal-safe. Products require `uom_id`; `brand_id` is optional.
- Stock: one canonical mutation service; immutable movements for every change; row locking and atomic commit; no direct stock editing. Stock list shows product image thumbnails plus Stock In / Out / Current / Damage with clickable history dialogs.
- POS: two-step sell/checkout UI with product images on cards and cart thumbnails; sale, items, payment/debt, stock movements, document number, and audit changes commit or roll back together; bilingual printable invoice after sale; optional Create Delivery Note after sale.
- Delivery Notes: track fulfillment of sold products to clients (Draft → Confirmed → Out for Delivery → Delivered / Cancelled); partial delivery allowed; no second stock-out.
- Debt: immutable payment history, no overpayment, atomic balance/status updates.
- Security: server-side permission enforcement, IDOR protection, one-time initial setup, secure password hashing, and hashed/expiring/single-use/rate-limited Telegram reset codes.
- Sequences: allocate under database locking with no duplicates under concurrency (includes `DN-` delivery notes).
- Scope exclusions: no ERP accounting, payroll, HR, CRM, ecommerce, multi-company, multi-warehouse, purchase-order workflow, procurement approvals, multi-UOM conversion matrices (v1), courier microservices, or microservices unless explicitly requested.

## Verification

Use the narrowest useful test while iterating. Before completing a changed slice, run the applicable commands from the repository root:

```text
pnpm --dir frontend test
pnpm --dir frontend typecheck
pnpm --dir frontend lint
pnpm --dir frontend build
python -m pytest backend/tests
docker compose config --quiet
```

Never state that a command passed unless it completed successfully.
