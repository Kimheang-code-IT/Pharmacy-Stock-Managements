import type { ApiMeta } from '~/types/stock-pos/common'
import type { AppRecord } from '~/config/admin-seed'

/** Query translation of the workspace list controls into named API parameters. */
export interface EntityListQuery {
  q?: string
  page?: number
  limit?: number
  sort?: string
  status?: string
  startDate?: string
  endDate?: string
  customerId?: string
  supplierId?: string
  productId?: string
  paymentMethod?: string
  type?: string
}

export interface EntityListResult<T extends object = AppRecord> {
  items: T[]
  meta: ApiMeta | null
}

/** Typed CRUD contract shared by every `/api/v1` entity collection. */
export interface EntityRepository {
  list(collection: string, query?: EntityListQuery): Promise<EntityListResult>
  get(collection: string, id: string): Promise<AppRecord | null>
  create(collection: string, input: Record<string, unknown>): Promise<AppRecord>
  update(collection: string, id: string, input: Record<string, unknown>): Promise<AppRecord>
  remove(collection: string, id: string): Promise<void>
  setStatus?(collection: string, id: string, status: string): Promise<AppRecord>
}

export interface PosSaleItemInput {
  productId: string
  quantity: number
  /** Optional override; when omitted the product sale price is used. */
  unitPrice?: number
  /** Per-line percent discount (0–100). */
  discountPercent?: number
  /** Selected line UOM (base or a product Convert-UOM row). */
  uomId?: string
  /** Selected UOM symbol snapshot for the invoice/lines. */
  uomSymbol?: string
  /** How many base UOM units 1 of the selected UOM contains (default 1).
   *  Stock is always mutated in the base UOM: baseQty = quantity × factor. */
  factorToBase?: number
}

export interface PosCompleteSaleInput {
  customerId?: string | null
  customerName?: string | null
  items: PosSaleItemInput[]
  paymentMethod: string
  paidAmount: number
  discount?: number
  note?: string | null
  /** Open customer-debt rows to include on this invoice and settle from paid now. */
  includedDebtIds?: string[]
  /** Delivery fee added to the sale total (editable on checkout). */
  deliveryPrice?: number
  /** Extra amount due on this invoice (selected debts and/or typed deposit). */
  deposit?: number
}

/** One delivery note line: quantity to deliver from a sold (already stocked-out) sale line
 *  of a parent invoice. Lines of MULTIPLE invoices of the SAME customer may be combined
 *  on one delivery note (spec §2.1.9). */
export interface DeliveryNoteLineInput {
  /** Parent sale id — required unless the request-level `saleId` applies to every line. */
  saleId?: string
  saleItemId: string
  productId: string
  qtyToDeliver: number
}

/**
 * Create a delivery note from one or many confirmed invoices of the SAME
 * customer. The backend must validate `qty_to_deliver` against the remaining
 * undelivered quantity per sale line across non-cancelled delivery notes,
 * allocate `DN-000001` under a lock, write the audit entry and commit —
 * without creating stock movements. Phone + location are the only
 * delivery-destination fields (no driver/vehicle/schedule form, spec §5.13).
 */
export interface DeliveryNoteCreateInput {
  /** POS auto-entry shortcut: applies to every line that omits its saleId. */
  saleId?: string
  /** Must match the invoices' customer when set (same-customer rule). */
  customerId?: string | null
  deliveryPhone?: string | null
  deliveryLocation?: string | null
  note?: string | null
  lines: DeliveryNoteLineInput[]
  /** Save directly as Confirmed instead of Draft. */
  confirm?: boolean
}

export type DeliveryStatusActionInput = 'confirm' | 'out_for_delivery' | 'deliver' | 'cancel'

/** Movement-kind filter for the product history dialog (Current Stock is display-only). */
export type StockHistoryKind = 'stock_in' | 'stock_out' | 'damage'

/** One product-scoped stock movement row (UI camelCase; GET /stock/products/{id}/history). */
export interface ProductHistoryRow {
  id: string
  date: string
  /** Backend movement label, e.g. 'Stock In' / 'Sale' / 'Damage'. */
  type: string
  /** Signed base-UOM quantity (negative = stock out). */
  quantity: number
  reference: string
  user: string
  note: string
  kind: StockHistoryKind
}

/** One Stock In cost lot of a product (UI camelCase; GET /stock/products/{id}/cost-history). */
export interface ProductCostHistoryRow {
  id: string
  date: string
  product: string
  unitCost: number
  quantity: number
  /** quantity × unitCost (decimal-safe). */
  amount: number
  /** 1 = oldest lot, incremented per newer lot; displayed newest first. */
  version: number
  documentNo: string
}

/** One sale-price version of a product (UI camelCase; /products/{id}/sale-prices). */
export interface ProductSalePriceRow {
  id: string
  productId: string
  product: string
  salePrice: number
  date: string
  /** Exactly one version per product is POS-active. */
  isActive: boolean
  version: number
}

/** Query accepted by the product-scoped history / price dialogs. */
export interface ProductScopedQuery {
  q?: string
  startDate?: string
  endDate?: string
  page?: number
  limit?: number
}

/** Read-only product-scoped queries used by the Stock list dialogs. */
export interface StockQueryRepository {
  /** Movement history of one product; `type` filters by dialog kind. */
  listProductHistory(productId: string, query?: ProductScopedQuery & { type?: StockHistoryKind }): Promise<EntityListResult<ProductHistoryRow>>
  /** Stock In cost lots of one product (versions assigned oldest → newest). */
  listProductCostHistory(productId: string, query?: ProductScopedQuery): Promise<EntityListResult<ProductCostHistoryRow>>
  /** Sale-price versions of one product (newest first). */
  listSalePrices(productId: string, query?: ProductScopedQuery): Promise<EntityListResult<ProductSalePriceRow>>
  /** Add a new POS-active version (version = MAX+1; copies onto products.salePrice). */
  addSalePrice(productId: string, input: { date: string, salePrice: number }): Promise<ProductSalePriceRow>
  /** Activate one version — exactly one stays active; copies onto products.salePrice. */
  activateSalePrice(productId: string, priceId: string): Promise<ProductSalePriceRow>
}

/** Printable receipt payload for a completed sale (no PDF/MinIO required). */
export interface SaleReceipt {
  saleId: string
  saleNo: string
  invoiceNo: string
  date: string
  customer: string
  cashier: string
  paymentMethod: string
  note: string
  items: Array<{
    name: string
    quantity: number
    uom: string
    unitPrice: number
    discount: number
    total: number
  }>
  subtotal: number
  discount: number
  deliveryPrice: number
  deposit: number
  total: number
  paidAmount: number
  remaining: number
}

/**
 * Operational commands for POS checkout. Implementations must treat the whole
 * checkout as one transaction on the backend side (sale + items + payment or
 * debt + stock movements + document number + audit entry).
 */
export interface PosCommandRepository {
  completeSale(input: PosCompleteSaleInput): Promise<AppRecord>
  createStockOperation(input: {
    type: 'stock_in' | 'adjustment' | 'damage' | 'expiry'
    productId: string
    quantity: number
    note?: string | null
    /** Stock In line UOM (base or a product Convert-UOM row). */
    uomId?: string
    /** Selected UOM symbol snapshot for history display. */
    uomSymbol?: string
    /** base qty = quantity × factorToBase (default 1, base UOM). */
    factorToBase?: number
    /** Unit cost per the selected UOM (Stock In). */
    unitCost?: number
  }): Promise<AppRecord>
  payCustomerDebt(input: {
    customerId: string
    /** When known, the backend path is POST /customers/{id}/debts/{debt_id}/payments. */
    debtId?: string
    amount: number
    paymentMethod: string
    reference?: string | null
  }): Promise<AppRecord>
  paySupplierDebt(input: {
    supplierId: string
    /** When known, the backend path is POST /suppliers/{id}/debts/{debt_id}/payments. */
    debtId?: string
    amount: number
    paymentMethod: string
    reference?: string | null
  }): Promise<AppRecord>
  /** Printable receipt payload derived from the stored sale (mock: in-memory). */
  getSaleReceipt(saleId: string): Promise<SaleReceipt>
  /** Customer return against a confirmed sale (POST /pos/sales/{id}/return). */
  returnSale(input: {
    saleId: string
    reason: string
    lines: Array<{ lineId: string, quantity: number, restock: boolean }>
  }): Promise<AppRecord>
  /** Supplier return against a confirmed Stock In (POST /stock/in/{id}/return). */
  returnPurchase(input: {
    stockInId: string
    reason: string
    lines: Array<{ lineId: string, quantity: number }>
  }): Promise<AppRecord>
}

/**
 * Operational commands for delivery notes (spec §2.1.9). Status transitions
 * must be permission-checked and audited server-side; Delivered stamps
 * `delivered_at` and per-line `qty_delivered`; cancelling is impossible after
 * Delivered and requires a reason. No command here may create stock movements.
 */
export interface DeliveryCommandRepository {
  createDeliveryNote(input: DeliveryNoteCreateInput): Promise<AppRecord>
  /** Update Status (spec §5.13): set a legal next status; cancel needs a reason. */
  setDeliveryStatus(id: string, status: string, reason?: string | null): Promise<AppRecord>
  /** Confirmed sales with remaining deliverable qty (create-page invoice picker). */
  deliverableInvoices(search?: string | null): Promise<AppRecord[]>
}

/**
 * Business Summary snapshot for the dashboard (spec section 2.1.1).
 *
 * Mirrors GET /api/v1/dashboard/summary (backend `cards` + `summary` +
 * `extras` blocks). `grossProfit` / `netIncome` are `null` when the viewer
 * lacks the profit permission. Money values are decimal-safe numbers.
 */
export interface DashboardSummary {
  productsTotal: number
  lowStockCount: number
  outOfStockCount: number
  salesToday: number
  salesTodayAmount: number
  salesThisMonth: number
  salesThisMonthAmount: number
  income: number
  expense: number
  grossProfit: number | null
  netIncome: number | null
  customerDebt: number
  supplierDebt: number
  damageLoss: number
  expiryLoss: number
  pendingDeliveryNotes: number
  salesByDay: Array<{ date: string, count: number }>
  incomeByDay: Array<{ date: string, amount: number }>
  expenseByDay: Array<{ date: string, amount: number }>
  startDate?: string | null
  endDate?: string | null
}

export interface FinanceSummary {
  income: number
  expense: number
  net: number
  outstanding: number
  startDate?: string | null
  endDate?: string | null
}

export type FinanceEntryType = 'income' | 'expense'

/**
 * One combined Finance Report ledger row (spec: Finance Report is an income
 * & expense table, not a chart). Income rows are system-derived from
 * confirmed POS sales / paid amounts; expense rows are user-managed
 * operating expenses. No chart, no standalone expense page.
 */
export interface FinanceEntry {
  id: string
  date: string
  type: FinanceEntryType
  /** Income: sale / invoice number. Expense: optional document reference. */
  reference: string
  /** Income: source label (e.g. Sales). Expense: operating category. */
  category: string
  description: string
  amount: number
  paymentMethod: string
  user: string
}

export interface FinanceExpenseInput {
  date: string
  category: string
  description: string
  /** Must be > 0. */
  amount: number
  paymentMethod: string
  reference?: string | null
  user?: string
}

export interface FinanceRepository {
  dashboard(startDate?: string, endDate?: string, requestKey?: string): Promise<DashboardSummary>
  financeSummary(startDate?: string, endDate?: string): Promise<FinanceSummary>
  /** Combined income + expense rows for the Finance table (date-filtered). */
  entries(startDate?: string, endDate?: string): Promise<FinanceEntry[]>
  /** Create an operating expense via the Add Expense modal (Finance only). */
  createExpense(input: FinanceExpenseInput): Promise<FinanceEntry>
}

export interface SearchHitItem {
  id: string
  type: string
  title: string
  subtitle?: string | null
  url: string
}

export interface SearchRepository {
  search(q: string, limit?: number): Promise<SearchHitItem[]>
}