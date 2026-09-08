# Stock & POS page and route map

This file converts the product specification into an implementation allowlist. It does not expand product scope. If it conflicts with `docs/stock_pos_ai_agent_project_spec.md`, the specification wins. The **lean** Docker stack is documented in `docs/DOCKER_INFRASTRUCTURE.md` (local image files; no S3/MinIO or scheduler containers).

## Print, files, and Telegram (must not contradict)

| Topic | Rule |
|---|---|
| Invoices | Frontend HTML print only (`frontend/app/utils/print/`). Heading is វិក្កយបត្រ / INVOICE — no shop-name title. Khmer fonts. Empty line rows (A4 18 / A5 12). Bordered summary table. |
| Delivery notes | HTML print from the list (**Delivery OK** + **Print**). POS sale snapshot only; no contact/driver form. Detail route optional. |
| PDFs | Do not generate, store, or download invoice/receipt PDFs. No `GET /pos/sales/{id}/invoice.pdf`. |
| Local images | Disk under `LOCAL_STORAGE_DIR`. Keys in PostgreSQL. `GET /api/v1/images/{key}`. No S3/MinIO. Never invoices. |
| Scheduler | In-process in the FastAPI API — not a Docker/Celery beat service. |
| Report export | Immediate HTTP CSV from `/api/v1/reports/...`. |
| Telegram | Password-reset, two expiry alerts, view-only inquiry. **No** payment/invoice send. |

Default shop name: **Yoeun Sokhon Pharmacy**. Logo: `frontend/app/assets/images/logo.png` (transparent; no black background).

## Sidebar and page allowlist

| Navigation item | Frontend route | Purpose |
|---|---|---|
| Dashboard | `/` | Exactly four KPI cards in one desktop row; Income/Expense chart with auto-fit height; complete Business Summary |
| Stock | `/stock` | Products with image thumbnails, stock qty columns + history dialogs, Expire Date before Status, stock-operation actions. **Stock In history dialog** includes **Add Stock In** (purchase form, product prefilled). Product tabs: **General** \| **Pricing** (No, Original UOM, Convert UOM, Conversion qty, Sale price, Default sale, delete) \| **Expire**. No Stock History tab |
| POS | `/pos` | Full-width POS. Cart UOM select = product Pricing Original UOMs; change UOM updates price from Pricing; print-only invoice |
| Delivery Notes | `/delivery-notes` | Track delivery from POS sales. List: `AppListTable`, **Update Status**, Delivery OK, Print. Add: multi-select invoices (search on table) + phone/location; auto-open from POS with invoice preselected. Nested detail optional. |
| Setup → Categories | `/setup/categories` | Category list and add/edit/disable actions |
| Setup → Units of Measure | `/setup/uoms` | UOM list and add/edit/disable actions; required by products |
| Setup → Brands | `/setup/brands` | Brand list and add/edit/disable actions; optional on products |
| Setup → Suppliers | `/setup/suppliers` | Supplier list/add/edit (name, phone, location). List Outstanding Debt is read-only from Stock In. Purchase/debt history is Reports-only |
| Setup → Customers | `/setup/customers` | Customer list/add/edit (name, phone, location). List Outstanding Debt is read-only from POS. Sales/debt/delivery history is Reports / Delivery Notes |
| Sales Report | `/reports/sales` | Sales reporting; row **Actions (`...`) → Return** (customer return modal) |
| Purchase Report | `/reports/purchases` | Stock-in/purchase reporting; row **Actions (`...`) → Return** (return to supplier). New purchases via Stock In, not this page |
| Customer Debt Report | `/reports/customer-debts` | Invoice-level debts with Date + Invoice No.; balances and payment history |
| Supplier Debt Report | `/reports/supplier-debts` | Document-level debts with Date + Invoice/Purchase No.; balances and payment history |
| Finance Report | `/reports/finance` | Income/expense table (no chart); Add Expense modal; filters on table toolbar only |
| Users | `/administration/users` | User and role assignment management |
| Roles & Permissions | `/administration/roles` | Grouped permission management |
| Document Sequence | `/administration/document-sequences` | Supported document numbering |
| Audit Log | `/administration/audit-logs` | Read-only critical activity log |
| Settings | `/administration/settings` | Shop (default name Yoeun Sokhon Pharmacy), currency, POS, stock (incl. two expiry alert lead times), Telegram (password-reset, expiry alerts, view-only inquiry — **no** payment/invoice notify), invoice print options, and system settings |

List/detail nested routes such as `/setup/customers/:id`, `/setup/suppliers/:id`, `/stock/:id`, `/setup/uoms/:id`, or `/setup/brands/:id` are allowed when a full detail view is more usable than a drawer. `/delivery-notes/:id` is optional (list **Update Status** + Delivery OK + Print is enough). `new` routes are allowed only when the form is too large for a modal/drawer. They do not become sidebar items.

Legacy flat frontend paths (`/categories`, `/uoms`, `/brands`, `/suppliers`, `/customers`) must redirect to the matching `/setup/*` route during migration, then be removed.

## Authentication routes

Authentication is outside the application sidebar.

| Route | Rule |
|---|---|
| `/auth/setup` | Available only while no Administrator exists |
| `/auth/login` | Email/password login; no Remember Me |
| `/auth/forgot-password` | Starts Telegram verification |
| `/auth/verify-code` | Optional separate step; may be folded into forgot-password |
| `/auth/reset-password` | Requires a valid verified reset flow |

## Features that must not become standalone pages

| Feature | Approved location |
|---|---|
| Sale history/details | POS result/history UI or Sales Report |
| Sale return (customer) | Sales Report row **Actions (`...`) → Return** (or sale detail action). Modal/drawer only — no `/returns` |
| Purchase / supplier return | Purchase Report row **Actions (`...`) → Return**. Modal/drawer only — no `/returns` |
| Purchase history | Purchase Report (search/filter). Not on supplier Setup records |
| Customer debt/payment | Customer Debt Report (search/filter). Not on customer Setup records |
| Supplier debt/payment | Supplier Debt Report (search/filter). Not on supplier Setup records |
| Stock In (purchase) | Stock row action, **Stock In history dialog → Add Stock In**, or Setup → Supplier action/modal/drawer. Same form + `POST /stock/in` |
| Stock Adjustment | Stock action/modal/drawer |
| Stock Damage | Stock action/modal/drawer |
| Stock Expiry | Stock action/modal/drawer |
| Stock movement history for one product/qty column | Wide (~70% viewport) dialog from Stock list cells (**Stock In / Stock Out / Damage only**). Body uses `TableAppListTable`. **Stock In dialog** has **Add Stock In**. **Current Stock is a number only — not clickable, no dialog.** |
| Cost price history (stock-in lots) | Wide dialog from Stock list **Cost** cell. `TableAppListTable`: Date, Product name, Cost price, Qty, Amount, Version. Read-only. |
| Sale price versions (POS-active) | Wide dialog from Stock list **Price** cell. `TableAppListTable`: Checkbox (exactly one POS-active), Date, Product name, Sale price. **Add Sale Price** in the dialog. |
| Product Pricing (multi-UOM sale prices) | Product **Pricing** tab: No, Original UOM, Convert UOM, Conversion qty, Sale price, Default sale (one), delete. POS cart UOM select = Original UOMs; select UOM applies that row's sale price / factor. |
| Product expiry settings | Product document **Expire** tab: Track Expiry + Expire Date (read-only from Stock In lots). |
| Create delivery from sale(s) | Delivery Notes **Add** (multi-select invoices + phone/location on table) or POS post-sale auto-open Create Delivery Note |
| Finance/expenses | Finance Report table + Add Expense modal/drawer only; **no** `/expenses` page, **no** Finance chart |

Do not create or retain sidebar routes named `/sales`, `/purchases`, `/returns`, `/customer-debts`, `/supplier-debts`, `/stock-in`, `/stock-adjustments`, `/stock-damage`, `/stock-expire`, `/expenses`, `/income-expense`, `/rentals`, `/motorcycles`, or `/rental-reports`.

Do not keep Categories, UOM, Brands, Suppliers, or Customers as top-level sidebar items; they belong under **Setup**.

## API ownership map

The new API base is `/api/v1`. Frontend Setup nesting does not change API ownership.

| Area | Route family |
|---|---|
| Authentication/setup | `/auth/*` |
| Dashboard | `/dashboard/*` |
| Categories | `/categories/*` |
| Units of Measure | `/uoms/*` |
| Brands | `/brands/*` |
| Products | `/products/*` |
| Stock operations/history | `/stock/*` |
| Suppliers and supplier debt | `/suppliers/*` |
| POS, sales, returns, **JSON receipt for HTML print** | `/pos/*` |
| Customers and customer debt | `/customers/*` |
| Delivery notes | `/delivery-notes/*` |
| Reports | `/reports/*` |
| Users, roles, permissions, sequences, audit, settings | `/admin/*` |

Detailed methods and paths are defined in specification section 7. Internal backend module names should follow business ownership even when a feature is nested under Setup in the frontend.

## Navigation acceptance check

Before completing navigation work, confirm:

- exactly seven top-level sidebar items exist: Dashboard, Stock, POS, Delivery Notes, Setup, Reports, Administration;
- only Setup, Reports, and Administration expand;
- Setup contains exactly five items: Categories, Units of Measure, Brands, Suppliers, Customers;
- Reports contains exactly five items;
- Administration contains exactly five items;
- authentication routes do not appear in the sidebar;
- no legacy flat master-data route remains as a top-level sidebar link;
- no legacy rental/motorcycle link or unapproved operational page is reachable from navigation or global search.
