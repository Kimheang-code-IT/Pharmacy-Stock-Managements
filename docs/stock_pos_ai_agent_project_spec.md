# Stock & POS Management System — AI Agent Project Specification

> Purpose: This document is the single source of truth for an AI coding agent building the project.
> Build the system as a small, production-ready modular monolith.
> Do not add modules or pages outside this specification unless explicitly requested.

Repository implementation companions (these five files plus `AGENTS.md` are the only product rules — do **not** add or keep `docs/prompts/`):

- `AGENTS.md` defines repository-wide engineering and migration rules.
- `docs/PAGE_ROUTE_MAP.md` is the exact frontend page allowlist and API ownership map.
- `docs/IMPLEMENTATION_PLAN.md` defines how to replace the legacy motorcycle-rental code without mixing domains.
- `docs/DOCKER_INFRASTRUCTURE.md` defines the **lean** Compose stack (API+db+redis+frontend). Images use **local disk**. RabbitMQ/Celery beat are off. The expiry scheduler runs **inside the API process**.
- `docs/DO_NOT_USE.md` is the hard exclusion filter.

The existing HollyWing motorcycle-rental frontend and backend are legacy migration input. The finished repository must contain only the Stock & POS product described here; generic infrastructure may be reused only when it conforms to this specification.

---

# 1. System Overview

## 1.1 Project Name

**Stock & POS Management System**

Default shop / application display name: **Yoeun Sokhon Pharmacy** (sidebar short name **Yoeun Sokhon**, tagline **Pharmacy**). Bundled frontend logo: `frontend/app/assets/images/logo.png` (transparent PNG — never wrap the logo in a black background).

## 1.2 Project Goal

Build a lightweight business management system for a small-to-medium shop.

The system must manage:

- Dashboard
- Product Categories
- Units of Measure (UOM)
- Brands
- Stock / Inventory
- Suppliers
- POS Sales
- Customers
- Delivery Notes (product delivery tracking to customers)
- Customer Debts
- Supplier Debts
- Reports
- Users
- Roles & Permissions
- Document Sequences
- Audit Logs
- System Settings
- Authentication
- Telegram-based forgot-password verification
- Telegram expiry-date alerts (two configurable lead times)
- Telegram view-only stock inquiry via bot keyboard (no create/edit/delete)

The system must remain simpler than ERPNext.

Use a clean business UI inspired by ERPNext:
- compact
- professional
- information-dense
- light background
- clear tables
- simple cards
- restrained spacing
- soft borders
- no oversized marketing UI
- no unnecessary gradients
- no heavy animations

Use **Nuxt UI** components for the frontend.

### 1.2.1 AI agent contract (print, files, Telegram, UI)

These decisions are product truth. Do not reintroduce removed behavior from older drafts.

**Invoices and delivery notes are print-only**

- After a confirmed POS sale, show the A4/A5 paper-size chooser, then print a bilingual HTML document through the hidden iframe (`frontend/app/utils/print/`). The OS/browser print dialog is the only output path.
- Invoice paper heading is **វិក្កយបត្រ / INVOICE** only (underlined). Do not print the shop name as a document title.
- Use a Khmer-first font stack (include Noto Sans Khmer) and wait for `document.fonts.ready` before printing. Meta block (invoice no, date, customer, cashier) is larger and bold; A4 and A5 share one style (A5 scaled).
- Line table headers are stacked **Khmer on top, English below** (e.g. ល.រ / N°), all header cells center-aligned. Cell borders are thin (**0.5px**).
- Pad the line table with empty filler rows so the grid fills about **70%** of the printable height (trim a few rows so short sales stay on one page). Product / Unit / Qty columns stay compact.
- Totals sit under the line table: label column width matches **Price + Discount**; amount column matches **Amount**. Summary cells have **left / right / bottom** borders only (no top). Rows: Total Amount, Delivery, Deposit/paid, outstanding (`ខ្វះសរុប`). Buyer / Seller signature lines below.
- Delivery notes print the same way (HTML → browser print). List actions include **Delivery OK** and **Print**. A nested detail route is optional, not required.
- Delivery notes store a **snapshot of the linked POS sale / customer** only. Do not add a contact, driver, vehicle, or schedule form.
- Do **not** generate, store, or download invoice/receipt PDFs (MinIO, disk, PostgreSQL BYTEA, or Celery PDF jobs).
- Do **not** add `GET /pos/sales/{id}/invoice.pdf` or `sales.invoice_pdf_object_key`.
- `GET /pos/sales/{id}/receipt` returns a JSON print payload for the frontend HTML printer — not a PDF.

**Local image storage — no S3 / MinIO**

- Product images, shop logo uploads, and brand logos are files on the API disk (`LOCAL_STORAGE_DIR`, default `var/media` or Docker volume `/srv/data/media`).
- PostgreSQL stores `image_object_key` / `logo_object_key` only. The UI loads `GET /api/v1/images/{object_key}`.
- Bundled chrome logo: `frontend/app/assets/images/logo.png`.
- Do **not** use S3, MinIO, Cloudflare R2, or Google Drive.
- Do **not** run MinIO/S3 containers.
- Do **not** run a Docker `scheduler`, Celery beat, RabbitMQ, or Celery workers in the default stack.
- Expiry-alert scans run **in the FastAPI API process** (`app.core.scheduler`). Telegram reset-code send also runs in that process.
- Report export is an immediate HTTP CSV from `/api/v1/reports/...`.
- Default Compose: `api`, `db`, `redis`, `frontend` only.

**Telegram — exactly three uses**

1. Forgot-password verification codes (hashed, expiring, single-use, attempt-limited, rate-limited).
2. Two Settings-configured product expiry alerts (in-process daily scan; once per lot per alert level).
3. View-only stock inquiry keyboards (period → text results). No create/edit/delete/mutate via Telegram. Optional extra `telegram-bot` container only for inquiry polling.

Do **not** send payment or invoice text (or PDFs) to Telegram.

**Stock / POS / reports UI (must match PAGE_ROUTE_MAP)**

- Dashboard: exactly four KPI cards in one desktop row — Today Sales, Income, Expense (operating expenses only), Outstanding Debt — plus Income/Expense chart with auto-fit height and complete Business Summary.
- Stock list: Current Stock is a **number only** (not clickable). Stock In / Stock Out / Damage cells open a wide history dialog (`TableAppListTable`). **Stock In** and **Damage** history dialogs have toolbar **Add** (nested form on top of the history dialog, product locked). Cost cell opens cost-history dialog. Price cell opens sale-price versions (exactly one POS-active; Add Sale Price in the dialog).
- Product form tabs: **General** | **Pricing** | **Expire**. Pricing table columns: **No**, **Original UOM**, **Convert UOM**, **Conversion qty**, **Sale price**, **Default sale**, delete. Expire tab: Track Expiry + Expire Date (read-only from stock-in lots).
- Sales Report and Purchase Report: each row has an **Actions (`...`)** column. Sales → **Return** (customer return). Purchase → **Return** (return to supplier). No `/returns` page.
- Finance Report: income/expense **table** (no chart); Add Expense modal with plus icon and full-width fields; filters on the table toolbar only; no `/expenses` page.
- Customer / Supplier Debt Reports: **document-level** rows with Date and Invoice No. / Purchase No. Row **Actions (`...`) → Pay** opens a payment modal for that open/partial debt (not on Setup customer/supplier documents).
- POS: full-width workspace; two-step sell → checkout; cart UOM select = every Pricing row for that product; selecting a UOM updates unit price / remaining stock from that row; default cart UOM = row with **Default sale**; stock out `qty × factor` in base (Convert) UOM; print-only invoice after submit. Live API payment methods: map UI Cash/Card/Mobile/Credit ↔ `CASH`/`BANK_QR`/`CUSTOMER_DEBT` (IMPLEMENTATION_PLAN Phase 9).
- Delivery Notes: list **Update Status** (allowed transitions); Add = multi-select invoices with search on `AppListTable` + phone/location; auto-open from POS with invoice preselected; no driver/vehicle form; no second stock-out.
- **FE↔BE live alignment** is tracked in IMPLEMENTATION_PLAN **Phase 9** (sale return `items`|`lines`, report list adapters, Stock In purchase header, Delivery Notes create/status, Pricing out mapping).

**Quality**

- No TODOs, stubs, unused exports, or dead compatibility layers.
- Decimal-safe money and quantities; one canonical stock mutation service; every stock change is a movement in one database transaction.
- Local mock frontend uses `NUXT_PUBLIC_USE_MOCK_DATA` (defaults to mock unless set to `false`) and does not require Docker or live API. Frontend-only / Vercel preview deploys should keep mock on so login works without a backend.

---

## 1.3 Final Main Navigation

The sidebar must contain only these main items:

1. Dashboard
2. Stock
3. POS
4. Delivery Notes
5. Setup
6. Reports
7. Administration

Only **Setup**, **Reports**, and **Administration** have sidebar sub-pages.

### Setup

Master-data and party records used across Stock and POS:

- Categories
- Units of Measure (UOM)
- Brands
- Suppliers
- Customers

Frontend routes for Setup children live under `/setup/*` (same pattern as `/reports/*` and `/administration/*`):

- `/setup/categories`
- `/setup/uoms`
- `/setup/brands`
- `/setup/suppliers`
- `/setup/customers`

Do not keep Categories, UOM, Brands, Suppliers, or Customers as top-level sidebar items.

### Reports

- Sales Report
- Purchase Report
- Customer Debt Report
- Supplier Debt Report
- Finance Report

### Administration

- Users
- Roles & Permissions
- Document Sequence
- Audit Log
- Settings

Do not create separate sidebar pages for:

- Sales
- Purchases
- Returns
- Customer Debts
- Supplier Debts
- Stock In
- Stock Adjustment
- Stock Damage
- Stock Expire
- Finance

Those features must exist inside the approved pages.

API route families stay business-owned (`/api/v1/categories`, `/api/v1/customers`, etc.). Only the frontend navigation/path nesting changes under Setup.

---

## 1.4 Authentication Flow

Authentication is outside the sidebar.

### First-Time Setup

If no Administrator user exists:

1. Show Initial Setup page.
2. Ask for:
   - Full Name
   - Email
   - Password
   - Confirm Password
   - Telegram Chat ID
3. Create the first user.
4. Automatically assign role: `Administrator`.
5. Mark initial setup as completed.
6. Redirect to Login.

Once an Administrator exists, the initial setup page must not be accessible.

### Login

Fields:

- Email
- Password
- Show / Hide Password
- Login button
- Forgot Password link

Do not implement "Remember Me".

### Forgot Password

Flow:

1. User enters email.
2. System finds the user.
3. System checks saved Telegram Chat ID.
4. Generate one-time verification code.
5. Send code through Telegram Bot.
6. User enters code.
7. Validate:
   - code matches
   - code not expired
   - code not already used
   - attempt limit not exceeded
8. Allow user to enter:
   - New Password
   - Confirm New Password
9. Update password.
10. Mark token/code used.
11. Write Audit Log.
12. Redirect to Login.

Recommended code expiry: **5 minutes**.

Never send the old password.

Passwords must be securely hashed.

---

# 2. System Requirements

## 2.1 Functional Requirements

### 2.1.1 Dashboard

Dashboard must show **exactly 4** important summary cards in **one row** on desktop (`grid` with four equal columns). Do not add a fifth card (including do not show “Sales This Month” as a KPI card).

Recommended KPI cards (exactly these four):

1. Today Sales
2. Income
3. Expense
4. Outstanding Debt (combined remaining customer + supplier debt; hint may break out customer vs supplier)

On tablet/mobile, cards wrap as 2×2 (still four cards total — never five).

Below the cards, one row on desktop:

- **Left (~70%):** one line chart with exactly two series — Income and Expense
- **Right (~30%):** **Business Summary** — the complete system snapshot (not a short duplicate of the KPI row)

Chart period controls (date range) stay on the chart card. Useful defaults: current month; last 7 days; custom range.

#### Chart height / responsiveness

- Chart container must **auto-fit height** across laptop, tablet, and mobile — fill the remaining dashboard workspace below the KPI row (flex/`min-h-0`), not a fixed pixel height that clips or leaves empty space.
- ECharts (or equivalent) must **autoresize** on window resize, sidebar collapse, and container size changes.
- Minimum readable height on small screens (e.g. ~220–280px); grow with available viewport on larger screens.
- On mobile/tablet, stack chart above Business Summary; each still uses flexible height.

#### Business Summary (complete system list)

Business Summary is the place for the fuller Stock & POS snapshot. Include at least:

**Sales & money**

- Sales This Month (count and/or amount — lives here, not as a KPI card)
- Total Income (selected/default period or month-to-date — label clearly)
- Total Expense
- Gross Profit
- Net Result / Net Income

**Debts**

- Customer Debt (remaining)
- Supplier Debt (remaining)

**Stock health**

- Total Products
- Low Stock count
- Out of Stock count
- Damage Loss
- Expiry Loss

**Operations (when data exists)**

- Pending / open Delivery Notes count (optional but recommended once Delivery Notes ship)
- Recent Sales (short list or link) — optional below the metric list
- Recent Stock Activity — optional
- Top Selling Products — optional

Do not invent extra sidebar pages for these metrics. Permission-gate sensitive values (profit/net) when required.

Access to sensitive values such as profit can be permission-controlled.

---

## 2.1.2 Categories

Category is a Setup sub-page (not a top-level sidebar item).

Route: `/setup/categories`

Features:

- List categories
- Search
- Add category
- Edit category
- Disable category
- Delete category only when safe

Fields:

- id
- code
- name
- description
- status
- created_at
- updated_at

Rules:

- Category name is required.
- Category code must be unique.
- Inactive categories must not appear in POS filters.
- If a category is linked to products, do not hard-delete it unless products are reassigned first.

---

## 2.1.3 Units of Measure (UOM)

Units of Measure is a Setup sub-page (master data), same operational pattern as Categories.

Route: `/setup/uoms`

Features:

- List UOMs
- Search
- Add UOM
- Edit UOM
- Disable UOM
- Delete UOM only when safe

Fields:

- id
- code
- name
- symbol (short display label, e.g. `pcs`, `box`, `kg`)
- description
- status
- created_at
- updated_at

Rules:

- UOM name is required.
- UOM code must be unique.
- Symbol is required and should be short (used on Stock, POS cart, and invoices).
- Inactive UOMs must not appear in product create/edit selectors or POS-facing pickers.
- If a UOM is linked to products (or historical lines that require referential integrity), do not hard-delete it unless products are reassigned first; prefer disable.
- Products must store `uom_id` (FK). Do not rely on free-text unit strings as the source of truth.
- Sale items, stock movements, and printed invoices display the UOM name/symbol snapshot at transaction time when useful, but product master always references the live UOM record.
- Products may define a **Pricing** table (pack / multi-UOM sale prices) on the product document **Pricing** tab. Same underlying `uom_conversions` data. Table columns (exact UI — only these):

  | Column | Behavior |
  |---|---|
  | **No** | Row number (1-based), display only |
  | **Original UOM** | From / sell unit (active Setup UOM). Unique per product. This is the UOM the cashier selects on POS. |
  | **Convert UOM** | Target / stock UOM. Defaults to the product **base UOM** from General (`uom_id`) — show as read-only (symbol — name) unless the product later allows another active UOM. Stock always mutates in Convert UOM when Convert UOM = base. |
  | **Conversion qty** | `factor_to_base` — how many of **Convert UOM** equal 1 of **Original UOM** (`NUMERIC > 0`). Helper e.g. `1 box = 12 pcs`. For a base=base row, qty is always `1`. |
  | **Sale price** | Sale price **per Original UOM** (`> 0`) |
  | **Default sale** | Checkbox. Exactly **one** row per product may be default. When the product is added to the POS cart, that Original UOM is pre-selected. New first/base row may default-checked; checking another row unchecks the previous. |
  | **Delete** | Remove row icon. Do not delete the last remaining row if it would leave the product with no sellable UOM (keep at least one pricing row, typically base). |

  Do **not** add Cost price or extra columns. Cost price stays on **General**.
- All `current_stock`, stock movements, and oversell checks are in the product **base UOM** (General `uom_id`, usually shown as Convert UOM). Converted quantities (`qty × factor_to_base`) must be decimal-safe — never persist float math.
- Stock In lines may select Original UOMs from Pricing; received qty converts to base before the stock mutation.
- **POS cart (per product):**
  1. UOM select options = every Pricing row's **Original UOM** for that product only.
  2. On add-to-cart: pre-select the row with **Default sale**; if none, use the base/Original=Convert row or first row.
  3. When the cashier **changes UOM**: update unit price to that row's **Sale price**; quantity stays in Original UOM; remaining stock display = `baseStock ÷ Conversion qty`; line UOM symbol = Original UOM.
  4. On complete sale: stock out `lineQty × Conversion qty` in base/Convert UOM; oversell blocked against base stock unless `allow_negative_stock`.
- The POS-active sale-price version (`product_sale_prices`) may sync with the base Original UOM row; pack prices come from Pricing rows.

Seed examples (development):

- PCS / Piece / pcs
- BOX / Box / box
- CAN / Can / can
- BTL / Bottle / btl
- KG / Kilogram / kg
- PACK / Pack / pack

---

## 2.1.4 Brands

Brand is a Setup sub-page (master data), same operational pattern as Categories and UOM.

Route: `/setup/brands`

Features:

- List brands
- Search
- Add brand
- Edit brand
- Disable brand
- Delete brand only when safe

Fields:

- id
- code
- name
- description
- logo_object_key (optional; local-disk object key for brand logo)
- status
- created_at
- updated_at

Rules:

- Brand name is required.
- Brand code must be unique.
- Inactive brands must not appear in product create/edit selectors.
- If a brand is linked to products, do not hard-delete it unless products are reassigned first; prefer disable.
- Products store optional `brand_id` (FK). Brand is recommended for filtering/reporting but not mandatory for every product in v1.
- Stock list and POS may show brand name as a secondary label when present.

---

## 2.1.5 Stock

Stock is one main page.

Do not create separate sidebar pages for stock operations.

The Stock page must contain:

- Product List (with product image thumbnail per row)
- Add Product
- Edit Product
- Product Details
- Search
- Barcode Search
- Category Filter
- UOM
- Current Stock
- Stock In total (derived)
- Stock Out total (derived)
- Damage Stock total (derived)
- Minimum Stock
- Cost Price
- Selling Price
- Expiry Tracking
- Quantity history dialog from Stock In / Stock Out / Damage list cells (not a Stock History tab on the product document)
- Product image upload/display (local-disk object key in DB; API-mediated URL for UI)

Stock list quantity columns:

- **Stock In** — cumulative inbound quantity for the product
- **Stock Out** — cumulative outbound quantity from sales (and other non-damage outflows as defined)
- **Current Stock** — authoritative on-hand quantity (`current_stock` / product quantity)
- **Damage Stock** — cumulative damaged quantity

Stock list also shows **Expire Date** immediately before **Status**:

- Value is the **nearest lot expiry date** for the product (soonest non-null `expiry_date` from stock-in / movement lots)
- Blank (`—`) when the product does not track expiry or no lot expiry is set
- Not directly editable on the product row — set via Stock In (and similar lot-bearing operations)

Clicking **Stock In**, **Stock Out**, or **Damage Stock** opens a history dialog (not a new page) filtered to that product and movement kind.

**Current Stock is display-only:** show the on-hand number in the cell. Do **not** make it a link/button and do **not** open a history dialog from Current Stock.

**History dialog (Stock In / Stock Out / Damage only):**

- Desktop dialog width must be **about 70% of the viewport**.
- Body must use the shared list table from `frontend/app/components/table` — **`TableAppListTable` / `AppListTable`** (same pattern as Finance Report). Do **not** use a raw HTML `<table>` and do **not** use `AppLineTable` (that is for editable document lines).
- Toolbar: search; optional date range (filter the movement rows). Pagination in the table footer.
- Columns: Date, Type, Quantity, Reference, User, Note. Read-only; Close in footer; no edit/delete of movements.
- On tablet/mobile, use nearly full width (e.g. ~95% / full sheet) with horizontal scroll inside the table if needed.
- Still a dialog/modal — never a separate page or route.

**Stock In / Damage history dialog — Add:**

- On the **Stock In** history dialog, show **Add Stock In** on the table toolbar (`#actions`; permission `products.operate` / `products.edit` or equivalent; hide when denied).
- On the **Damage** history dialog, show **Add Damage** the same way (same permission gate). **Stock Out** stays read-only (no Add).
- Clicking Add opens a **nested** small form dialog stacked on top of the history dialog (elevated z-index; same pattern as Sale Price → Add Sale Price) — not a new route. Product is locked to the history product.
- Stock In nested form: UOM (Pricing Original UOMs), qty, unit cost, note. Damage nested form: qty (−), note.
- Confirming runs the same stock operation as the product-list row action (`createStockOperation`). After success, reload history rows and refresh the Stock list; keep the history dialog open.
- Stock In confirming creates a purchase: increases stock via the canonical stock mutation service, may create/update product cost, and creates **supplier debt** when not fully paid (see Stock In rules and §4.4).
- Stock operation / nested Add form fields are **full width** inside the dialog.

**Cost Price cell (Stock list):**

Clicking **Cost** / **Cost Price** opens a wide dialog (~70vw, same chrome as qty history). It is **not** a new page.

- Body: `TableAppListTable` only (not a raw HTML table, not `AppLineTable`).
- Source: **Stock In lots** for this product (`stock_transaction_items` / mock `stockIns` line items). Read-only — do not add/edit cost rows here (costs are created by Stock In).
- Columns:
  1. Date (stock-in date)
  2. Product name
  3. Cost price (unit cost of that lot)
  4. Qty
  5. Amount (`qty × cost_price`, decimal-safe)
  6. Version — sequential per product, oldest stock-in = `1`, next = `2`, … (display as the version number)
- Newest lots first. Search + optional date range + pagination on the table toolbar.
- The Stock list Cost cell still shows the product’s current `cost_price` (latest / maintained product cost). It is clickable (tabular-nums + link style), not a plain unclickable number.

**Sale Price cell (Stock list):**

Clicking **Price** / **Sale Price** opens a wide dialog (~70vw). It is **not** a new page.

- Body: `TableAppListTable` only.
- Source: **sale-price versions** for this product (`product_sale_prices`). The product’s `selling_price` always equals the **POS-active** version.
- Columns:
  1. **Checkbox** — which version POS uses when selling to a customer. **Exactly one** row is checked (radio behavior with a checkbox control). Checking a row unchecks others, sets `is_active` on that version, and copies that price onto `products.selling_price` / `salePrice`. Do **not** use AppListTable bulk row-selection for this.
  2. Date (effective / created date)
  3. Product name
  4. Sale price
- **Add Sale Price** button on this dialog (table toolbar `#actions` or dialog footer — not a new route). Opens a small form/modal: date (default today), sale price (`> 0`). Saving creates a new version; the new version becomes the POS-active price. Permission: `product.update` (hide/disable add + checkbox when denied; viewing still allowed with `stock.view`).
- POS add-to-cart / product cards **must** use the active sale-price version (`selling_price`), never a stale or unchecked version.
- Newest versions first. Search + optional date range + pagination.

Stock actions must be available through tabs, buttons, drawers, or modals:

- Stock In
- Stock Adjustment
- Stock Damage
- Stock Expire

### Product Fields

- id
- code / SKU
- barcode
- name
- category_id
- uom_id
- brand_id (optional)
- cost_price
- selling_price
- current_stock
- minimum_stock
- expiry_tracking
- image (stored on local disk; DB keeps object key)
- status
- note
- created_at
- updated_at

Rules:

- SKU must be unique.
- Barcode must be unique when present.
- Product name is required.
- Category is required.
- UOM is required.
- Brand is optional.
- Current stock must not be directly editable.
- Stock changes must be derived from stock movement transactions.
- Inactive products must not be selectable in POS.
- Product image is optional but strongly recommended for Stock list and POS.
- When an image exists, Stock list and POS must display it; when missing, show a compact package placeholder (never a broken image icon).
- Image binary lives on local disk; PostgreSQL stores `image_object_key` only. List/detail APIs may return a resolved `imageUrl` (API-mediated) for the UI.

### Stock In (Purchase)

Stock In **is** the supplier purchase for inventory. There is no separate Purchases page — create/manage Stock In from Stock list row actions, from the **Stock In history dialog → Add Stock In** (nested form), or (optionally) a supplier-scoped action. Purchase history and returns are managed on **Purchase Report**. Damage may also be created from the **Damage history dialog → Add Damage**.

Header fields:

- stock_in_no (sequence)
- supplier_id (required for purchase / debt tracking)
- stock_in_date
- reference_no (supplier invoice / optional)
- note
- paid_amount (0 … total; payment method when paid_amount > 0)
- status (derived: PAID / PARTIAL / UNPAID when supplier-facing)

Line fields:

- product_id
- uom_id (Original UOM from the product Pricing table, or base UOM)
- quantity (in the selected UOM, > 0)
- cost_price (per the selected UOM; defaults from product cost / Pricing conversion, editable)
- total_cost (`qty × cost_price`, decimal-safe)
- batch_no
- expiry_date (required when product Track Expiry is on)

Rules:

- quantity > 0 in the selected UOM
- received qty is converted to the base UOM before the stock mutation: `current_stock += quantity × factor_to_base`
- the stock-in line/movement snapshots the selected UOM symbol for history display
- cost_price >= 0
- confirming stock in must increase stock via the canonical stock mutation service + immutable `STOCK_IN` movement
- link supplier; if `paid_amount < total_cost`, create **supplier debt** for the remaining amount in the same transaction
- if `paid_amount > 0`, create supplier payment / stock-in payment record (immutable)
- update product `cost_price` / weighted average when enabled
- confirmed stock in must **not** be edited or deleted; corrections use **Return to supplier** (Purchase Report) or Adjustment / Damage / Expire as appropriate
- Entry points share one form and one `POST /stock/in` (or equivalent) API

### Stock Adjustment

Fields:

- adjustment_no
- date
- product_id
- system_quantity
- actual_quantity
- difference
- reason
- note
- created_by

Formula:

`difference = actual_quantity - system_quantity`

Rules:

- positive difference -> Adjustment In
- negative difference -> Adjustment Out
- reason is required
- create stock movement
- write audit log

### Stock Damage

Fields:

- damage_no
- date
- product_id
- quantity
- unit_cost
- total_loss
- reason
- note
- created_by

Rules:

- damage quantity > 0
- damage quantity cannot exceed available stock
- confirmed damage decreases stock
- create stock movement
- damage loss must appear in reports

### Stock Expire

Fields:

- expire_no
- date
- product_id
- batch_no
- expiry_date
- quantity
- unit_cost
- total_loss
- note
- created_by

Rules:

- only applicable to expiry-tracked products
- expired quantity cannot exceed available batch quantity
- confirming expiry decreases stock
- create stock movement
- expiry loss must appear in reports

---

## 2.1.6 Suppliers

Suppliers is a Setup sub-page (not a top-level sidebar item).

Route: `/setup/suppliers`

Features:

- Supplier List
- Add Supplier
- Edit Supplier
- Search Supplier
- (Purchase / Stock In history, supplier debt, and payments live on Reports — search and filter there. Do not create those views on the supplier record. Outstanding Debt is a list-table column only, derived from unpaid/partial Stock In — not a create/edit field.)

Supplier Fields:

- id
- code
- name
- company_name
- phone
- location
- note
- status
- created_at
- updated_at

Supplier Debt fields:

- supplier_id
- stock_in / purchase reference
- document_no / invoice_no (display document number — Stock In / Purchase No.)
- transaction_date / date
- total_amount
- paid_amount
- remaining_amount
- due_date
- status

Any supplier-debt table (Customer/Supplier **Debt Report**) must show **Date** and **Invoice No. / Purchase No.** columns.
Debt statuses:

- UNPAID
- PARTIAL
- PAID

---

## 2.1.7 POS

POS must be optimized for fast cashier use.

### Product Search

Support all:

- Search by Product Name
- Search by Barcode
- Scan Barcode
- Filter by Category

Barcode scanner behavior:

- A standard barcode scanner behaving as keyboard input must work.
- Scanner input goes to the barcode/search field.
- Exact barcode match adds product directly to cart.
- If product already exists in cart, increment quantity.

### POS Layout

Recommended layout:

Left:
- search bar
- category filters
- product grid/list

Right:
- cart
- customer selector
- totals
- payment controls

### Cart

Features:

- Add product
- Increase quantity
- Decrease quantity
- Remove product
- Item price
- Discount
- Subtotal
- Grand total

Rules:

- Do not allow quantity greater than available stock unless setting `allow_negative_stock = true`.
- Discount must respect user permission.
- Maximum discount must respect settings.

### Customer

Support:

- Select Customer
- Walk-in Customer
- Quick Add Customer if user has permission

### Payment Types

- Cash
- Bank / QR
- Customer Debt

Cash:

- amount_received
- change_amount

Customer Debt rules:

- must select a real registered customer
- Walk-in Customer cannot create debt
- create customer debt record
- support partial payment

### Completing Sale

On successful POS sale:

1. Create sale
2. Create sale items
3. Create payment or customer debt
4. Create stock movements
5. Reduce stock
6. Update reports
7. Generate invoice number
8. Return a JSON receipt/print payload so the frontend can print HTML (browser/OS print only)
9. Write audit log if required

Do not generate or store an invoice PDF. Do not enqueue Telegram invoice/payment messages.

---

## 2.1.8 Customers

Customers is a Setup sub-page (not a top-level sidebar item).

Route: `/setup/customers`

Features:

- Customer List
- Add Customer
- Edit Customer
- Search
- (Purchase history, customer debt, payments, and delivery notes live on Reports / Delivery Notes — search and filter there. Do not create those views or Record Payment on the customer record. Outstanding Debt is a list-table column only, derived from unpaid/partial POS sales — not a create/edit field.)

Fields:

- id
- code
- name
- phone
- location
- note
- status
- created_at
- updated_at

Customer Debt fields:

- customer_id
- sale_id
- invoice_no
- invoice_date / date (sale / invoice date)
- invoice_total
- paid_amount
- remaining_amount
- due_date
- status

Any customer-debt table (Customer Debt Report) must show **Date** and **Invoice No.** columns before or immediately after the party name.
Debt status:

- UNPAID
- PARTIAL
- PAID

Rules:

- debt payment updates remaining amount
- payment history must be immutable
- debt reaching zero becomes PAID
- Setup customer/supplier records store name, phone, location, and status only — no purchase/payment/delivery UI on those pages. Persist `location` in the existing `address` column; do not show email on these records.

---

## 2.1.9 Delivery Notes

Delivery Notes is a main sidebar page for tracking product delivery to customers after they buy (fulfillment). It does **not** replace POS sales and does **not** reduce stock again — stock is already deducted when the sale completes.

Purpose:

- Create a delivery note from one or more confirmed POS invoices (full or partial lines)
- Capture **phone** and **location** for this delivery
- Track delivery status to the client (including **Update Status** from the list)
- Print a delivery note (HTML / browser print only; no stored PDF)
- See what remains to deliver per sale line

Features:

- List delivery notes (search, status filter, date filter, customer filter) using `TableAppListTable` / `AppListTable`
- **Add** delivery note: multi-select invoices with invoice-no search; selected invoices appear in the create table; editable phone + location
- **Auto from POS**: after a sale with Delivery checked (or post-sale Create Delivery Note), open create flow with that invoice already selected
- Edit draft (lines/qty, phone, location)
- **Update Status** from the list (and optional detail) with allowed-transition logic
- Cancel (only before Delivered; reason required)
- Print from the list (and optional detail)

Statuses:

- Draft
- Confirmed
- Out for Delivery
- Delivered
- Cancelled

Header fields:

- id
- delivery_no (sequence `DN-000001`)
- customer_id (required; must match selected invoices’ customer — all selected invoices must be for the **same customer**)
- delivery_phone (editable; default from customer / sale snapshot)
- delivery_location / delivery_address (editable; default from customer location / sale snapshot)
- invoice display: one or more invoice nos from linked sales (denormalized list or joined string for list/print)
- delivered_at
- status
- note
- created_by
- created_at
- updated_at

Linked invoices (many):

- delivery_note_id
- sale_id
- invoice_no (snapshot)

Line fields:

- id
- delivery_note_id
- sale_id (parent invoice of the line)
- sale_item_id (when linked to a sale line)
- product_id
- product_name (snapshot)
- uom_symbol (snapshot)
- qty_ordered (from sale line)
- qty_to_deliver
- qty_delivered (set when status becomes Delivered; default equals qty_to_deliver)

Rules:

- Delivery notes are created from **confirmed POS sales/invoices only**. One delivery note may include **multiple invoices** for the same customer.
- Selecting an invoice loads its remaining deliverable lines into the create table. Deselecting removes those lines (or clears qty for that invoice).
- `qty_to_deliver` cannot exceed remaining undelivered qty for that sale line across non-cancelled delivery notes.
- Partial delivery is allowed (multiple delivery notes per sale over time; multiple sales on one note).
- **Phone** and **location** are required for Confirm / Out for Delivery / Delivered (editable inputs on create/edit — not a driver/vehicle/schedule form).
- Do **not** add driver name, vehicle, or courier microservice fields in v1.
- Confirming / Out for Delivery / Delivered / Cancel must be permission-checked and audited.
- **Update Status** only allows legal transitions (see Status transitions). Invalid jumps return 400.
- Delivered is terminal for quantity purposes; do not edit lines after Delivered.
- Cancelled notes release reserved-to-deliver quantities back to each sale’s remaining-to-deliver pool.
- Delivery Notes do not create stock movements (no second stock-out).
- Document sequence type: Delivery Note → `DN-000001`.

Status transitions (Update Status logic):

| From | Allowed next |
|---|---|
| Draft | Confirmed, Cancelled |
| Confirmed | Out for Delivery, Delivered, Cancelled |
| Out for Delivery | Delivered, Cancelled |
| Delivered | (none — terminal) |
| Cancelled | (none — terminal) |

- List **Update Status** opens a small dialog/menu of **allowed next statuses only** (or a single primary action that advances to the next operational status when only one applies).
- Shortcut **Delivery OK** may still map to **Delivered** when permitted from Draft / Confirmed / Out for Delivery (same as setting status → Delivered), with audit.
- Setting **Delivered** sets `delivered_at` (UTC) if empty.
- **Cancelled** requires a reason.

---

## 2.1.10 Reports

Reports has exactly 5 sidebar sub-pages.

### Sales Report

Filters:

- Today
- This Week
- This Month
- Custom Date Range
- Invoice No.
- Customer
- Product
- Category
- Cashier
- Payment Method

Metrics / columns:

- Date
- Invoice No.
- Customer
- Product
- Quantity
- Selling Price
- Discount
- Sales Amount
- Return Amount
- Cost
- Gross Profit
- Cashier
- Payment Method
- **Actions (`...`)** — row menu (not a separate sidebar page)

**Row Actions (`...`):**

- **Return** — open **Customer return** modal/drawer for that sale (invoice). Prefer document-level return against the sale; if the report row is a line, pre-select that product/line but still return against the parent sale.
- Hide/disable Return when the user lacks return permission, the sale has nothing left to return, or the sale is voided/cancelled (if those states exist).

Support:

- Print
- Export if enabled

### Customer return (from Sales Report / sale)

Not a standalone `/returns` page. Modal/drawer only.

Logic:

1. Load sale + items; for each line show sold qty, already returned qty, **returnable qty**.
2. User enters return qty (0 … returnable) per line; reason required; optional restock checkbox (default true for inventory products).
3. Refund amount = sum of (return qty × net unit price after line discount), decimal-safe. Cannot exceed remaining refundable for the sale.
4. On confirm (one DB transaction):
   - create immutable `sale_returns` + `sale_return_items`
   - if restock: stock mutation **in** via canonical service (`SALE_RETURN` movement); if not restock, do not increase stock
   - apply refund: reduce customer debt remaining when the sale created debt; otherwise record cash/bank refund payment as configured
   - update sale return totals / report `Return Amount`
   - audit log
5. Reject over-return, concurrent over-return, and oversell of restock edge cases with rollback.

**API contract:** `POST /api/v1/pos/sales/{id}/return` body must accept both `items` and `lines` arrays (same element shape: `sale_item_id`, `quantity`, `restock`). Reason required. See IMPLEMENTATION_PLAN Phase 9.

### Purchase Report

This report is sourced from Stock In / supplier purchase transactions.

Filters:

- Date Range
- Supplier
- Product
- Status

Metrics / columns:

- Stock In / Purchase No.
- Date
- Supplier
- Product
- Quantity
- Cost Price
- Total Cost
- Paid
- Remaining Supplier Debt
- Status
- **Actions (`...`)** — row menu

**Row Actions (`...`):**

- **Return** — open **Return to supplier** modal/drawer for that Stock In / purchase document. Prefill product/line when the report row is line-level.
- Hide/disable when nothing remains returnable on that purchase, stock cannot cover the return (unless `allow_negative_stock`), or permission denied.

### Return to supplier (from Purchase Report)

Not a standalone page. Complements Stock In (purchase).

Logic:

1. Load Stock In header + lines; for each line show received qty, already returned qty, **returnable qty**.
2. User enters return qty (0 … min(returnable, available stock in base UOM after UOM conversion)) per line; reason required.
3. Return value = sum of (return qty × line cost), decimal-safe.
4. On confirm (one DB transaction):
   - create immutable purchase/supplier return header + items (see data model)
   - stock mutation **out** via canonical service (`PURCHASE_RETURN` / supplier-return movement); cannot exceed available stock unless `allow_negative_stock`
   - money: reduce **supplier debt** remaining when debt exists for that stock-in (cannot drive remaining below 0 without an explicit credit path); if the purchase was fully paid, record a supplier credit / refund amount against that document for reporting
   - update Purchase Report returnable quantities / status as needed
   - audit log
5. Confirmed Stock In stays immutable; returns are separate documents. Reject over-return with rollback.

### Customer Debt Report

Primary table is **invoice-level customer debt rows** (not one row per customer aggregate). Each open/partial/paid debt document is one row.

Required columns (order):

1. **Date** (invoice / sale date)
2. **Invoice No.**
3. Customer
4. Invoice Total
5. Paid Amount
6. Remaining Amount
7. Due Date
8. Status

Filters: date range, customer, status, search by invoice no / customer.

**Pay (row action):** each open/partial row has **Actions (`...`) → Pay**. Opens a small payment modal (`ReportsDebtPaymentDialog`) for **that debt document** — amount (default = remaining; reject overpayment), payment method (Cash / Card / Mobile Payment / Bank Transfer — not Credit), optional reference. Confirm calls `payCustomerDebt` with `customerId` + `debtId`. Paid rows (`remaining = 0`) disable Pay. Do **not** put Record Payment on Setup → Customers.

Support debt payment history (separate section or drill-down). Do not omit Date or Invoice No.

### Supplier Debt Report

Primary table is **document-level supplier debt rows** (not one row per supplier aggregate). Each unpaid/partial/paid stock-in / purchase debt is one row.

Required columns (order):

1. **Date** (stock-in / purchase date)
2. **Invoice No.** / Purchase No. / Stock In document no. (canonical document number shown as Invoice No. in the UI when that is the shop label; otherwise label “Purchase No.” — both refer to the same document reference)
3. Supplier
4. Total Amount
5. Paid Amount
6. Remaining Amount
7. Due Date
8. Status

Filters: date range, supplier, status, search by document no / supplier.

**Pay (row action):** same pattern as Customer Debt — **Actions (`...`) → Pay** → payment modal for that document → `paySupplierDebt` with `supplierId` + `debtId`. Do **not** put Record Payment on Setup → Suppliers.

Support supplier debt payment history. Do not omit Date or document/Invoice No.

### Finance Report

Route: `/reports/finance` only. Do **not** create a standalone Expense page or `/expenses` / `/income-expense` routes.

Do not create a full accounting / general-ledger module.

Finance is an **operational income & expense table**, not a chart page.

#### Layout

1. Optional compact summary cards (Income, Expense, Net, outstanding debts / other approved totals)
2. **Main content: a table** of income and expense rows (manage and review)
3. **No chart** on the Finance page (no Income/Expense trend chart, bar chart, or line chart here). Dashboard may still use Income/Expense charts.

#### Table (required)

Combined ledger table (or Income / Expense tabs that share one table pattern) with columns such as:

- Date
- Type (Income | Expense)
- Reference / Invoice No. (income from sales) or Category (expense)
- Description / Note
- Amount
- Payment method (when applicable)
- Created by / User
- Status (optional)

Income rows are derived from confirmed POS sales / payments (system-generated; not manually “added” as free-form income unless explicitly approved later).

Expense rows are user-managed operating expenses recorded on this page.

#### Add Expense (allowed on Finance only)

- Header (or table primary action) provides **Add Expense** — opens a modal/drawer (not a new page).
- Fields: date, category, description/note, amount, payment method (optional reference).
- Permission-gated (e.g. `report.finance` plus create/expense permission as defined in the permission catalog).
- Creating an expense updates the Finance table and Finance totals; include expense in Net Result when present.
- Do **not** add sidebar item “Expenses”.

#### Filters and header chrome

- **AppHeader / page header:** title + breadcrumbs + **Add Expense** only.
- **Do not** put date range filter or Refresh control in the AppHeader for Finance.
- **Table toolbar** holds filters: search, date range, type (Income/Expense), and category when useful. Refresh/reload belongs with the table pattern if needed — not as a header Refresh button.

#### Summary metrics (cards or footer totals)

May still show:

- Total Sales / Income
- Total Expense (including recorded operating expenses)
- Total Purchase Cost (optional card)
- Total Customer Debt
- Total Supplier Debt
- Cost of Goods Sold
- Stock Damage Loss
- Stock Expire Loss
- Gross Profit
- Net Result

Recommended formulas:

`Gross Profit = Sales Revenue - Cost of Goods Sold`

`Net Result = Gross Profit - Damage Loss - Expire Loss - Operating Expenses`

(Operating expenses = rows created via Add Expense on Finance.)


---

## 2.1.11 Administration

Administration has exactly 5 sidebar sub-pages.

### Users

Features:

- List users
- Add user
- Edit user
- Disable user
- Reset password
- Assign role
- Configure Telegram Chat ID

Fields:

- id
- full_name
- email
- password_hash
- telegram_chat_id
- telegram_verified
- role_id or user_roles relation
- status
- last_login_at
- created_at
- updated_at

### Roles & Permissions

Default roles may include:

- Administrator
- Manager
- Cashier
- Stock Staff

Permission examples:

#### Dashboard
- dashboard.view
- dashboard.view_profit

#### Categories
- category.view
- category.create
- category.update
- category.delete

#### Units of Measure
- uom.view
- uom.create
- uom.update
- uom.delete

#### Brands
- brand.view
- brand.create
- brand.update
- brand.delete

#### Stock
- stock.view
- product.create
- product.update
- product.delete
- stock.in
- stock.adjust
- stock.damage
- stock.expire

#### Suppliers
- supplier.view
- supplier.create
- supplier.update
- supplier.delete
- supplier.debt.pay

#### POS
- pos.access
- pos.discount
- pos.debt_sale
- pos.print

#### Customers
- customer.view
- customer.create
- customer.update
- customer.delete
- customer.debt.pay

#### Delivery Notes
- delivery.view
- delivery.create
- delivery.update
- delivery.confirm
- delivery.deliver
- delivery.cancel

#### Reports
- report.sales
- report.purchase
- report.customer_debt
- report.supplier_debt
- report.finance
- expense.create   # Add Expense on Finance Report only (no Expense page)

#### Administration
- user.manage
- role.manage
- sequence.manage
- audit.view
- settings.manage

### Document Sequence

Supported documents:

- Invoice: `INV-000001`
- Delivery Note: `DN-000001`
- Stock In: `STI-000001`
- Stock Adjustment: `STA-000001`
- Stock Damage: `DMG-000001`
- Stock Expire: `EXP-000001`
- Sale Return: `SRT-000001`
- Purchase Return: `PRT-000001`
- Customer: `CUS-000001`
- Supplier: `SUP-000001`
- Customer Debt Payment: `CDP-000001`
- Supplier Debt Payment: `SDP-000001`

Fields:

- id
- document_type
- prefix
- next_number
- number_length
- reset_type
- status

Sequence generation must be transaction-safe.

### Audit Log

Fields:

- id
- user_id
- action
- module
- entity_type
- entity_id
- old_values
- new_values
- ip_address
- user_agent
- created_at

Log important actions:

- login
- failed login where appropriate
- password reset
- role changes
- permission changes
- price changes
- stock adjustment
- stock damage
- stock expire
- sale
- return
- customer debt payment
- supplier debt payment
- settings changes

Audit logs must not be editable by normal users.

### Settings

Groups:

#### Shop
- Shop Name
- Logo
- Phone
- Email
- Address

#### Currency
- Currency Code
- Symbol
- Decimal Places

#### POS
- Default Customer
- Allow Discount
- Maximum Discount
- Allow Negative Stock
- Receipt Footer

#### Stock
- Low Stock Level
- Track Expiry
- Expiry Alert 1 (lead time before expiry, e.g. 3 months / 90 days)
- Expiry Alert 2 (second lead time before expiry, e.g. 1 week / 7 days)
- Enable Telegram Expiry Alerts

#### Telegram
- Telegram Bot Token (env/secrets; UI may show masked status only)
- Enable Password Reset by Telegram
- Verification Code Expiry
- Max Verification Attempts
- Enable Stock Inquiry Bot (view-only)
- Default inquiry chat recipients (users with verified Telegram Chat ID), or broadcast rules for linked staff users

#### Invoice
- Shop Logo (local image for on-screen Settings / optional print header mark — invoices still do not print the shop name as the document title)
- Shop Information
- Footer
- Paper Size
- Auto Print (opens the browser print dialog after sale; does not generate a PDF file)

#### System
- Language
- Date Format
- Timezone

---

## 2.2 Non-Functional Requirements

### Security

- Hash passwords with Argon2id or bcrypt.
- Never store plain passwords.
- Use secure HTTP-only cookies or secure access token strategy.
- Protect all backend routes with authorization.
- Server-side permission checks are mandatory.
- Frontend permission hiding alone is not enough.
- Rate-limit login and password reset endpoints.
- Verification codes must be hashed or securely stored.
- Telegram bot token must come from environment/secrets.
- Prevent IDOR by scoping resource access.
- Validate all input server-side.

### Data Integrity

- Use database transactions for:
  - POS sale
  - stock in
  - stock adjustment
  - damage
  - expiry
  - debt payment
  - supplier debt payment
  - document sequence generation
- Never allow partial stock updates.
- Never modify current stock without a movement record.

### Performance

Target:

- Common page load under 2 seconds on normal LAN/internet.
- POS search should feel instant.
- Barcode lookup should be indexed.
- Use pagination for large tables.
- Use server-side filtering for reports.
- Avoid loading all records at once.

### Auditability

Critical business changes must be traceable.

### Responsiveness

Desktop-first.

Must support:
- desktop
- laptop
- tablet

POS should still be usable on a tablet.

Mobile support can be simplified.

---

# 3. Technology Stack

## 3.1 Architecture

Use a **modular monolith**.

Do not use microservices.

Recommended architecture:

- Frontend: Nuxt
- Backend API: FastAPI
- Database: PostgreSQL
- Cache: Redis
- Reverse Proxy: Nginx or Caddy
- Deployment: Docker Compose

One repository is preferred.

---

## 3.2 Frontend

### Core

- Nuxt 3 / current stable Nuxt
- Vue 3
- TypeScript
- Nuxt UI
- Pinia only if global client state is truly needed
- VueUse where helpful
- Zod for client-side schema sharing/validation where appropriate

### UI Components

Use Nuxt UI components where possible:

- `UApp`
- `UContainer`
- `UCard`
- `UButton`
- `UInput`
- `UTextarea`
- `USelect`
- `USelectMenu`
- `UTable`
- `UBadge`
- `UModal`
- `UDrawer`
- `UDropdownMenu`
- `UTabs`
- `UPagination`
- `UForm`
- `UFormField`
- `UCheckbox`
- `USwitch`
- `UAlert`
- `UToast`
- `UBreadcrumb`
- `UNavigationMenu`
- `USkeleton`
- `UIcon`

Prefer Nuxt UI over custom components unless required.

### Reusable Frontend Architecture

Follow the reusable architecture already proven in the existing frontend, but replace all rental-specific domain code with Stock & POS concepts.

Use these layers:

- thin Nuxt route pages
- configuration-driven standard modules
- reusable layout, table, document, form, filter, export, and feedback components
- focused business components for Stock, POS, debts, dashboard, reports, and settings
- composables for reusable UI/application behavior
- repository contracts with HTTP and mock adapters
- Pinia stores only for authentication, preferences, and genuinely shared application state
- shared domain types and pure utilities
- centralized English and Khmer localization files

Route pages should primarily:

- declare page metadata and permission requirements
- select the appropriate module configuration or specialized view
- pass route parameters to reusable components
- avoid duplicating tables, forms, filters, API calls, or permission logic

Standard CRUD-style areas should use one reusable module system where their behavior is genuinely shared:

- Categories
- Units of Measure (UOM)
- Brands
- Products
- Suppliers
- Customers
- Delivery Notes
- Users
- Roles
- Document Sequences
- Audit Logs

The reusable module configuration may define:

- path and API collection
- title, description, icon, and permission
- list columns
- form fields and validation metadata
- filters and select options
- document tabs
- related records
- row and document actions
- read-only/create/update behavior

Do not force unique transactional experiences into a generic CRUD abstraction. These should use dedicated business components while still reusing common controls, tables, dialogs, formatting, and API utilities:

- Dashboard
- Stock In
- Stock Adjustment
- Stock Damage
- Stock Expiry
- POS cart and checkout
- Sale Return (customer)
- Purchase Return (supplier)
- Customer Debt Payment
- Supplier Debt Payment
- Reports
- Settings

Keep reusable components domain-neutral. Names such as `AppListTable`, `AppDocumentPage`, `AppDocumentForm`, `AppFilterMenu`, and `AppConfirmDialog` are preferred over duplicated feature-specific copies. A component should become domain-specific only when it owns real Stock & POS business behavior.

Repository usage must be replaceable:

- components and pages depend on repository contracts, not raw fetch calls
- the HTTP adapter uses `/api/v1`
- a mock adapter may support frontend development and tests
- response-envelope parsing, authentication refresh, query serialization, pagination, and API errors stay centralized

English and Khmer translation keys must stay synchronized. Do not hard-code user-facing labels in reusable components when the surrounding UI uses localization.

### Charts

Use:
- ECharts, or
- ApexCharts, or
- Chart.js

Recommended: **ECharts** for dashboard and reports.

Dashboard must have one line chart with two series:
- Income
- Expense

Dashboard chart container must auto-fit available height on all devices (flex fill + autoresize). Do not lock the chart to a fixed desktop-only pixel height.
---

## 3.3 Backend

Recommended:

- Python 3.12+
- FastAPI
- SQLAlchemy 2.x
- Pydantic 2
- Alembic
- PostgreSQL driver: psycopg
- Redis
- HTTPX for Telegram API
- Local disk for product/shop/brand images (`LOCAL_STORAGE_DIR`). Do not add S3, MinIO, or cloud object storage.
- Do **not** add Celery beat or a Docker scheduler service. Daily jobs run in the FastAPI process (`app.core.scheduler`).
- Argon2 / Passlib or maintained password hashing library
- PyJWT or equivalent if token auth is used

Backend must use the feature-based modular-monolith structure shown in the approved reference image:

```text
app/
├── core/
├── modules/
│   ├── auth/
│   ├── dashboard/
│   ├── categories/
│   ├── uoms/
│   ├── brands/
│   ├── stock/
│   ├── suppliers/
│   ├── pos/
│   ├── customers/
│   ├── delivery_notes/
│   ├── reports/
│   └── administration/
├── shared/
└── api/v1/
```

Each business module is self-contained. Do not create repository-wide `models/`, `schemas/`, `repositories/`, or `services/` directories. A module owns its SQLAlchemy models, Pydantic schemas, repository, service, router, permissions, and internal helpers.

Example module:

```text
modules/categories/
├── __init__.py
├── models.py
├── schemas.py
├── repository.py
├── service.py
├── router.py
└── permissions.py
```

Module responsibilities:

- `models.py`: SQLAlchemy persistence mappings, relationships, constraints, and indexes owned by the module.
- `schemas.py`: Pydantic create, update, response, filter, and operation contracts.
- `repository.py`: SQLAlchemy queries, pagination, filtering, row locks, persistence, and `flush`; never commits.
- `service.py`: business rules, orchestration, transaction boundaries, and calls to shared services.
- `router.py`: thin FastAPI endpoints, dependency declarations, request/response mapping, and status codes.
- `permissions.py`: permission constants used by the module and administration seed data.
- additional files are allowed only for a real module need, such as `pricing.py`, `calculations.py`, or `selectors.py`.

Repository-wide responsibilities:

- `core/`: configuration, database, Redis, security primitives, base exceptions, logging, local image storage, and application infrastructure.
- `shared/`: cross-module capabilities such as audit, document sequences, Telegram, pagination, money, dates, storage, and response envelopes.
- `api/v1/`: API composition only. Its root router imports and registers each module router under `/api/v1`.
- `tasks/`: leftover Celery modules may exist for an optional queue profile; they are **not** required. Daily expiry scans use `core/scheduler.py` inside the API process.
- `tests/`: mirrors the feature-module structure and contains shared fixtures.

Modules may depend on `core/` and `shared/`. Avoid circular imports between business modules. Cross-module workflows must be coordinated by one clearly owning module service through small public interfaces.

Thin API routers must not:

- calculate stock, totals, profit, debt, or change
- update SQLAlchemy models directly
- allocate document numbers
- call `commit()`
- duplicate permission or error-handling behavior

Services own transaction completion. Repositories may `flush()` so generated identifiers are available, but the service commits once after every required database change succeeds. On failure, the entire operation rolls back.

All `/api/v1` success responses use a consistent envelope:

```json
{
  "data": {},
  "meta": {}
}
```

`meta` may be omitted or empty for single-record responses. List responses include pagination metadata. Errors use the centralized error handler and one stable error shape.

The complete required feature-module tree and module-by-module delivery order are defined in sections 8.2 and 8.3.

---

## 3.4 Database

Use PostgreSQL.

Reasons:

- strong relational integrity
- good transactions
- row locking for document sequences
- JSONB for audit values/settings where useful
- excellent indexing
- production reliability

---

## 3.5 Redis

Use Redis for:

- forgot-password verification code state
- rate limiting
- short-lived cache
- optional session support
- optional dashboard cache
- Celery result backend

Do not use Redis as source of truth for stock, money, images, or files. Do not store invoice PDFs anywhere.

---

## 3.6 Telegram Integration

Use Telegram Bot API. Bot token and client secrets stay server-side only (Compose env / secrets). Never expose the bot token to the frontend.

### Approved Telegram use cases (Stock & POS only)

1. **Password-reset verification codes** (existing)
   - Hashed, short-lived, single-use, attempt-limited, rate-limited.
2. **Product expiry alerts (two configurable windows)**
   - Settings define two lead times before `expiry_date` (examples: Alert 1 = 3 months, Alert 2 = 1 week).
   - A scheduled job **inside the FastAPI API process** (`app.core.scheduler`) scans expiry-tracked stock/batches and notifies linked staff users when a product/batch enters Alert 1 and again when it enters Alert 2. Do not run Celery beat or a Docker scheduler container.
   - Each alert level fires at most once per product/batch per level (track `expiry_alert_1_sent_at` / `expiry_alert_2_sent_at` or equivalent) to avoid spam.
   - Message includes product name, SKU/barcode, batch if any, expiry date, remaining qty, and which alert level fired.
3. **View-only stock inquiry bot (keyboard flow)**
   - Linked/verified users may query information through Telegram reply keyboards / inline keyboards.
   - **Read-only:** no create, edit, delete, stock mutation, sale, payment, or settings change via Telegram.
   - Typical flow:
     1. `/start` or **Menu** → tools keyboard
     2. User selects a tool (e.g. Current Stock Summary, Low Stock, Expiring Soon, Sales Summary)
     3. User selects a period when required (Today, Last 7 days, This month, Custom range if implemented later)
     4. Bot replies with a compact text result (paginated if long)
   - Unauthorized or unlinked Telegram users receive a link/verify instruction only — no business data.

### Explicitly forbidden via Telegram

- Any write/mutation: stock in/adjust/damage/expire, POS sale, debt payment create, master-data CRUD, user/role changes
- Sending invoices, invoice PDFs, or payment/invoice text notifications
- Rental/motorcycle legacy bot workflows
- Exposing secrets, tokens, or raw database dumps

### Runtime shape (Docker Compose)

- Default: Telegram reset-code send and expiry scans run **inside the API process** (no extra containers).
- Optional later: `telegram-bot` Compose profile for view-only inquiry polling (`backend/Dockerfile.telegram`).
- Do not require RabbitMQ or Celery workers for Telegram.

### Required environment variables

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_ENABLED=true
TELEGRAM_BOT_MODE=polling
TELEGRAM_BOT_CLIENT_ID=stock-pos-telegram-bot
TELEGRAM_BOT_CLIENT_SECRET=CHANGE_ME
PASSWORD_RESET_CODE_EXPIRY_SECONDS=300
PASSWORD_RESET_MAX_ATTEMPTS=5
```

Settings-stored alert lead times (examples; persisted in app settings, not secrets):

```text
stock.expiry_alert_1_days = 90   # e.g. 3 months
stock.expiry_alert_2_days = 7    # e.g. 1 week
telegram.expiry_alerts_enabled = true
telegram.stock_inquiry_enabled = true
```

Do not persist `telegram.payment_invoice_notify_enabled`. Do not expose Telegram bot token in frontend code.

### 3.6.1 View-only inquiry keyboard UX

```text
/start or Menu
   |
   +-- [Current Stock]
   +-- [Low Stock]
   +-- [Expiring Soon]
   +-- [Sales Summary]
   +-- [Help]
         |
         v
   Period keyboard (when needed)
   +-- [Today]
   +-- [Last 7 days]
   +-- [This month]
         |
         v
   Text result (paginated / Next page if long)
```

Result formatting rules:

- Compact monospace-friendly lines; include product name, qty, UOM, expiry when relevant.
- Cap message length; offer “Next” / page buttons rather than dumping huge lists.
- Sales Summary: period totals (invoice count, gross sales, paid, debt) — no line-item edit.
- Expiring Soon: respect Alert 1 / Alert 2 settings windows for filtering.
- Every handler is read-only; refuse any callback that would mutate data.

### 3.6.2 Payment / invoice Telegram — forbidden

Do **not** send invoice text, payment summaries, or invoice files through Telegram after POS sales or debt payments. Invoices are print-only in the web UI.

---

## 3.7 Local image storage

Images are files on the API host. Default directory: `var/media` (Docker: `/srv/data/media` volume `mediadata`).

PostgreSQL stores object keys only (`image_object_key`, `logo_object_key`). The API streams files at `GET /api/v1/images/{object_key}`. Max upload size 5 MB. jpeg/png/webp/gif only.

Do **not** use S3, MinIO, R2, or Google Drive. Do **not** store invoice PDFs or report exports on disk (print HTML / HTTP CSV).

The bundled UI logo remains `frontend/app/assets/images/logo.png`.

---

## 3.8 Background jobs

Daily expiry-alert scans and similar maintenance run **in the FastAPI process** (`app.core.scheduler`). Do not add a Docker scheduler or Celery beat service.

RabbitMQ and Celery workers are optional Compose profiles and must stay off in the default lean stack. They must never generate invoice PDFs, store exports in MinIO, or write stock/money outside the canonical services.

Detailed Compose service list: `docs/DOCKER_INFRASTRUCTURE.md`.

---

# 4. Database Design

## 4.1 Database Principles

- PostgreSQL
- UUID primary keys recommended
- timestamps in UTC
- display local time using configured timezone
- numeric money fields use `NUMERIC`, never float
- foreign keys required
- indexes on search/filter fields
- soft delete only where appropriate
- audit critical actions

Recommended money type:

`NUMERIC(18, 2)`

Recommended quantity type:

`NUMERIC(18, 4)`

---

## 4.2 Core Tables

### users

```text
id UUID PK
full_name VARCHAR
email VARCHAR UNIQUE NOT NULL
password_hash VARCHAR NOT NULL
telegram_chat_id VARCHAR NULL
telegram_verified BOOLEAN DEFAULT FALSE
status VARCHAR
last_login_at TIMESTAMP NULL
created_at TIMESTAMP
updated_at TIMESTAMP
```

### roles

```text
id UUID PK
name VARCHAR UNIQUE
description TEXT NULL
is_system BOOLEAN DEFAULT FALSE
status VARCHAR
created_at TIMESTAMP
updated_at TIMESTAMP
```

### permissions

```text
id UUID PK
code VARCHAR UNIQUE
module VARCHAR
action VARCHAR
description TEXT NULL
```

### user_roles

Use if multiple roles per user are desired.

```text
user_id UUID FK users
role_id UUID FK roles
PRIMARY KEY (user_id, role_id)
```

If only one role per user is desired, role_id may live directly on users.

Preferred: many-to-many for flexibility.

### role_permissions

```text
role_id UUID FK roles
permission_id UUID FK permissions
PRIMARY KEY (role_id, permission_id)
```

---

### categories

```text
id UUID PK
code VARCHAR UNIQUE NOT NULL
name VARCHAR NOT NULL
description TEXT NULL
status VARCHAR NOT NULL
created_at TIMESTAMP
updated_at TIMESTAMP
```

---

### units_of_measure

```text
id UUID PK
code VARCHAR UNIQUE NOT NULL
name VARCHAR NOT NULL
symbol VARCHAR NOT NULL
description TEXT NULL
status VARCHAR NOT NULL
created_at TIMESTAMP
updated_at TIMESTAMP
```

---

### brands

```text
id UUID PK
code VARCHAR UNIQUE NOT NULL
name VARCHAR NOT NULL
description TEXT NULL
logo_object_key VARCHAR NULL
status VARCHAR NOT NULL
created_at TIMESTAMP
updated_at TIMESTAMP
```

---

### products

```text
id UUID PK
sku VARCHAR UNIQUE NOT NULL
barcode VARCHAR UNIQUE NULL
name VARCHAR NOT NULL
category_id UUID FK categories
uom_id UUID FK units_of_measure NOT NULL
brand_id UUID FK brands NULL
cost_price NUMERIC(18,2) DEFAULT 0
selling_price NUMERIC(18,2) NOT NULL
minimum_stock NUMERIC(18,4) DEFAULT 0
expiry_tracking BOOLEAN DEFAULT FALSE
image_object_key VARCHAR NULL
status VARCHAR NOT NULL
note TEXT NULL
created_at TIMESTAMP
updated_at TIMESTAMP
```

`image_object_key` points to the local file for the product image. The binary file is not stored in PostgreSQL.
`uom_id` is required. Product quantity and selling price are expressed in this UOM.
`brand_id` is optional.
`uom_conversions` (JSONB, optional) stores product **Pricing** rows: `{ uom_id, uom_symbol, convert_uom_id, convert_uom_symbol, factor_to_base NUMERIC > 0, sale_price NUMERIC, is_default_sale BOOLEAN, cost_price NUMERIC NULL optional }`. UI tab name is **Pricing**. **Original UOM** = `uom_id` (POS selectable). **Convert UOM** = usually product base `uom_id` from General. Exactly one row has `is_default_sale = true`. Stock and movements remain in the product base UOM (see §2.1.3). Legacy `use_on_pos` may map to always-true (all Pricing rows are POS-selectable).

Do not store current stock as the only source of truth.

Optionally maintain a materialized/current balance table for performance.

---

### product_sale_prices

Sale-price versions for a product. Exactly one row per product is POS-active.

```text
id UUID PK
product_id UUID FK products NOT NULL
sale_price NUMERIC(18,2) NOT NULL
effective_date DATE NOT NULL
is_active BOOLEAN NOT NULL DEFAULT FALSE
version INTEGER NOT NULL
created_by UUID FK users NULL
created_at TIMESTAMP
updated_at TIMESTAMP
UNIQUE (product_id, version)
```

Rules:

- `sale_price` > 0
- At most one `is_active = TRUE` per `product_id`
- Activating a version copies `sale_price` onto `products.selling_price`
- Adding a version assigns `version = MAX(version)+1` for that product (first version = 1)
- Cost history is **not** stored here — cost versions come from Stock In (`stock_transaction_items.unit_cost`)

---

### suppliers

```text
id UUID PK
code VARCHAR UNIQUE NOT NULL
name VARCHAR NOT NULL
company_name VARCHAR NULL
phone VARCHAR NULL
location TEXT NULL
note TEXT NULL
status VARCHAR NOT NULL
created_at TIMESTAMP
updated_at TIMESTAMP
```

---

### customers

```text
id UUID PK
code VARCHAR UNIQUE NOT NULL
name VARCHAR NOT NULL
phone VARCHAR NULL
location TEXT NULL
note TEXT NULL
status VARCHAR NOT NULL
is_walk_in BOOLEAN DEFAULT FALSE
created_at TIMESTAMP
updated_at TIMESTAMP
```

Seed one system customer:

`Walk-in Customer`

---

### stock_transactions

Use one transaction header for stock operations where practical.

```text
id UUID PK
document_no VARCHAR UNIQUE NOT NULL
transaction_type VARCHAR NOT NULL
supplier_id UUID NULL FK suppliers
transaction_date TIMESTAMP NOT NULL
reference_no VARCHAR NULL
note TEXT NULL
status VARCHAR NOT NULL
created_by UUID FK users
confirmed_by UUID NULL FK users
created_at TIMESTAMP
updated_at TIMESTAMP
```

transaction_type:

- STOCK_IN
- ADJUSTMENT
- DAMAGE
- EXPIRE

---

### stock_transaction_items

```text
id UUID PK
stock_transaction_id UUID FK stock_transactions
product_id UUID FK products
quantity NUMERIC(18,4) NOT NULL
unit_cost NUMERIC(18,2) NOT NULL
system_quantity NUMERIC(18,4) NULL
actual_quantity NUMERIC(18,4) NULL
batch_no VARCHAR NULL
expiry_date DATE NULL
reason TEXT NULL
line_total NUMERIC(18,2) NOT NULL
created_at TIMESTAMP
```

---

### stock_movements

This is critical.

```text
id UUID PK
product_id UUID FK products
movement_type VARCHAR NOT NULL
quantity_delta NUMERIC(18,4) NOT NULL
unit_cost NUMERIC(18,2) NOT NULL
reference_type VARCHAR NOT NULL
reference_id UUID NOT NULL
document_no VARCHAR NULL
batch_no VARCHAR NULL
expiry_date DATE NULL
note TEXT NULL
created_by UUID FK users
created_at TIMESTAMP
```

movement_type:

- STOCK_IN
- SALE
- SALE_RETURN
- PURCHASE_RETURN
- ADJUSTMENT_IN
- ADJUSTMENT_OUT
- DAMAGE
- EXPIRE

Rules:

- every stock change creates a movement
- movement records are append-only
- never silently rewrite history

---

### purchase_returns

Supplier returns against a confirmed Stock In / purchase. No standalone `/returns` page.

```text
id UUID PK
return_no VARCHAR UNIQUE NOT NULL
stock_transaction_id UUID FK stock_transactions
supplier_id UUID FK suppliers
return_date TIMESTAMP NOT NULL
refund_amount NUMERIC(18,2) NOT NULL
reason TEXT NOT NULL
created_by UUID FK users
created_at TIMESTAMP
```

### purchase_return_items

```text
id UUID PK
purchase_return_id UUID FK purchase_returns
stock_transaction_item_id UUID FK stock_transaction_items
product_id UUID FK products
quantity NUMERIC(18,4) NOT NULL
unit_cost NUMERIC(18,2) NOT NULL
line_refund NUMERIC(18,2) NOT NULL
created_at TIMESTAMP
```

Rules: quantity > 0; cumulative returned qty per stock-in line ≤ original received qty; stock out uses base UOM after any line UOM conversion.

### stock_balances

Performance helper.

```text
product_id UUID PK FK products
quantity NUMERIC(18,4) NOT NULL DEFAULT 0
average_cost NUMERIC(18,2) NOT NULL DEFAULT 0
updated_at TIMESTAMP
```

This table must be updated in the same DB transaction as stock movement creation.

---

### sales

```text
id UUID PK
invoice_no VARCHAR UNIQUE NOT NULL
customer_id UUID FK customers
sale_date TIMESTAMP NOT NULL
subtotal NUMERIC(18,2) NOT NULL
discount_amount NUMERIC(18,2) NOT NULL DEFAULT 0
grand_total NUMERIC(18,2) NOT NULL
paid_amount NUMERIC(18,2) NOT NULL DEFAULT 0
debt_amount NUMERIC(18,2) NOT NULL DEFAULT 0
payment_status VARCHAR NOT NULL
sale_status VARCHAR NOT NULL
cashier_id UUID FK users
note TEXT NULL
created_at TIMESTAMP
```

Sales do not store an invoice PDF object key. Printing is frontend HTML only.

payment_status:

- PAID
- PARTIAL
- UNPAID

sale_status:

- COMPLETED
- PARTIAL_RETURN
- RETURNED
- CANCELLED

---

### sale_items

Store historical price/cost snapshots.

```text
id UUID PK
sale_id UUID FK sales
product_id UUID FK products
product_name VARCHAR NOT NULL
sku VARCHAR NOT NULL
barcode VARCHAR NULL
quantity NUMERIC(18,4) NOT NULL
unit_price NUMERIC(18,2) NOT NULL
unit_cost NUMERIC(18,2) NOT NULL
discount_amount NUMERIC(18,2) NOT NULL DEFAULT 0
line_total NUMERIC(18,2) NOT NULL
returned_quantity NUMERIC(18,4) NOT NULL DEFAULT 0
created_at TIMESTAMP
```

---

### delivery_notes

Fulfillment document for delivering sold products to a customer. Does not mutate stock. May link **one or more** POS invoices for the same customer.

```text
id UUID PK
delivery_no VARCHAR UNIQUE NOT NULL
customer_id UUID FK customers NOT NULL
delivery_phone VARCHAR NOT NULL
delivery_location TEXT NOT NULL
delivered_at TIMESTAMP NULL
status VARCHAR NOT NULL
note TEXT NULL
created_by UUID FK users
created_at TIMESTAMP
updated_at TIMESTAMP
```

### delivery_note_sales

```text
id UUID PK
delivery_note_id UUID FK delivery_notes
sale_id UUID FK sales NOT NULL
invoice_no VARCHAR NOT NULL
created_at TIMESTAMP
UNIQUE (delivery_note_id, sale_id)
```

### delivery_note_items

```text
id UUID PK
delivery_note_id UUID FK delivery_notes
sale_id UUID FK sales NOT NULL
sale_item_id UUID FK sale_items NOT NULL
product_id UUID FK products
product_name VARCHAR NOT NULL
uom_symbol VARCHAR NULL
qty_ordered NUMERIC(18,4) NOT NULL
qty_to_deliver NUMERIC(18,4) NOT NULL
qty_delivered NUMERIC(18,4) NOT NULL DEFAULT 0
created_at TIMESTAMP
```

Legacy single `sale_id` on `delivery_notes` (if present in older migrations) must be migrated to `delivery_note_sales`. Do not keep driver_name / vehicle_note / scheduled_date as required UI fields.

---

### sale_returns

```text
id UUID PK
return_no VARCHAR UNIQUE NOT NULL
sale_id UUID FK sales
return_date TIMESTAMP NOT NULL
refund_amount NUMERIC(18,2) NOT NULL
reason TEXT NOT NULL
created_by UUID FK users
created_at TIMESTAMP
```

### sale_return_items

```text
id UUID PK
sale_return_id UUID FK sale_returns
sale_item_id UUID FK sale_items
product_id UUID FK products
quantity NUMERIC(18,4) NOT NULL
refund_amount NUMERIC(18,2) NOT NULL
restock BOOLEAN NOT NULL
created_at TIMESTAMP
```

---

### payments

```text
id UUID PK
payment_no VARCHAR UNIQUE NOT NULL
sale_id UUID NULL FK sales
customer_id UUID NULL FK customers
supplier_id UUID NULL FK suppliers
payment_type VARCHAR NOT NULL
payment_method VARCHAR NOT NULL
amount NUMERIC(18,2) NOT NULL
reference_no VARCHAR NULL
note TEXT NULL
created_by UUID FK users
created_at TIMESTAMP
```

payment_type:

- SALE_PAYMENT
- CUSTOMER_DEBT_PAYMENT
- SUPPLIER_DEBT_PAYMENT

---

### customer_debts

```text
id UUID PK
customer_id UUID FK customers
sale_id UUID FK sales
invoice_no VARCHAR NOT NULL
original_amount NUMERIC(18,2) NOT NULL
paid_amount NUMERIC(18,2) NOT NULL DEFAULT 0
remaining_amount NUMERIC(18,2) NOT NULL
due_date DATE NULL
status VARCHAR NOT NULL
created_at TIMESTAMP
updated_at TIMESTAMP
```

---

### supplier_debts

Created from stock-in/purchase transactions when not fully paid.

```text
id UUID PK
supplier_id UUID FK suppliers
stock_transaction_id UUID FK stock_transactions
document_no VARCHAR NOT NULL
original_amount NUMERIC(18,2) NOT NULL
paid_amount NUMERIC(18,2) NOT NULL DEFAULT 0
remaining_amount NUMERIC(18,2) NOT NULL
due_date DATE NULL
status VARCHAR NOT NULL
created_at TIMESTAMP
updated_at TIMESTAMP
```

---

### document_sequences

```text
id UUID PK
document_type VARCHAR UNIQUE NOT NULL
prefix VARCHAR NOT NULL
next_number BIGINT NOT NULL
number_length INT NOT NULL DEFAULT 6
reset_type VARCHAR NULL
status VARCHAR NOT NULL
updated_at TIMESTAMP
```

Sequence generation must lock the row during increment.

---

### audit_logs

```text
id UUID PK
user_id UUID NULL FK users
action VARCHAR NOT NULL
module VARCHAR NOT NULL
entity_type VARCHAR NULL
entity_id UUID NULL
old_values JSONB NULL
new_values JSONB NULL
ip_address VARCHAR NULL
user_agent TEXT NULL
created_at TIMESTAMP NOT NULL
```

---

### telegram_expiry_alert_state

Tracks that an expiry alert level was already sent for a product lot so the scheduler does not spam.

```text
id UUID PK
product_id UUID FK products NOT NULL
batch_no VARCHAR NULL
expiry_date DATE NOT NULL
alert_level SMALLINT NOT NULL   -- 1 = first window (e.g. 90 days), 2 = second window (e.g. 7 days)
sent_at TIMESTAMP NOT NULL
UNIQUE (product_id, batch_no, expiry_date, alert_level)
```

Rules:

- In-process API scheduler (daily, UTC hour from settings) compares remaining days until `expiry_date` against Settings Alert 1 / Alert 2 day counts.
- When days remaining <= alert_N_days and no row exists for that level, send Telegram and insert this row.
- Only products with `expiry_tracking = true` and remaining quantity > 0 participate.
- Alert 2 may fire after Alert 1; each level is independent once-per-lot.

---

### system_settings

Prefer key/value grouped settings.

Required Stock / Telegram keys (examples):

```text
stock.low_stock_level
stock.expiry_alert_1_days          -- e.g. 90
stock.expiry_alert_2_days          -- e.g. 7
telegram.expiry_alerts_enabled
telegram.stock_inquiry_enabled
telegram.password_reset_enabled
```

```text
id UUID PK
group_name VARCHAR NOT NULL
key VARCHAR UNIQUE NOT NULL
value JSONB NOT NULL
is_secret BOOLEAN DEFAULT FALSE
updated_by UUID NULL FK users
updated_at TIMESTAMP
```

Secret values should be encrypted or stored in environment/secrets when appropriate.

Telegram bot token should preferably remain in environment variables.

---

### password_reset_codes

Optional persistent table if not using Redis-only flow.

```text
id UUID PK
user_id UUID FK users
code_hash VARCHAR NOT NULL
expires_at TIMESTAMP NOT NULL
attempt_count INT NOT NULL DEFAULT 0
used_at TIMESTAMP NULL
created_at TIMESTAMP NOT NULL
```

Redis is preferred for the active temporary code state.

---

## 4.3 Important Indexes

Add indexes for:

- users.email
- products.sku
- products.barcode
- products.name
- products.category_id
- products.uom_id
- products.brand_id
- units_of_measure.code
- brands.code
- brands.name
- suppliers.name
- customers.name
- customers.phone
- sales.invoice_no
- sales.sale_date
- sales.customer_id
- delivery_notes.delivery_no
- delivery_notes.customer_id
- delivery_notes.status
- delivery_note_sales.delivery_note_id
- delivery_note_sales.sale_id
- delivery_note_sales.invoice_no
- delivery_note_items.delivery_note_id
- stock_movements.product_id
- stock_movements.created_at
- customer_debts.customer_id
- customer_debts.status
- supplier_debts.supplier_id
- supplier_debts.status
- audit_logs.created_at
- audit_logs.user_id

---

## 4.4 Transaction Rules

### POS Sale Transaction

Single database transaction:

1. lock required stock balances
2. validate availability
3. generate invoice sequence
4. create sale
5. create sale items
6. create payment/debt
7. create stock movements
8. update stock balances
9. commit

If any step fails -> rollback everything.

### Stock In Transaction

1. validate product/supplier
2. generate document no
3. create stock transaction
4. create items
5. create stock movements
6. update stock balances
7. create supplier debt if needed (and payment record if paid_amount > 0)
8. commit

### Sale Return Transaction

1. lock sale / items; validate returnable qty
2. generate return_no
3. create sale_returns + items
4. restock via stock mutation when requested (`SALE_RETURN`)
5. apply refund / reduce customer debt
6. audit; commit or rollback

### Purchase Return Transaction (return to supplier)

1. lock stock-in / items and stock balances; validate returnable qty and available stock
2. generate return_no
3. create purchase_returns + items
4. stock out via stock mutation (`PURCHASE_RETURN`)
5. reduce supplier debt / record supplier credit for that document
6. audit; commit or rollback

### Debt Payment Transaction

1. lock debt row (by `debtId`)
2. validate payment <= remaining for that document
3. create payment record
4. update paid / remaining on that debt
5. update status
6. commit

Frontend: Debt Report row **Pay** modal only (customer or supplier); pass `debtId` so the selected document is settled first.

---

# 5. UI Design

## 5.1 Design Direction

Use **Nuxt UI** and create a style inspired by ERPNext.

Do not copy ERPNext branding.

Design principles:

- white / light gray backgrounds
- small radius
- subtle borders
- restrained shadows
- compact spacing
- clear typography
- strong data tables
- simple form layouts
- left sidebar
- sticky shared top header (`AppHeader`) for title and actions
- actions aligned consistently in the top header
- breadcrumbs for document/sub-pages (in the top header, not a separate page chrome block)
- responsive but desktop-focused
- avoid flashy gradients
- avoid giant cards
- avoid excessive rounded "mobile app" styling

---

## 5.2 Layout

Desktop layout:

```text
┌─────────────────────────────────────────────────────┐
│ Sidebar │ Sticky Top Header (title + page actions)  │
│         ├───────────────────────────────────────────┤
│ Dash…   │ Main Content                              │
│ Cat…    │                                           │
│ Stock   │                                           │
│ Supp…   │                                           │
│ POS     │                                           │
│ Cust…   │                                           │
│ Reports │                                           │
│ Admin   │                                           │
└─────────┴───────────────────────────────────────────┘
```

Sidebar:
- compact width
- icons + labels
- expandable only for Reports and Administration
- active page highlight
- no unnecessary nested menus

---

## 5.3 Page Header Pattern

Do **not** render a separate in-page header block with title + short description + action row.

Use the shared sticky top header already in the default layout:

- `AppHeader.vue` — `UDashboardNavbar` chrome (title / breadcrumbs / actions)
- `useAppHeader()` — page sets title, breadcrumbs, badges, and action config
- `AppHeaderPageActions.vue` — registers list/document actions into that header

### Left (title area)

- List/workspace pages: single page title from `definePageMeta({ titleKey })` or `setTitle()`
- Document/detail pages: `UBreadcrumb` via `setBreadcrumbs()` (last crumb is the display title)
- Optional status `UBadge` items beside breadcrumbs (`setBadges()`)
- Mobile: compact home › … › current title trail
- No short description line under the title

### Right (actions area, left → right)

1. Document list navigation (optional): List · Previous · Next
2. Page-specific trailing controls (teleport slot — e.g. POS **Next**, immediately left of Refresh)
3. Refresh (default on when actions are registered)
4. More menu `⋯` (`UDropdownMenu`) — Export and other secondary actions
5. Meta-rail toggle (document detail, optional)
6. Cancel / Save (create/edit document modes)
7. Primary create action(s) — opt-in solid button; only pages that can create set `canCreate`

Filters and search stay in the main content toolbar / table chrome, not in the top header description row.

### Examples

List page:

```text
[☰] Stock                                      [↻] [⋯] [+ Add Product]
```

Document page:

```text
[☰] Stock › Widget A  [Open]     [List] [‹] [›] [↻] [⋯] [Cancel] [Save]
```

Implementation rules:

- Prefer Nuxt UI primitives already used by the header (`UDashboardNavbar`, `UBreadcrumb`, `UBadge`, `UButton`, `UDropdownMenu`)
- Create is opt-in; do not show a create button on every page
- Export belongs in the more menu, not as a always-visible secondary header button beside create
- Keep page content starting directly under the sticky header (tables, forms, POS workspace)

---

## 5.4 Table Style

ERPNext-like business table:

- compact rows
- sticky header for long tables
- subtle row hover
- checkbox selection only when bulk actions exist
- status badges
- actions in row dropdown
- pagination
- server-side search/filter
- no giant action buttons in every row

Recommended row action menu:

- View
- Edit
- Stock In
- Adjustment
- Damage
- Expire
- History

Use `UDropdownMenu`.

---

## 5.5 Dashboard UI

### Summary Row (KPI)

Exactly **4** cards in **one row** on desktop (`lg:grid-cols-4`). Never five.

1. Today Sales
2. Income
3. Expense
4. Outstanding Debt

Remove “Sales This Month” from the KPI row (keep that metric in Business Summary instead).

Card design:

- compact
- metric title
- main number
- optional small icon
- optional small comparison / hint text
- no large illustrations

### Chart + Business Summary Row

Below cards, one row on desktop (~70% / ~30%):

Left:
- Income vs Expense line chart (exactly 2 series)
- Date-range controls in the card header
- Chart area uses **auto-fit height** (flex fill of remaining viewport / parent; `autoresize`; no fixed `h-72`-style trap). Works on all device widths.

Right — title **Business Summary**:
- Complete system metric list per section 2.1.1 (sales/money, debts, stock health, operations)
- Dense label/value rows; scroll inside the panel if the list is long rather than shrinking the chart awkwardly
- Do not duplicate only the four KPI values; Business Summary must be broader

On mobile/tablet, stack vertically (chart then Business Summary); chart still auto-fits available height.

---

## 5.6 Categories UI

Setup sub-page at `/setup/categories`.

Components:

- page header
- search input
- status filter
- category table
- add/edit modal or drawer

Use:
- `UInput`
- `USelect`
- `UTable`
- `UModal` or `UDrawer`
- `UForm`

---

## 5.7 Units of Measure UI

Setup sub-page at `/setup/uoms`. Same compact master-data pattern as Categories.

Components:

- page header
- search input
- status filter
- UOM table (code, name, symbol, status, actions)
- add/edit modal or drawer

Product forms must select UOM from active UOM records (not free text).

---

## 5.8 Brands UI

Setup sub-page at `/setup/brands`. Same compact master-data pattern as Categories / UOM.

Components:

- page header
- search input
- status filter
- brand table (code, name, status, actions; optional logo thumbnail)
- add/edit modal or drawer

Product forms may select Brand from active brand records.

---

## 5.9 Stock UI

Main Stock page is the product list (and product create/edit). Do **not** add a Stock History tab on the product document or as a Stock page section.

Quantity history opens only from Stock list cells (Stock In / Stock Out / Damage) as a short dialog. Do not make stock operations sidebar pages.

Product list table columns must include a leading **Image** thumbnail column for every product row:

- small square thumbnail (e.g. 40×40 or 48×48)
- rounded corners
- object-cover crop
- placeholder icon when `image_object_key` / `imageUrl` is empty
- do not block the row click/actions if the image fails to load

Product list must also show quantity summary columns:

- Stock In
- Stock Out
- Current Stock
- Damage Stock

**Stock In**, **Stock Out**, and **Damage Stock** cells are clickable and open a history dialog for that product (filtered by movement kind).

**Current Stock** is a plain number (tabular-nums). Not clickable. No dialog.

**Dialog chrome (Stock In / Stock Out / Damage):**

- Width ≈ **70% of viewport** on desktop.
- Body: `TableAppListTable` from `frontend/app/components/table` (search + optional date range + pagination). Not a raw HTML table. Not `AppLineTable`.
- Give the dialog body a real height (flex / ~55–65vh) so `AppListTable` can fill (`min-h-0`, `flex-1`).
- Close action in footer; no edit/delete of movements from this dialog.
- **Stock In / Damage dialogs:** toolbar **Add Stock In** / **Add Damage** opens a nested form dialog on top of history (product locked; see §2.1.5). After a successful save, refresh the history table and Stock list aggregates. **Stock Out** has no Add.

**Cost Price** and **Sale Price** cells are clickable (same wide-dialog + `TableAppListTable` pattern):

- Cost dialog: Stock In lots — Date, Product name, Cost price, Qty, Amount, Version. Read-only.
- Sale Price dialog: versions — Checkbox (POS-active, exactly one), Date, Product name, Sale price. **Add Sale Price** in the dialog. POS uses the checked price.

Place **Expire Date** immediately before **Status** on the product table:

- nearest lot expiry date (from stock movements / stock-in lots)
- show `—` when blank
- read-only on the list (set via Stock In)

On Product table row actions:

- Stock In
- Adjustment
- Damage
- Expire
- View History

Use modal/drawer forms.

Product form — exactly **three** tabs:

- **General** — identity and master fields only: name, image, category, brand, barcode, required base UOM (`uom_id`), supplier, **cost price**, current stock (read-only), status. Do **not** put Sale Price, Track Expiry, or Expire Date on General (those move to Pricing / Expire). Do not keep the old Pricing/Stock field groups on General.
- **Pricing** — editable table (see §2.1.3). Columns **only**: **No**, **Original UOM**, **Convert UOM**, **Conversion qty**, **Sale price**, **Default sale** (exactly one checked), delete icon. **Add row** on the toolbar. Saved with the product (same Save as General). No Cost column. No separate Convert UOM tab.
- **Expire** — Track Expiry checkbox; Expire Date read-only (nearest lot expiry from Stock In; blank when not tracked or no expiry set). Helper text: set expiry on Stock In, not edited here. Saved with the product.

Do not keep a separate **Convert UOM** tab — Pricing owns pack UOM + sale prices.

Stock movement history table:

- Date
- Document No.
- Product
- Movement Type
- Qty In
- Qty Out
- UOM
- Unit Cost
- User
- Reference

---

## 5.10 Suppliers UI

Setup sub-page at `/setup/suppliers`.

Main supplier table:

- Code
- Name
- Phone
- Location
- Debt
- Status
- Actions

Supplier create/edit is master data only (name, phone, location, status). Outstanding Debt appears on the **list table only** as a read-only total from unpaid/partial Stock In — do **not** show or edit it on the create/edit document. Do **not** put purchase history, payment history, KPI cards, or Record Payment on `/setup/suppliers/:id`. Search and filter purchases and supplier debts on **Purchase Report** and **Supplier Debt Report**.

Supplier Debt Report columns must include:

1. **Date**
2. **Invoice No.** / Purchase No. (document number)
3. Total / Paid / Remaining / Status (as applicable)

Row **Actions (`...`) → Pay** records a payment against that open/partial document (modal only). Do not show a debt ledger without Date and document/Invoice No.
---

## 5.11 POS UI

POS should be the fastest page.

Desktop two-step flow:

**Step 1 — Sell (products + cart)**

```text
┌────────────────────────────── (~70%) ──────────────┬──────── (~30%) ────────┐
│ Search / Barcode + Category chips                  │ Cart                   │
│ Product card grid                                  │ thumb · qty / unit $ / │
│  image · name · selling price · stock · add (+)    │ % discount · remove    │
│                                                    │ Next (no summary yet)  │
└────────────────────────────────────────────────────┴────────────────────────┘
```

Every POS product card must show the product image (or placeholder). Every cart line must show a small product thumbnail when available.

Product images on POS use the same product image source as Stock (`imageUrl` / local object key). Do not maintain a separate POS-only image field.

**Step 2 — Checkout (order summary + customer/payment; no AppHeader)**

```text
┌───────────────────────────────────────┬──────────────────────┐
│ Back to cart            [Delivery]    │ Name                 │
│ Order summary table                   │ Phone                │
│  N° · Product · Unit(UOM) · Qty ·     │ Location             │
│  Price · Discount · Amount            │ Outstanding Debt     │
│                                       │  (opens invoice table│
│                                       │   to include on this │
│                                       │   invoice)           │
│                                       │ Subtotal / Discount  │
│                                       │ Delivery price       │
│                                       │ Deposit total        │
│                                       │ Paid now             │
│                                       │ Outstanding amount   │
│                                       │ Submit               │
└───────────────────────────────────────┴──────────────────────┘
```

Outstanding Debt is a selection control. Clicking it opens a wide `TableAppListTable` dialog of that customer's open invoices:

- Checkbox (include this debt on the current invoice)
- Date
- Invoice No
- Paid
- Debt
- Payment method

Payment totals:

- Subtotal
- Discount
- Delivery price (only when Delivery is checked) and Deposit total
- Paid now
- Outstanding amount (`sale net + delivery fee + deposit − paid now`)

Checkout hides the sticky AppHeader. **Back to cart** returns to step 1. Walk-in customers cannot leave an outstanding balance.

After a successful sale, do **not** open an invoice preview dialog. Auto-print the bilingual invoice (Khmer/English) through a standalone print document so the preview is not blank. The OS/browser print dialog still appears (websites cannot silent-print). After Submit, show a small paper-size chooser (A4 default / A5, `CommonAppDialog` size `sm`); picking a size prints the invoice in that `@page` size through the hidden-iframe print document; closing/cancel skips printing (the sale is already saved). Never generate or store a PDF.

The invoice print document includes:

- Centered underlined title វិក្កយបត្រ / INVOICE only (do not print shop name as the document title)
- Khmer-first fonts (Noto Sans Khmer); wait for `document.fonts.ready` before calling print
- Bold, larger meta: Invoice no + Date (left); Customer + Cashier (right)
- Line table headers stacked Khmer then English, all center-aligned; **0.5px** cell borders; compact Product / Unit / Qty widths
- Empty filler rows so the grid fills ~70% printable height (short sales must still fit on one page)
- Summary aligned to Price+Discount | Amount columns; borders left/right/bottom only (no top): Total, Delivery, Deposit/paid, outstanding; Buyer / Seller signature lines

If Delivery was checked, open Create Delivery Note after the paper-size dialog is resolved (printed or cancelled), with that invoice **auto-selected** and phone/location defaulted.

Search input must autofocus where appropriate.

Barcode scanner:
- exact barcode -> add immediately

Cart (step 1):
- compact rows with product thumbnail when available
- **UOM select per line** — options = every Pricing row **Original UOM** for that product. On add-to-cart use **Default sale** row. Changing UOM updates sale price + remaining stock from that Pricing row (per-product only).
- changing UOM sets unit price to that UOM's sale price; qty is in the selected UOM; remaining stock shown in the selected UOM (`base ÷ factor`)
- quantity controls
- editable unit price
- per-line discount %
- remove
- no payment summary yet — **Next** lives in the sticky AppHeader (right), not in the cart footer

Checkout (step 2):
- no AppHeader; Back to cart (soft) and a Delivery checkbox on the order-summary toolbar
- customer Name / Phone / Location / Outstanding Debt and payment in one panel
- Outstanding Debt opens a dialog to include open invoices on this sale
- Subtotal, Discount, Delivery price (when Delivery is checked), Deposit total, Paid now, Outstanding amount
- Checking Delivery includes delivery price in the sale and opens Create Delivery Note after auto-print (invoice preselected)
- Cash / Bank-QR / Customer Debt payment
- Submit (centers on the payment button; completes the sale, then shows the A4/A5 print chooser — no invoice preview dialog)

Debt option disabled for Walk-in Customer.
Cart and invoice lines must show the **selected** UOM symbol/name. Completing the sale stocks out `qty × factor_to_base` in the base UOM (oversell blocked against base stock unless `allow_negative_stock`). Factor for the base UOM is always `1`.
After sale completion, offer an optional action to **Create Delivery Note** when the customer needs product delivery (opens Delivery Notes create flow with that invoice preselected; user may multi-select additional invoices for the same customer).

#### POS chrome (full-width workspace)

While `/pos` is open:

- Hide the left sidebar so the sell/checkout layout can use the full width.
- Replace the header sidebar-collapse control with a **Back** button that returns to the previous in-app page (Dashboard `/` if there is no previous app page). Do not leave POS via a hidden nav only.
- Keep the sticky `AppHeader` on the cart step with **Back** (soft button, no page title), **Next** immediately left of Refresh, then Refresh. Put a compact user menu on the header right so profile/logout remain available without the sidebar. Hide `AppHeader` on the checkout step.

Leaving POS restores the normal sidebar + header collapse control.

---

## 5.12 Customers UI

Setup sub-page at `/setup/customers`.

Customer table:

- Code
- Name
- Phone
- Location
- Debt
- Status
- Actions

Customer create/edit is master data only (name, phone, location, status). Outstanding Debt appears on the **list table only** as a read-only total from unpaid/partial POS sales — do **not** show or edit it on the create/edit document. Do **not** put purchase history, payment history, delivery notes, KPI cards, or Record Payment on `/setup/customers/:id`. Search and filter sales, debts, and deliveries on **Sales Report**, **Customer Debt Report**, and **Delivery Notes**.

Customer Debt Report columns must include:

1. **Date**
2. **Invoice No.**
3. Totals / paid / remaining / status as applicable

Row **Actions (`...`) → Pay** records a payment against that open/partial invoice debt (modal only). Do not omit Date or Invoice No. from customer debt tables.
---

## 5.13 Delivery Notes UI

Main page for delivery tracking of products sold to clients.

### List (`/delivery-notes`)

Use `TableAppListTable` / `AppListTable` from `frontend/app/components/table`.

List table columns:

- Delivery No
- Date
- Invoice No(s) (comma-separated when multiple)
- Customer
- Phone
- Location
- Status
- Items count
- Actions

Filters / toolbar:

- status
- date range
- customer
- search (delivery no / invoice no / customer / phone)

Row / toolbar actions:

- **Update Status** — opens allowed next statuses only (see §2.1.9 transition table); permission-gated; audit on change. Prefer a clear **Update Status** button (list row action and/or bulk-safe single-row control), not a hidden-only menu.
- **Delivery OK** — shortcut to Delivered when transition is allowed
- **Print** (HTML)
- Cancel (reason required) when allowed

Nested `/delivery-notes/:id` is optional — list actions are enough.

### Create / Add (`/delivery-notes/new` or equivalent drawer)

Two entry points:

1. **Auto from POS** — after sale with Delivery checked (or “Create Delivery Note”), navigate/open create with that `saleId` / invoice already selected and phone/location defaulted from the sale/customer.
2. **Add** from Delivery Notes page — blank create; user multi-selects invoices.

Create layout:

1. **Phone** and **Location** inputs (required before Confirm/Deliver; default from selected customer; user may edit for this delivery only).
2. **Invoice selection on the table** (not a separate detached picker outside the table UX):
   - Body uses `TableAppListTable` / `AppListTable`.
   - Table toolbar includes **live search by Invoice No** (and customer name as secondary).
   - Rows are selectable (**multi-select** checkboxes) for confirmed sales that still have remaining deliverable qty.
   - Selecting rows **stores/adds** those invoices’ deliverable product lines into the delivery lines set shown in the same create flow (second table or expanded lines section also using `AppListTable` / line table pattern as appropriate).
   - All selected invoices must belong to the **same customer**; selecting an invoice for a different customer clears the previous selection or blocks with a clear error.
3. **Lines table** (selected invoices’ products): Invoice No, Product, UOM, Ordered, Already reserved, Remaining, Qty to deliver (editable). Uses shared table components under `frontend/app/components/table` where list/read patterns apply; editable qty may use the approved line-table pattern if needed.
4. Save as Draft or Confirm — auto-print bilingual delivery note (HTML only).

Do **not** add driver / vehicle / courier schedule forms. Phone + location are the only delivery-destination fields.

### Detail (optional)

- Status badge + **Update Status** + Delivery OK + Cancel + Print
- Phone / location editable while Draft (and Confirmed if product allows before Out for Delivery)
- Lines table read-only after Delivered
- Show linked invoice nos

Status path:

- Prefer **Update Status** with allowed transitions; **Delivery OK** remains a fast path to Delivered
- No stock mutation on any delivery status change

Do not add a separate courier microservice.

---

## 5.14 Reports UI

Use sidebar sub-pages.

Common report pattern:

Header:
- report title
- date filter
- filter button
- print (HTML / browser print) and HTTP CSV export (no MinIO artifact)

Summary metrics:
- compact cards

Main:
- server-side table

**Customer Debt Report** table must include **Date** and **Invoice No.** (invoice-level rows). See section 2.1.10 report columns.

**Supplier Debt Report** table must include **Date** and **Invoice No. / Purchase No.** (document-level rows). See section 2.1.10 report columns.

Do not render these two reports as party-only aggregate lists that omit Date and Invoice/document number. Party totals may appear as summary cards above the document table.

**Finance Report** (`/reports/finance`):

- Optional summary cards
- **Income & expense management table** (required) — no chart on this page
- **Add Expense** via modal/drawer (not a separate Expense page)
- AppHeader: title + breadcrumbs + Add Expense only — **no** header date filter, **no** header Refresh
- Date/search/type filters live on the **table toolbar**
- Not a general ledger; income rows come from sales; expenses are recorded here

Do not create full report editing forms for Sales/Purchase/Debt reports. Finance may use create/edit modals only for expenses as specified.

**Sales Report** (`/reports/sales`):

- Columns per §2.1.10, including trailing **Actions (`...`)** column.
- Row menu **Return** opens the customer-return modal against that sale (see §2.1.10 Customer return). Do not add `/returns`.

**Purchase Report** (`/reports/purchases`):

- Columns per §2.1.10, including trailing **Actions (`...`)** column.
- Row menu **Return** opens return-to-supplier modal against that Stock In / purchase (see §2.1.10 Return to supplier).
- Creating new purchases is **not** done on this report — use Stock list / Stock In history dialog **Add Stock In**.

**Customer Debt Report** / **Supplier Debt Report** UI:

- Row **Actions (`...`) → Pay** for open/partial debts (see §2.1.10). Payment modal only — not on Setup customer/supplier documents.

---

## 5.15 Administration UI

### Users

Table:
- Name
- Email
- Role
- Telegram Status
- Status
- Last Login
- Actions

### Roles & Permissions

Use grouped permission matrix.

Example:

```text
Stock
[✓] View
[✓] Stock In
[ ] Adjustment
[ ] Damage
[ ] Expire
```

Do not show hundreds of ungrouped checkboxes.

### Document Sequence

Table:
- Document Type
- Prefix
- Next Number
- Number Length
- Status

### Audit Log

Read-only table.

Filters:
- user
- module
- action
- date range

### Settings

Use grouped tabs/cards:

- Shop
- Currency
- POS
- Stock
- Telegram
- Invoice
- System

---

## 5.16 Validation UX

- show inline field errors
- disable submit while saving
- show toast after success
- confirm destructive actions
- never use browser alert()
- use Nuxt UI modal/alert components

---

## 5.17 Reusable Page Composition

Use the following composition model instead of rebuilding each page independently:

```text
Route Page
   |
   +-- Standard module? --> Module Configuration
   |                          |
   |                          +-- Workspace/List View
   |                          +-- Document View/Form
   |                          +-- Shared Table/Filters/Actions
   |
   +-- Transaction page? --> Dedicated Business View
                              |
                              +-- Shared Top Header (`AppHeader` / `AppHeaderPageActions`)
                              +-- Shared Inputs/Dialogs/Tables
                              +-- Domain Composables
                              +-- Repository Contract
```

### Standard List Pattern

Create one reusable list workspace supporting:

- page title in the shared top header (`useAppHeader` / `titleKey`)
- primary create action in the top header (opt-in via `AppHeaderPageActions`)
- search and server-side filters in the content toolbar
- compact table
- status badges
- row action dropdown
- pagination
- loading, empty, error, and permission-denied states
- export from the header more menu only where allowed

Feature configuration supplies the fields, columns, permissions, filters, and actions. It must not duplicate the workspace implementation.

### Standard Document Pattern

Create one reusable document shell supporting:

- create, view, and edit modes
- breadcrumbs and list navigation
- grouped form sections
- schema validation and inline errors
- save/cancel actions
- detail tabs and related records
- audit metadata where useful
- unsaved-change protection
- loading and not-found states

Use it for master and administration records when the field behavior fits. Use dedicated transactional drawers/modals for operations that require stock locking, totals, payment allocation, confirmation, or immutable history.

### Shared Component Rules

- Search existing shared components before creating a new feature component.
- Prefer props, slots, and typed configuration over copy/paste variants.
- Keep business calculations out of visual components.
- Keep HTTP calls out of low-level table, field, and dialog components.
- Do not build a universal component with feature-specific conditionals for every module.
- Split a shared component when its API becomes harder to understand than two focused components.
- Add component or utility tests for reusable behavior that affects multiple pages.

---

# 6. Deployment

## 6.1 Deployment Architecture

Recommended production deployment:

```text
Internet
   |
Nginx / Caddy
   |
   +---- Frontend (Nuxt)
   |
   +---- Backend (FastAPI)  -- in-process scheduler + Telegram reset send
            |
            +---- PostgreSQL
            |
            +---- Redis
```

Use Docker Compose.

Full service table, env examples, and exposure rules: `docs/DOCKER_INFRASTRUCTURE.md`.

---

## 6.2 Suggested Repository

```text
project/
├── frontend/
├── backend/
├── infrastructure/
│   ├── nginx/                 # host reverse-proxy configs
│   ├── scripts/               # install, start, deploy helpers
│   └── README.md
├── docker-compose.yml         # keep at repo root for CI / Compose
├── docker-compose.prod.yml
├── .env.example
├── .env.production.example
├── README.md
├── scripts/                   # thin wrappers → infrastructure/scripts/
└── docs/
    ├── stock_pos_ai_agent_project_spec.md
    ├── PAGE_ROUTE_MAP.md
    ├── IMPLEMENTATION_PLAN.md
    ├── DOCKER_INFRASTRUCTURE.md
    └── DO_NOT_USE.md
```

Service Dockerfiles and the frontend container nginx config stay under `frontend/` and `backend/` because they belong to those image build contexts. Host-level reverse-proxy files belong under `infrastructure/nginx/`.

---

## 6.3 Docker Services

Required Compose services:

```yaml
services:
  frontend:
  api:          # includes in-process expiry scheduler
  db:
  redis:
```

Optional Compose profiles (off by default): `queue` (RabbitMQ/Celery workers), `telegram` (inquiry bot). **No MinIO. No scheduler container.**

Optional:

- host reverse-proxy (Nginx / Caddy) documented under `infrastructure/nginx/`
- backup service
- database admin tool in development only

Production exposure:

- Do not expose PostgreSQL publicly.
- Do not expose Redis publicly.
- Do not expose RabbitMQ or its management UI publicly.
- Do not expose PostgreSQL or Redis publicly.
- Do not publish the API port publicly when a reverse proxy fronts `/api`.

---

## 6.4 Environment Variables

Example:

```env
# App
APP_ENV=production
APP_NAME=Stock POS
APP_URL=https://example.com
API_URL=https://example.com/api

# Database
POSTGRES_DB=stock_pos
POSTGRES_USER=stock_pos
POSTGRES_PASSWORD=CHANGE_ME
DATABASE_URL=postgresql+psycopg://stock_pos:CHANGE_ME@db:5432/stock_pos

# Redis
REDIS_URL=redis://redis:6379/0

# RabbitMQ / Celery
RABBITMQ_USER=stock_pos
RABBITMQ_PASSWORD=CHANGE_ME
RABBITMQ_VHOST=stock_pos
RABBITMQ_URL=amqp://stock_pos:CHANGE_ME@rabbitmq:5672/stock_pos
CELERY_BROKER_URL=amqp://stock_pos:CHANGE_ME@rabbitmq:5672/stock_pos
CELERY_RESULT_BACKEND=redis://redis:6379/2

# Security
SECRET_KEY=CHANGE_ME_LONG_RANDOM_SECRET
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Telegram
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=CHANGE_ME
TELEGRAM_BOT_MODE=polling
TELEGRAM_BOT_CLIENT_ID=stock-pos-telegram-bot
TELEGRAM_BOT_CLIENT_SECRET=CHANGE_ME
PASSWORD_RESET_CODE_EXPIRY_SECONDS=300
PASSWORD_RESET_MAX_ATTEMPTS=5

# Local image storage (no S3 / MinIO)
LOCAL_STORAGE_DIR=var/media
SCHEDULER_ENABLED=true
EXPIRY_ALERT_SCAN_HOUR=7

# Timezone
APP_TIMEZONE=Asia/Phnom_Penh
```

Never commit real secrets.

---

## 6.5 Development Setup

Development:

```bash
# Data plane only
docker compose up -d db redis

# Or full stack
docker compose up -d --build
```

Backend:

```bash
cd backend
uv sync
alembic upgrade head
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
pnpm install
pnpm dev
```

Adapt exact commands to the chosen package manager.

---

## 6.6 Production Build

Frontend:

```bash
pnpm install --frozen-lockfile
pnpm build
```

Backend:

- install locked dependencies
- run Alembic migrations
- start FastAPI with production ASGI server/process manager

Recommended container health checks:

- frontend HTTP health
- backend `/health`
- PostgreSQL readiness
- Redis ping

---

## 6.7 Database Migration

Use Alembic.

Rules:

- every schema change requires a migration
- never manually edit production DB schema
- migrations should be reviewed before production
- take backup before destructive migrations

---

## 6.8 Backups

Minimum:

- PostgreSQL daily backup
- keep at least 7 daily backups
- keep selected weekly/monthly backups if needed
- test restore procedure

Backup should include:

- database

Do not rely only on Docker volumes as backup. Redis is cache/reset-code state and is not the backup source of truth.

---

## 6.9 HTTPS

Production must use HTTPS.

Recommended:
- Caddy automatic TLS, or
- Nginx + Let's Encrypt

Secure cookies must be enabled under HTTPS.

---

## 6.10 Logging

Backend:
- structured logs
- request ID
- error logs
- important security events

Do not log:
- passwords
- reset codes
- Telegram bot token
- secrets

---

## 6.11 Monitoring

Minimum production checks:

- backend health
- frontend health
- database availability
- Redis availability
- disk space
- backup success

---

# 7. Required API Structure for This Repository

All new Stock & POS endpoints use this base:

```text
/api/v1
```

Authentication:

```text
POST /auth/setup
POST /auth/login
POST /auth/logout
POST /auth/forgot-password
POST /auth/verify-reset-code
POST /auth/reset-password
GET  /auth/me
```

Dashboard:

```text
GET /dashboard/summary
GET /dashboard/income-expense
GET /dashboard/recent-sales
GET /dashboard/recent-stock
```

Categories:

```text
GET    /categories
POST   /categories
GET    /categories/{id}
PATCH  /categories/{id}
DELETE /categories/{id}
```

Units of Measure:

```text
GET    /uoms
POST   /uoms
GET    /uoms/{id}
PATCH  /uoms/{id}
DELETE /uoms/{id}
```

Brands:

```text
GET    /brands
POST   /brands
GET    /brands/{id}
PATCH  /brands/{id}
DELETE /brands/{id}
```

Stock / Products:

```text
GET    /products
POST   /products
GET    /products/{id}
PATCH  /products/{id}
DELETE /products/{id}

POST /stock/in
POST /stock/adjust
POST /stock/damage
POST /stock/expire
POST /stock/in/{id}/return

GET /stock/movements
GET /stock/products/{id}/history
GET /stock/products/{id}/cost-history
GET /products/{id}/sale-prices
POST /products/{id}/sale-prices
POST /products/{id}/sale-prices/{price_id}/activate
```

Suppliers:

```text
GET    /suppliers
POST   /suppliers
GET    /suppliers/{id}
PATCH  /suppliers/{id}
DELETE /suppliers/{id}

GET  /suppliers/{id}/history
GET  /suppliers/{id}/debts
POST /suppliers/{id}/debts/{debt_id}/payments
```

POS:

```text
GET  /pos/products/search
GET  /pos/products/barcode/{barcode}
POST /pos/sales
POST /pos/sales/{id}/return
GET  /pos/sales/{id}/receipt
POST /pos/sales/{id}/delivery-notes
```

`GET /pos/sales/{id}/receipt` returns JSON for frontend HTML print. Do **not** add `GET /pos/sales/{id}/invoice.pdf`.

Images / files:

```text
POST /images/upload
GET  /images/{object_key}
```

Object keys for product images and shop/brand logos are stored on product/settings/brand records. Binary image files live on local disk. Invoice PDFs are not stored.

Customers:

```text
GET    /customers
POST   /customers
GET    /customers/{id}
PATCH  /customers/{id}
DELETE /customers/{id}

GET  /customers/{id}/history
GET  /customers/{id}/debts
GET  /customers/{id}/delivery-notes
POST /customers/{id}/debts/{debt_id}/payments
```

Delivery Notes:

```text
GET    /delivery-notes
POST   /delivery-notes
GET    /delivery-notes/{id}
PATCH  /delivery-notes/{id}
POST   /delivery-notes/{id}/status
POST   /delivery-notes/{id}/confirm
POST   /delivery-notes/{id}/out-for-delivery
POST   /delivery-notes/{id}/deliver
POST   /delivery-notes/{id}/cancel
GET    /delivery-notes/{id}/print
GET    /delivery-notes/deliverable-invoices
GET    /sales/{sale_id}/deliverable-items
```

`POST /delivery-notes/{id}/status` body `{ "status": "<next>", "cancel_reason"?: "..." }` enforces the §2.1.9 transition table (Update Status). Dedicated confirm/out-for-delivery/deliver/cancel endpoints may remain as aliases of the same transition service.

`GET /delivery-notes/deliverable-invoices` supports create-page invoice search + multi-select (query: search, customer_id, date filters). Returns confirmed sales with remaining deliverable qty.

Reports:

```text
GET  /reports/sales
GET  /reports/purchases
GET  /reports/customer-debts
GET  /reports/supplier-debts
GET  /reports/finance
GET  /reports/finance/entries
POST /reports/finance/expenses
```

Finance `entries` returns combined income (from sales) and expense rows for the table. `POST .../expenses` creates an operating expense (no `/expenses` page). Alternative ownership under `/api/v1/expenses` is allowed only as an API path — never as a frontend sidebar page.
Administration:

```text
GET    /admin/users
POST   /admin/users
PATCH  /admin/users/{id}
POST   /admin/users/{id}/reset-password

GET    /admin/roles
POST   /admin/roles
PATCH  /admin/roles/{id}

GET /admin/permissions

GET   /admin/document-sequences
PATCH /admin/document-sequences/{id}

GET /admin/audit-logs

GET   /admin/settings
PATCH /admin/settings
```

---

# 8. Required Application Folder Structures

## 8.1 Frontend Folder Structure

```text
frontend/
├── app/
│   ├── app.vue
│   ├── app.config.ts
│   ├── assets/
│   │   └── css/
│   │       ├── main.css
│   │       └── scrollbar.css
│   ├── components/
│   │   ├── common/
│   │   │   ├── AppConfirmDialog.vue
│   │   │   ├── AppDateRangeFilter.vue
│   │   │   ├── AppExportDialog.vue
│   │   │   ├── AppFilterMenu.vue
│   │   │   ├── AppLiveSearch.vue
│   │   │   └── AppSecretInput.vue
│   │   ├── layout/
│   │   │   ├── AppHeader.vue
│   │   │   ├── AppHeaderPageActions.vue
│   │   │   ├── AppSidebar.vue
│   │   │   └── UserMenu.vue
│   │   ├── table/
│   │   │   ├── AppListTable.vue
│   │   │   ├── AppLineTable.vue
│   │   │   └── AppRelatedRecords.vue
│   │   ├── document/
│   │   │   ├── AppDocumentPage.vue
│   │   │   ├── AppDocumentForm.vue
│   │   │   ├── AppDocumentTabBar.vue
│   │   │   └── AppDynamicFieldRenderer.vue
│   │   ├── module/
│   │   │   ├── WorkspaceView.vue
│   │   │   ├── ModulePage.vue
│   │   │   └── DocumentView.vue
│   │   ├── dashboard/
│   │   │   ├── AppEChart.vue
│   │   │   ├── AppKpiSection.vue
│   │   │   └── DashboardView.vue
│   │   ├── stock/
│   │   │   ├── StockInModal.vue
│   │   │   ├── StockAdjustmentModal.vue
│   │   │   ├── StockDamageModal.vue
│   │   │   ├── StockExpiryModal.vue
│   │   │   └── StockHistoryTable.vue
│   │   ├── suppliers/
│   │   ├── pos/
│   │   │   ├── PosProductBrowser.vue
│   │   │   ├── PosCart.vue
│   │   │   ├── PosPaymentModal.vue
│   │   │   └── PosReceipt.vue
│   │   ├── customers/
│   │   ├── debts/
│   │   ├── reports/
│   │   └── settings/
│   ├── composables/
│   │   ├── auth/
│   │   ├── common/
│   │   ├── layout/
│   │   ├── module/
│   │   ├── search/
│   │   ├── stock/
│   │   ├── pos/
│   │   └── settings/
│   ├── config/
│   │   ├── modules.ts
│   │   ├── master-data-modules.ts
│   │   ├── administration-modules.ts
│   │   ├── shared-options.ts
│   │   ├── pos-options.ts
│   │   └── settings-schemas.ts
│   ├── layouts/
│   │   ├── default.vue
│   │   └── auth.vue
│   ├── middleware/
│   │   ├── auth.global.ts
│   │   └── permission.ts
│   ├── mocks/
│   │   ├── seed.ts
│   │   └── query.ts
│   ├── pages/
│   │   ├── index.vue
│   │   ├── stock/
│   │   │   ├── index.vue
│   │   │   ├── new.vue
│   │   │   └── [id].vue
│   │   ├── pos.vue
│   │   ├── delivery-notes/
│   │   │   ├── index.vue
│   │   │   ├── new.vue
│   │   │   └── [id].vue
│   │   ├── setup/
│   │   │   ├── categories/
│   │   │   │   ├── index.vue
│   │   │   │   ├── new.vue
│   │   │   │   └── [id].vue
│   │   │   ├── uoms/
│   │   │   │   ├── index.vue
│   │   │   │   ├── new.vue
│   │   │   │   └── [id].vue
│   │   │   ├── brands/
│   │   │   │   ├── index.vue
│   │   │   │   ├── new.vue
│   │   │   │   └── [id].vue
│   │   │   ├── suppliers/
│   │   │   │   ├── index.vue
│   │   │   │   ├── new.vue
│   │   │   │   └── [id].vue
│   │   │   └── customers/
│   │   │       ├── index.vue
│   │   │       ├── new.vue
│   │   │       └── [id].vue
│   │   ├── reports/
│   │   │   ├── sales.vue
│   │   │   ├── purchases.vue
│   │   │   ├── customer-debts.vue
│   │   │   ├── supplier-debts.vue
│   │   │   └── finance.vue
│   │   ├── administration/
│   │   │   ├── users/
│   │   │   ├── roles/
│   │   │   ├── document-sequences/
│   │   │   ├── audit-logs/
│   │   │   └── settings/
│   │   └── auth/
│   │       ├── setup.vue
│   │       ├── login.vue
│   │       ├── forgot-password.vue
│   │       ├── verify-code.vue
│   │       └── reset-password.vue
│   ├── plugins/
│   │   └── auth-hydrate.client.ts
│   ├── repositories/
│   │   ├── index.ts
│   │   ├── contracts/
│   │   │   ├── entities.ts
│   │   │   ├── transactions.ts
│   │   │   └── settings.ts
│   │   ├── http/
│   │   │   ├── entities.ts
│   │   │   ├── transactions.ts
│   │   │   ├── settings.ts
│   │   │   └── response.ts
│   │   └── mock/
│   ├── stores/
│   │   ├── auth.ts
│   │   ├── preferences.ts
│   │   └── pos.ts
│   ├── types/
│   │   ├── api.ts
│   │   ├── auth-user.ts
│   │   ├── page-meta.d.ts
│   │   └── stock-pos/
│   │       ├── common.ts
│   │       ├── domain.ts
│   │       ├── entities.ts
│   │       ├── transactions.ts
│   │       ├── reports.ts
│   │       ├── search.ts
│   │       └── settings.ts
│   └── utils/
│       ├── api/
│       ├── auth/
│       ├── constants/
│       ├── export/
│       ├── filter/
│       ├── format/
│       ├── module/
│       ├── security/
│       ├── stock/
│       └── table/
├── i18n/
│   └── locales/
│       ├── en.json
│       └── km.json
├── tests/
│   ├── module-pages.spec.ts
│   ├── list-table.spec.ts
│   ├── repositories.spec.ts
│   ├── stock-transactions.spec.ts
│   ├── pos-cart.spec.ts
│   ├── permissions.spec.ts
│   └── localization-config.spec.ts
├── nuxt.config.ts
├── package.json
├── vitest.config.ts
└── tsconfig.json
```

The tree shows architectural ownership, not a requirement to create empty folders. Create a folder or file only when the implemented feature needs it.

### Folder Responsibilities

- `pages/`: route adapters only; keep them small.
- `components/common/`, `layout/`, `table/`, and `document/`: reusable domain-neutral UI.
- `components/module/`: configuration-driven list and document composition.
- feature component folders: business-specific interactive flows.
- `config/`: typed module schemas, fields, columns, options, and settings schemas; no network calls.
- `composables/`: reusable application behavior and component orchestration.
- `repositories/contracts/`: interfaces consumed by pages/composables.
- `repositories/http/`: `/api/v1` implementations and response normalization.
- `repositories/mock/` and `mocks/`: development/test adapters only; never production truth.
- `stores/`: small shared state; do not mirror all server records in Pinia.
- `types/stock-pos/`: Stock & POS domain and transport types; never import legacy-domain types.
- `utils/`: pure helpers without component state.
- `tests/`: reusable component, utility, repository-contract, permission, and business-behavior tests.

### Reuse Acceptance Criteria

- Categories, Units of Measure, Brands, Products, Suppliers, Customers, Delivery Notes, Users, Roles, Sequences, and Audit Logs share list/table/filter/pagination infrastructure.
- Master-data create/edit pages share the document shell and field renderer where appropriate.
- Stock operations share form controls and stock transaction helpers but keep separate schemas and business validation.
- Customer and supplier debt payments share visual payment primitives without combining their backend domain services.
- All five reports share filter, summary, table, print, loading, and export primitives.
- No route page duplicates HTTP request, pagination, formatting, permission, or error-handling code already provided by a composable/repository/utility.
- Shared component behavior has focused tests.

## 8.2 Backend Folder Structure

Use feature modules exactly as shown in the approved backend structure. Each folder under `app/modules/` is one independently understandable business module.

```text
backend/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── seed.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── redis.py
│   │   ├── security.py
│   │   ├── exceptions.py
│   │   ├── logging.py
│   │   └── storage.py
│   ├── modules/
│   │   ├── auth/
│   │   ├── dashboard/
│   │   ├── categories/
│   │   ├── uoms/
│   │   ├── brands/
│   │   ├── stock/
│   │   ├── suppliers/
│   │   ├── pos/
│   │   ├── customers/
│   │   ├── delivery_notes/
│   │   ├── reports/
│   │   └── administration/
│   ├── shared/
│   │   ├── audit/
│   │   ├── documents/
│   │   ├── telegram/
│   │   ├── pagination/
│   │   ├── money.py
│   │   ├── dates.py
│   │   └── responses.py
│   ├── api/
│   │   ├── deps.py
│   │   └── v1/
│   │       └── router.py
│   └── tasks/
│       ├── celery_app.py
│       ├── telegram.py
│       └── maintenance.py
├── alembic/
│   ├── env.py
│   └── versions/
├── tests/
│   ├── conftest.py
│   ├── modules/
│   ├── shared/
│   └── api/
├── alembic.ini
├── Dockerfile
├── pytest.ini
├── pyproject.toml
└── requirements.lock
```

The tree defines ownership, not a requirement to create empty placeholder files. Add a file when its module begins implementation.

Every business module normally uses this internal structure:

```text
module_name/
├── __init__.py
├── models.py
├── schemas.py
├── repository.py
├── service.py
├── router.py
└── permissions.py
```

Read-only modules such as Dashboard and Reports may omit `models.py`. A complex module may add focused files such as `calculations.py`, `returns.py`, or `invoice.py`; it must not create another repository-wide layer.

### Module Ownership

| Module | Owns |
|---|---|
| `auth` | Login, logout, access/refresh tokens, initial setup, password reset codes, authentication security |
| `dashboard` | Dashboard query schemas, aggregation repository, summary service, dashboard router |
| `categories` | Category model and CRUD rules |
| `uoms` | Unit of Measure model and CRUD rules; active UOM list for product forms |
| `brands` | Brand model and CRUD rules; optional brand list for product forms |
| `stock` | Products, batches, balances, stock transactions, stock movements, Stock In mutation, purchase return, adjustment, damage, expiry |
| `suppliers` | Supplier master data, supplier purchase history, supplier debts, supplier debt payments |
| `pos` | Sales, sale items, sale payments, sale returns, checkout, receipts/invoices; may start a delivery note from a sale |
| `customers` | Customer master data, purchase history access, customer debts, customer debt payments |
| `delivery_notes` | Delivery note headers/lines, status workflow, deliverable-qty rules, print view (no stock mutation) |
| `reports` | Sales, purchase, customer debt, supplier debt, and finance read models/queries |
| `administration` | Users, roles, permissions, settings APIs, document-sequence administration, audit-log access |

Shared code must not become a miscellaneous dumping ground:

- `shared/audit/` owns immutable audit persistence and write helpers.
- `shared/documents/` owns transaction-safe sequences and shared invoice document infrastructure.
- `shared/telegram/` owns the Telegram API client and delivery primitives.
- `shared/pagination/` owns list request/response contracts and SQLAlchemy pagination helpers.
- `shared/money.py`, `shared/dates.py`, and `shared/responses.py` contain small cross-module primitives only.

### Feature Module Rules

- `main.py` creates the FastAPI application, lifespan, middleware, exception handlers, and root router registration.
- `api/deps.py` centralizes database/Redis dependencies, authenticated users, permission guards, and shared HTTP dependencies.
- `api/v1/router.py` imports and registers each module's `router.py`; it contains no business endpoints.
- A module router imports its own schemas/service plus approved `core` or `shared` dependencies.
- A module service coordinates its repository and owns commits/rollbacks. A service method represents one complete use case.
- A module repository never contains permission decisions, HTTP exceptions, presentation formatting, or commits.
- Module models use explicit foreign keys, relationships, uniqueness rules, check constraints, and indexes from section 4.
- Module schemas separate create, update, filter, operation, and response models.
- `Decimal` is mandatory across schemas, services, repositories, and models for money and quantity values.
- All stock changes call `modules/stock/service.py`; no other module writes stock balances directly.
- Number allocation calls `shared/documents/service.py`; no module calculates the next number from row count.
- Audit creation calls `shared/audit/service.py`.
- Telegram calls use `shared/telegram/client.py`, HTTPX, and backend-only secrets (reset-code send is in-process).
- MinIO is **not used**. Images are local disk. Never store invoice PDFs or export files in object storage.
- Daily expiry scans use `core/scheduler.py` inside the API process. Do not add Celery beat or a Docker scheduler.
- A dedicated Telegram bot Compose service is **optional** (inquiry polling only). Password-reset and expiry alerts do not need it. No payment/invoice notify. No create/edit/delete via Telegram.
- A module may expose a small public interface from `__init__.py`; never import another module's repository directly.

### Backend Test Placement

- `tests/modules/<module>/`: router, service, repository, permission, transaction, and module-specific unit tests.
- `tests/shared/`: audit, sequences, pagination, money, Telegram, storage, and date tests.
- `tests/api/`: root routing, health, envelope, authentication dependency, and cross-module contracts.
- `tests/conftest.py`: isolated database fixtures, authenticated users, role fixtures, and Redis fakes/test instances.

Do not place all backend tests in one file. Tests mirror the owning feature module.

## 8.3 Module-by-Module Backend Delivery

Build one complete vertical module at a time. Do not create every model first, every router second, and every service last.

For each module, complete this slice before starting the next module:

```text
1. Read the module's specification and dependencies
2. Add or update SQLAlchemy model(s)
3. Add Alembic migration
4. Add Pydantic schemas
5. Add repository queries and locks
6. Add service business rules and transaction boundary
7. Add permission codes and audit events
8. Add the module `router.py` and register it in `api/v1/router.py`
9. Add seed/reference data only when required
10. Add service and API tests
11. Run focused tests and migration verification
12. Connect the matching frontend repository contract
```

A module is not complete when only CRUD endpoints exist. It is complete when persistence, validation, permissions, transaction behavior, auditability, API contracts, tests, and its frontend contract agree.

### Required Delivery Order

#### Stage 0 — Shared Foundation

Build or adapt only the reusable base:

- configuration
- database session and SQLAlchemy base
- Redis client
- local image storage directory bootstrap
- Celery app + RabbitMQ broker configuration
- centralized errors and response envelope
- pagination/filter/sort helpers
- security/password/JWT utilities
- permission dependency
- decimal money helpers
- UTC/date helpers
- logging and request ID
- health endpoints
- isolated test fixtures

Remove assumptions tied to motorcycles, rentals, rental pricing, or `/api/v2`. Keep the lean stack (API, PostgreSQL, Redis). Do not require MinIO, RabbitMQ, Celery workers, or a Docker scheduler.

#### Stage 1 — Authentication and Initial Setup

Files primarily owned by this stage:

- `modules/auth/models.py`
- `modules/auth/schemas.py`
- `modules/auth/repository.py`
- `modules/auth/service.py`
- `modules/auth/router.py`
- `modules/auth/permissions.py`
- `shared/telegram/client.py`

Complete first-Administrator setup, login/logout/me, password hashing, reset-code storage, Telegram delivery, expiry, attempts, single use, rate limiting, and audit events.

#### Stage 2 — Roles, Permissions, Users, Audit, Settings, and Sequences

Build shared administration capabilities before business modules need them:

1. roles and permissions
2. users
3. audit logs
4. system settings
5. document sequences

Administration owns users, roles, permissions, settings, and their API endpoints. Shared audit and document-sequence persistence lives under `shared/audit/` and `shared/documents/` because every business module uses it. Sequence generation must use database locking and concurrency tests before any numbered transaction module uses it.

#### Stage 3 — Categories

Complete `modules/categories/` with category models, schemas, repository, service, router, permissions, tests, unique codes, inactive behavior, safe delete rules, audit calls, and the frontend category repository contract.

#### Stage 3b — Units of Measure (UOM)

Complete `modules/uoms/` with UOM models, schemas, repository, service, router, permissions, tests, unique codes, inactive behavior, safe delete rules, seed defaults, audit calls, and the frontend UOM repository/module contract. Product create/update must require an active `uom_id`.

#### Stage 3c — Brands

Complete `modules/brands/` with brand models, schemas, repository, service, router, permissions, tests, unique codes, inactive behavior, safe delete rules, optional logo object key, audit calls, and the frontend brand repository/module contract. Products may optionally set `brand_id`.

#### Stage 4 — Products and Stock Read Model

Complete the product and inventory read capabilities inside `modules/stock/`: products, unique SKU/barcode constraints, category, UOM, and brand relationships, product images, stock balances, Stock In/Out/Damage aggregates for list columns, minimum stock, expiry settings, search, barcode lookup indexes, and stock history reads (including short history dialog filters). Do not allow direct current-stock editing.

#### Stage 5 — Suppliers and Stock In

Complete `modules/suppliers/` first, then add Stock In orchestration through the public interface of `modules/stock/` and `shared/documents/`. Supplier debt and supplier debt-payment history are owned by the Suppliers module. Supplier debt created by unpaid/partially paid Stock In belongs in the same transaction. Frontend entry points: Stock row action **Stock In**, and Stock In history dialog **Add Stock In** (nested form, product locked) — same form and API. Damage history dialog **Add Damage** is a Stage 6 entry point using the same stock-operation path.

#### Stage 6 — Remaining Stock Operations

Implement in this order:

1. Stock Adjustment
2. Stock Damage
3. Stock Expiry

Every operation must lock affected inventory, create stock transaction/items/movements, update balances, write audit data, and roll back completely on failure.

#### Stage 7 — Customers

Complete `modules/customers/` with customer CRUD, search, status, safe delete behavior, permissions, audit, purchase-history contract, customer debt ownership, and debt-read contract. Customer debt creation waits for POS sales.

#### Stage 8 — POS Sales, Payments, and Customer Debt

Complete `modules/pos/` with barcode/name search first, then the complete POS sale transaction. POS owns sales, sale items, sale returns, sale payment records, JSON receipt/print payload, and checkout rules. It calls public Stock, Customers, Documents, and Audit interfaces. Sale, items, payment or customer debt, stock movements, balances, invoice sequence, and audit must commit once or roll back together. Do not generate or store invoice PDFs.

#### Stage 9 — Sale Returns and Purchase Returns

Implement **customer returns** against confirmed sales (`POST /pos/sales/{id}/return`) and **supplier returns** against confirmed Stock In (`POST /stock/in/{id}/return`). Cover returnable qty, refund/debt adjustment, stock restore (sale) or stock out (purchase), immutable return records, permissions, audit, and rollback tests.

UI entry points only — no standalone `/returns` page:

- Sales Report row **Actions (`...`) → Return**
- Purchase Report row **Actions (`...`) → Return**
- Optional: same return action from a sale/purchase detail drawer if present

#### Stage 9b — Delivery Notes

Complete `modules/delivery_notes/` with delivery note headers/lines, `delivery_note_sales` (multi-invoice same customer), `DN-` sequence, status workflow + Update Status transitions (Draft → Confirmed → Out for Delivery → Delivered / Cancelled), deliverable-qty validation, phone/location fields, permissions, audit, print view, POS auto-open create entry, and create UI with invoice search + multi-select on `AppListTable`. Delivery Notes must not mutate stock. No driver/vehicle form.

#### Stage 10 — Debt Payments

Implement customer debt payments in `modules/customers/` and supplier debt payments in `modules/suppliers/`. They may reuse shared money/payment validation helpers, but keep separate domain methods, immutable histories, overpayment rejection, locked balances, and transaction-safe status updates.

UI entry points only — no payment forms on Setup customer/supplier documents:

- Customer Debt Report row **Actions (`...`) → Pay** → payment modal (`ReportsDebtPaymentDialog`) → `payCustomerDebt` with `debtId`
- Supplier Debt Report row **Actions (`...`) → Pay** → same modal pattern → `paySupplierDebt` with `debtId`

#### Stage 11 — Dashboard and Reports

Complete `modules/dashboard/` and `modules/reports/` after transaction sources are reliable:

1. dashboard summary and Income/Expense series
2. sales report
3. purchase report
4. customer debt report
5. supplier debt report
6. finance report

Report queries derive values from authoritative transaction tables; they do not store duplicate report totals as source-of-truth data. Sales and Purchase report tables include an **Actions (`...`)** column that opens Return modals (customer / supplier) as specified in §2.1.10 — not separate report edit forms.

#### Stage 12 — Legacy Cleanup and Production Verification

- remove `/api/v2` registration
- remove motorcycle/rental/charge/expense models, schemas, repositories, services, routers, tests, seed data, and migrations/bootstrap assumptions
- replace rental Telegram workflows with Stock & POS Telegram behavior (password-reset, expiry alerts, view-only inquiry); keep the approved `telegram-bot` service and queues; do not implement payment/invoice Telegram notify
- keep local-disk product images and logos; do not store invoice PDFs or export files
- verify a clean Alembic upgrade on an empty database
- run the complete backend test suite
- run frontend contract tests
- validate Docker Compose and production configuration (lean stack; no MinIO)

### Per-Module Completion Gate

Before marking any stage complete, verify:

- only approved endpoints were added
- model constraints and indexes match the specification
- migration upgrade succeeds from the supported baseline
- permissions are enforced by the backend
- audit events are written for critical mutations
- service owns one atomic transaction
- repository does not commit
- API responses follow `{ data, meta }`
- validation and conflict errors use centralized error handling
- focused success, failure, permission, and rollback tests pass
- the matching frontend repository contract uses the same fields and paths

---

# 9. AI Agent Implementation Rules

The coding agent must follow these rules.

## 9.1 Scope

Do not add new modules without explicit instruction.

Do not add:

- ERP accounting
- payroll
- HR
- multi-company
- multi-warehouse
- supplier purchase order workflow
- procurement approval workflow
- CRM
- ecommerce
- microservices

unless requested later.

---

## 9.2 Code Quality

- TypeScript strict mode.
- Python type hints.
- Small focused functions.
- Clear module boundaries.
- Avoid circular imports.
- Avoid business logic in route handlers.
- Use service/application layer.
- Repository/database code separate from domain logic.
- Central error handling.
- Central permission checks.
- No duplicated stock logic.

---

## 9.3 Business Logic

There must be one canonical stock mutation service.

All of these use it:

- Stock In
- Sale
- Sale Return (restock)
- Purchase Return (return to supplier)
- Adjustment
- Damage
- Expire

There must be one canonical debt payment service for each debt type.

There must be one canonical document sequence service.

---

## 9.4 Testing

Required tests:

### Auth
- initial admin setup only once
- login success/failure
- forgot-password Telegram code
- expiry
- wrong code
- attempt limit
- password reset

### Stock
- stock in
- adjustment in/out
- damage
- expiry
- cannot oversell
- rollback on failure

### POS
- barcode lookup
- sale transaction
- walk-in customer cash sale
- registered customer debt sale
- debt sale rejected for walk-in customer
- return
- restock logic

### Debts
- partial customer payment
- full customer payment
- partial supplier payment
- full supplier payment
- overpayment rejected

### Permissions
- denied actions return 403
- UI hides actions
- backend still enforces permission

### Sequences
- no duplicate invoice numbers under concurrent requests

### Reports
- sales totals
- purchase totals
- debt totals
- finance calculations
- Finance page has no chart; income/expense table works; Add Expense persists; filters are on the table toolbar (not AppHeader date/refresh)

---

# 10. Definition of Done

The system is complete when:

- first-time admin setup works
- login works
- Telegram forgot-password works
- product image thumbnails use local files (or placeholders when missing)
- Stock product table shows image thumbnails (placeholder when missing)
- Stock product table shows Expire Date column immediately before Status
- POS product cards and cart lines show product images (placeholder when missing)
- invoices print from the browser only (no stored PDF, no Telegram invoice send)
- RabbitMQ/Celery workers process approved async jobs (Telegram, expiry alerts, maintenance — not invoice PDFs)
- all approved sidebar pages exist
- categories work
- units of measure (UOM) work
- brands work
- products require UOM
- products may link optional brand
- products work
- all stock operations work
- stock list shows Stock In / Stock Out / Damage Stock with clickable history dialogs; Current Stock is a number only; Stock In / Damage history dialogs support toolbar Add
- suppliers work
- supplier debt works
- POS name/barcode/scanner search works
- POS two-step sell/checkout and printable bilingual invoice work
- POS sale is transactional
- delivery notes track product delivery to customers from sales (no second stock-out)
- customer debt works
- customer/supplier debt payments work from Debt Report row **Pay** actions
- all 5 reports work
- dashboard has exactly 4 KPI cards in one desktop row (no Sales This Month KPI card)
- dashboard has Income vs Expense line chart with auto-fit height on all devices
- dashboard has complete Business Summary beside chart
- users work
- roles/permissions work
- document sequences work (including Delivery Note `DN-`)
- audit logs work
- settings work
- tests pass
- migrations are clean
- Docker production deployment works with the lean stack (API, frontend, db, redis). Scheduler runs in the API. MinIO/RabbitMQ/workers are not required.
- backup/restore instructions exist (PostgreSQL; Redis is disposable cache)
- no critical security issue remains

---

# 11. Final Navigation Reference

```text
Dashboard

Stock

POS

Delivery Notes

Setup
├── Categories
├── Units of Measure (UOM)
├── Brands
├── Suppliers
└── Customers

Reports
├── Sales Report
├── Purchase Report
├── Customer Debt Report
├── Supplier Debt Report
└── Finance Report

Administration
├── Users
├── Roles & Permissions
├── Document Sequence
├── Audit Log
└── Settings
```

Setup frontend routes:

```text
/setup/categories
/setup/uoms
/setup/brands
/setup/suppliers
/setup/customers
```

Authentication is outside the sidebar:

```text
First-Time Setup
Login
Forgot Password
Reset Password
```

---

# 12. Final Instruction to AI Coding Agent

Build exactly the system defined in this document.

Priorities:

1. Data correctness
2. Stock transaction integrity
3. Financial/debt correctness
4. Permission security
5. POS speed
6. Clean ERPNext-inspired business UI
7. Maintainable modular-monolith architecture
8. Production deployment

Before adding any new page, module, table, workflow, or major dependency not defined here, stop and request approval.

Do not replace Nuxt UI with another component library.

Do not convert the project to microservices.

Do not make the UI look like a marketing dashboard.

Keep the interface compact, professional, and optimized for daily shop operations.
