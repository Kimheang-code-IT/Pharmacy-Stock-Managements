import type { AppRecord } from '~/config/admin-seed'
import type {
  DashboardSummary,
  EntityListQuery,
  EntityListResult,
  EntityRepository,
  FinanceEntry,
  FinanceRepository,
  FinanceSummary,
  PosCommandRepository,
  PosCompleteSaleInput,
  ProductBatchRow,
  ProductCostHistoryRow,
  ProductHistoryRow,
  ProductSalePriceRow,
  ProductScopedQuery,
  SaleDetail,
  SaleReceipt,
  SearchHitItem,
  SearchRepository,
  StockHistoryKind,
  StockQueryRepository,
} from '~/repositories/contracts/entities'
import { applyListQuery, createId, mockLatency, nowIso, paginateMeta } from '../mocks/query'
import { mockInsert, mockRecords, mockRemove, mockUpdate, useMockDb } from '../mocks/db'
import { convertToBase, divideDecimalSafe, multiplyDecimalSafe, roundQty } from '~/utils/stock/uom-conversions'

/** Spec: a new product starts with sale-price version 1 (POS-active). */
function insertFirstSalePrice(product: AppRecord): void {
  mockInsert('productSalePrices', {
    productId: String(product.id),
    product: String(product.name ?? ''),
    salePrice: Number(product.salePrice || 0),
    date: String(product.createdAt || nowIso()).slice(0, 10),
    isActive: true,
    version: 1,
  })
}

/** Keep Setup location in sync with address used by delivery notes. */
function withPartyLocation(collection: string, input: Record<string, unknown>): Record<string, unknown> {
  if (collection !== 'customers' && collection !== 'suppliers') return input
  const location = String(input.location ?? input.address ?? '')
  const next: Record<string, unknown> = { ...input, location, address: location }
  // Outstanding debt is POS / Stock In only — never written from Setup forms.
  delete next.debtBalance
  delete next.totalDebt
  return next
}

/** In-memory implementation of the entity CRUD contract for mock-only mode. */
export function createMockEntityRepository(): EntityRepository {
  return {
    async list(collection: string, query: EntityListQuery = {}): Promise<EntityListResult> {
      const rows = mockRecords(collection)
      const response = applyListQuery(rows, { ...query, limit: query.limit ?? 1000 })
      return { items: response.data, meta: response.meta ?? null }
    },

    async get(collection: string, id: string): Promise<AppRecord | null> {
      return mockLatency(mockRecords(collection).find(row => String(row.id) === String(id)) || null)
    },

    async create(collection: string, input: Record<string, unknown>): Promise<AppRecord> {
      const payload = withPartyLocation(collection, input)
      if (collection === 'customers') payload.debtBalance = 0
      if (collection === 'suppliers') payload.totalDebt = 0
      const created = mockInsert(collection, payload)
      if (collection === 'products') insertFirstSalePrice(created)
      return mockLatency(created)
    },

    async update(collection: string, id: string, input: Record<string, unknown>): Promise<AppRecord> {
      const updated = mockUpdate(collection, id, withPartyLocation(collection, input))
      if (!updated) throw new Error(`Record ${id} not found in ${collection}`)
      return mockLatency(updated)
    },

    async remove(collection: string, id: string): Promise<void> {
      mockRemove(collection, id)
      await mockLatency(undefined)
    },

    async setStatus(collection: string, id: string, status: string): Promise<AppRecord> {
      const updated = mockUpdate(collection, id, { status })
      if (!updated) throw new Error(`Record ${id} not found in ${collection}`)
      return mockLatency(updated)
    },
  }
}

const dayKey = (iso: string) => String(iso).slice(0, 10)
const round2 = (value: number) => Math.round(value * 100) / 100

/** Movement type → history-dialog kind (Current Stock is display-only). */
function historyKindOf(type: string): StockHistoryKind | null {
  if (type === 'Stock In' || type === 'Sale Return') return 'stock_in'
  if (type === 'Sale' || type === 'Purchase Return') return 'stock_out'
  if (type === 'Damage') return 'damage'
  return null
}

/** Shared q / date-range / pagination handling for product-scoped dialog rows. */
function paginateScopedRows<T extends { date: string }>(
  rows: T[],
  query: ProductScopedQuery = {},
  searchKeys: string[],
): EntityListResult<T> {
  const page = Number(query.page || 1)
  const limit = Number(query.limit || 500)
  const q = String(query.q || '').trim().toLowerCase()
  let filtered = rows
  if (q) {
    filtered = filtered.filter(row => searchKeys.some(key =>
      String((row as Record<string, unknown>)[key] ?? '').toLowerCase().includes(q)))
  }
  const startDate = query.startDate ? String(query.startDate).slice(0, 10) : ''
  const endDate = query.endDate ? String(query.endDate).slice(0, 10) : ''
  if (startDate || endDate) {
    filtered = filtered.filter((row) => {
      const day = String(row.date ?? '').slice(0, 10)
      if (!day) return true
      if (startDate && day < startDate) return false
      if (endDate && day > endDate) return false
      return true
    })
  }
  const start = (page - 1) * limit
  return { items: filtered.slice(start, start + limit), meta: paginateMeta(filtered.length, page, limit) }
}

/**
 * In-memory product-scoped queries for the Stock list dialogs. Implementations
 * mirror the /api/v1 product-scoped history / cost-history / sale-price paths,
 * so the dialogs never need to download unrelated collections.
 */
export function createMockStockQueryRepository(): StockQueryRepository {
  /** Receipt payload for one sale (POS print + Stock Out invoice detail dialog). */
  function saleReceipt(saleId: string): SaleReceipt {
    const db = useMockDb()
    const sale = db.collections.sales.find(row => String(row.id) === String(saleId))
    if (!sale) throw new Error(`Sale ${saleId} not found`)
    const items = (Array.isArray(sale.items) ? sale.items : []) as AppRecord[]
    return {
      saleId: String(sale.id),
      saleNo: String(sale.saleNo ?? ''),
      invoiceNo: String(sale.invoiceNo || sale.saleNo || ''),
      date: String(sale.date || sale.createdAt || '').slice(0, 10),
      customer: String(sale.customer || 'Walk-in customer'),
      cashier: String(sale.cashier || '—'),
      paymentMethod: String(sale.paymentMethod || ''),
      note: String(sale.note ?? ''),
      items: items.map(item => ({
        name: String(item.name ?? ''),
        quantity: Number(item.quantity ?? 0),
        uom: String(item.uom ?? ''),
        unitPrice: Number(item.price ?? 0),
        discount: Number(item.discount ?? 0),
        total: Number(item.total ?? 0),
      })),
      subtotal: Number(sale.subtotal ?? 0),
      discount: Number(sale.discount ?? 0),
      deliveryPrice: Number(sale.deliveryPrice ?? 0),
      deposit: Number(sale.deposit ?? 0),
      total: Number(sale.total ?? 0),
      paidAmount: Number(sale.paidAmount ?? 0),
      remaining: Number(sale.remaining ?? 0),
    }
  }

  function productSalePriceRows(productId: string): ProductSalePriceRow[] {
    return mockRecords('productSalePrices')
      .filter(row => String(row.productId ?? '') === String(productId))
      .map(row => ({
        id: String(row.id),
        productId: String(row.productId),
        product: String(row.product ?? ''),
        salePrice: Number(row.salePrice ?? 0),
        date: String(row.date ?? '').slice(0, 10),
        isActive: row.isActive === true || row.isActive === 'Yes',
        version: Number(row.version ?? 0),
        batchNo: row.batchNo != null ? String(row.batchNo) : null,
        purchaseDate: row.purchaseDate != null ? String(row.purchaseDate).slice(0, 10) : null,
        expiryDate: row.expiryDate != null ? String(row.expiryDate).slice(0, 10) : null,
        purchaseCost: row.purchaseCost != null ? Number(row.purchaseCost) : null,
        uomPrices: Array.isArray(row.uomPrices)
          ? (row.uomPrices as Record<string, unknown>[]).map(uomRow => ({
              uomId: String(uomRow.uomId ?? ''),
              uomSymbol: uomRow.uomSymbol != null ? String(uomRow.uomSymbol) : null,
              factorToBase: Number(uomRow.factorToBase ?? 1),
              salePrice: Number(uomRow.salePrice ?? 0),
              isDefaultSale: uomRow.isDefaultSale === true,
            }))
          : [],
      }))
      .sort((a, b) => b.version - a.version || b.date.localeCompare(a.date))
  }

  function copyActivePriceOntoProduct(productId: string, salePrice: number): void {
    const product = mockRecords('products').find(row => String(row.id) === String(productId))
    if (product) product.salePrice = round2(salePrice)
  }

  return {
    async listProductHistory(productId, query = {}): Promise<EntityListResult<ProductHistoryRow>> {
      const kind = query.type
      const rows: ProductHistoryRow[] = mockRecords('stockMovements')
        .filter(row => String(row.productId ?? '') === String(productId))
        .filter((row) => {
          if (!kind) return true
          return historyKindOf(String(row.type ?? '')) === kind
        })
        .map((row) => {
          const signedQty = Number(row.quantity ?? 0)
          const unitPrice = Number(row.unitPrice ?? 0)
          const type = String(row.type ?? '')
          // Sale rows link to their POS invoice (Stock Out click-through).
          const isSale = type === 'Sale'
          const sale = isSale
            ? mockRecords('sales').find(saleRow =>
                String(saleRow.saleNo ?? '') === String(row.reference ?? '')
                || String(saleRow.invoiceNo ?? '') === String(row.reference ?? ''))
            : undefined
          return {
            id: String(row.id),
            date: dayKey(String(row.date || row.createdAt || '')),
            type,
            quantity: signedQty,
            product: String(row.product ?? ''),
            unit: String(row.unit ?? row.uomSymbol ?? ''),
            unitPrice,
            reference: String(row.reference ?? ''),
            referenceType: isSale ? 'sale' : 'stock_transaction',
            referenceId: isSale ? String(sale?.id ?? row.referenceId ?? '') : String(row.referenceId ?? row.id ?? ''),
            user: String(row.user ?? ''),
            note: String(row.note ?? ''),
            // Batch traceability (spec: movements expose the lot the change hit).
            batchNo: (row.batchNo ?? null) as string | null,
            expiryDate: (row.expiryDate ?? null) as string | null,
            kind: historyKindOf(type) ?? 'stock_in',
          }
        })
        .sort((a, b) => b.date.localeCompare(a.date))
      return mockLatency(paginateScopedRows(rows, query, ['type', 'reference', 'user', 'note']))
    },

    /**
     * Batch lots of one product derived from the mock movement ledger
     * (same rule as the HTTP repository: identity = product + batch_no,
     * remaining = inbound − outbound, expiry = latest stamped on the lot).
     */
    async listProductBatches(productId, query = {}): Promise<EntityListResult<ProductBatchRow>> {
      const today = new Date().toISOString().slice(0, 10)
      const lots = new Map<string, {
        batchNo: string
        expiryDates: string[]
        received: number
        remaining: number
        unitCost: number | null
        supplier: string
        purchaseNo: string
        createdDate: string
      }>()
      for (const row of mockRecords('stockMovements')) {
        if (String(row.productId ?? '') !== String(productId)) continue
        const batchNo = String(row.batchNo ?? '').trim()
        if (!batchNo) continue
        const qty = Number(row.quantity ?? 0)
        const date = String(row.date ?? row.createdAt ?? '').slice(0, 10)
        // Batch identity = product + batch_no + expiry (a different expiry is a
        // distinct lot), matching the backend.
        const expiryKey = String(row.expiryDate ?? '').trim()
        const key = `${String(productId)}:${batchNo}:${expiryKey}`
        let lot = lots.get(key)
        if (!lot) {
          lot = { batchNo, expiryDates: [], received: 0, remaining: 0, unitCost: null, supplier: '', purchaseNo: '', createdDate: date }
          lots.set(key, lot)
        }
        if (qty > 0) {
          lot.received += qty
          lot.remaining += qty
          if (row.expiryDate) lot.expiryDates.push(String(row.expiryDate))
          if (row.unitCost != null && Number(row.unitCost) > 0) lot.unitCost = Number(row.unitCost)
          if (!lot.purchaseNo) lot.purchaseNo = String(row.documentNo ?? '')
        }
        else {
          lot.remaining += qty
        }
        if (date && date > lot.createdDate) lot.createdDate = date
      }
      const product = mockRecords('products').find(row => String(row.id) === String(productId))
      const prices = productSalePriceRows(productId)
      const rows: ProductBatchRow[] = []
      for (const [key, lot] of lots) {
        const remaining = roundQty(lot.remaining)
        const expiry = lot.expiryDates.sort()[0] ?? null
        // Supplier snapshot: the purchase document that first received the lot.
        const sourcePurchase = lot.purchaseNo
          ? mockRecords('stockIns').find(row => String(row.purchaseNo ?? '') === lot.purchaseNo)
          : undefined
        const activePrice = prices.find(row => row.isActive && String(row.batchNo ?? '') === lot.batchNo)
        const latestPrice = activePrice
          || prices.find(row => String(row.batchNo ?? '') === lot.batchNo)
        const generalPrice = prices.find(row => row.isActive && !row.batchNo)
        rows.push({
          id: key,
          productId: String(productId),
          batchNo: lot.batchNo,
          expiryDate: expiry,
          remainingQty: remaining,
          receivedQty: roundQty(lot.received),
          unitCost: lot.unitCost ?? 0,
          supplier: String(sourcePurchase?.supplier ?? lot.supplier ?? ''),
          purchaseNo: lot.purchaseNo,
          createdDate: lot.createdDate,
          status: remaining <= 0
            ? 'Depleted'
            : (lot.expiryDates.length && (lot.expiryDates.sort()[0] ?? '') < today)
              ? 'Expired'
              : 'Active',
          purchaseDate: String(sourcePurchase?.date ?? lot.createdDate ?? '').slice(0, 10) || null,
          purchaseUom: String(product?.uomSymbol || product?.uom || 'pcs'),
          currency: String(sourcePurchase?.currency ?? 'USD'),
          salePrice: latestPrice != null
            ? Number(latestPrice.salePrice)
            : Number(generalPrice?.salePrice ?? product?.salePrice ?? 0),
          salePriceId: latestPrice?.id ? String(latestPrice.id) : null,
          pricingActive: activePrice != null,
        })
      }
      const filtered = rows
        .filter((row) => {
          const status = String(query.status || '').toUpperCase()
          if (!status || status === 'ALL') return true
          return row.status.toUpperCase() === status
        })
        .sort((a, b) => {
          const depleted = Number(a.remainingQty <= 0) - Number(b.remainingQty <= 0)
          if (depleted !== 0) return depleted
          const expiry = String(a.expiryDate ?? '9999-12-31').localeCompare(String(b.expiryDate ?? '9999-12-31'))
          if (expiry !== 0) return expiry
          return a.batchNo.localeCompare(b.batchNo)
        })
      return mockLatency({
        items: filtered,
        meta: { page: Number(query.page || 1), limit: Number(query.limit || 500), total: filtered.length },
      })
    },

    async listProductCostHistory(productId, query = {}): Promise<EntityListResult<ProductCostHistoryRow>> {
      // Stock In lots oldest → newest assign versions 1, 2, 3… then display newest first.
      const lots = mockRecords('stockIns')
        .flatMap(purchase => (Array.isArray(purchase.items) ? purchase.items as AppRecord[] : [])
          .filter(item => String(item.productId ?? '') === String(productId))
          .map(item => ({
            purchase,
            item,
          })))
        .sort((a, b) => dayKey(String(a.purchase.date || a.purchase.createdAt || ''))
          .localeCompare(dayKey(String(b.purchase.date || b.purchase.createdAt || ''))))
        .map((lot, index) => ({
          id: `${String(lot.purchase.id)}:${String(lot.item.id ?? lot.item.name ?? '')}`,
          date: dayKey(String(lot.purchase.date || lot.purchase.createdAt || '')),
          product: String(lot.item.name ?? ''),
          unitCost: Number(lot.item.price ?? 0),
          quantity: Number(lot.item.quantity ?? 0),
          // Decimal-safe amount (spec: never persist/compute via binary floats).
          amount: round2(multiplyDecimalSafe(lot.item.price ?? 0, lot.item.quantity ?? 0)),
          version: index + 1,
          documentNo: String(lot.purchase.purchaseNo ?? ''),
        }))
        .reverse()
      return mockLatency(paginateScopedRows(lots, query, ['product', 'documentNo']))
    },

    async listSalePrices(productId, query = {}): Promise<EntityListResult<ProductSalePriceRow>> {
      return mockLatency(paginateScopedRows(
        productSalePriceRows(productId),
        query,
        ['product'],
      ))
    },

    async getMovementInvoice(movementId): Promise<SaleReceipt | null> {
      const movement = mockRecords('stockMovements').find(row => String(row.id) === String(movementId))
      if (!movement || String(movement.type ?? '') !== 'Sale') return null
      const reference = String(movement.reference ?? '')
      const sale = mockRecords('sales').find(row =>
        String(row.saleNo ?? '') === reference || String(row.invoiceNo ?? '') === reference)
      if (!sale) return null
      return mockLatency(saleReceipt(String(sale.id)))
    },

    async addSalePrice(productId, input): Promise<ProductSalePriceRow> {
      const salePrice = Number(input.salePrice)
      if (!Number.isFinite(salePrice) || salePrice <= 0) throw new Error('Sale price must be greater than zero')
      if (!String(input.date || '').trim()) throw new Error('Date is required')
      const product = mockRecords('products').find(row => String(row.id) === String(productId))
      if (!product) throw new Error(`Unknown product: ${productId}`)
      const existing = productSalePriceRows(productId)
      const batchNo = String(input.batchNo ?? '').trim() || null
      // Spec: exactly one POS-active version per product + batch scope —
      // retire the current active version of the SAME scope only.
      for (const row of mockRecords('productSalePrices')) {
        if (String(row.productId) !== String(productId) || !row.isActive) continue
        if (String(row.batchNo ?? '') === String(batchNo ?? '')) row.isActive = false
      }
      // UOM price rows inside the version (fall back to one base row).
      const uomPrices = (input.uomPrices?.length ? input.uomPrices : [{
        uomId: String(product.uomId ?? ''),
        uomSymbol: String(product.uom ?? ''),
        factorToBase: 1,
        salePrice,
        isDefaultSale: true,
      }]).map(row => ({
        uomId: String(row.uomId),
        uomSymbol: row.uomSymbol ?? null,
        factorToBase: Number(row.factorToBase) || 1,
        salePrice: round2(Number(row.salePrice)),
        isDefaultSale: row.isDefaultSale === true,
      }))
      const defaultPrice = uomPrices.find(row => row.isDefaultSale)?.salePrice ?? round2(salePrice)
      const nextVersion = existing.reduce((max, row) => Math.max(max, row.version), 0) + 1
      const created = mockInsert('productSalePrices', {
        productId: String(productId),
        product: String(product.name ?? ''),
        salePrice: defaultPrice,
        date: String(input.date).slice(0, 10),
        isActive: true,
        version: nextVersion,
        batchNo,
        purchaseDate: input.purchaseDate ? String(input.purchaseDate).slice(0, 10) : null,
        expiryDate: input.expiryDate ? String(input.expiryDate).slice(0, 10) : null,
        uomPrices,
      })
      // General scope mirrors onto products.salePrice; batch-scoped prices do not.
      if (!batchNo) {
        copyActivePriceOntoProduct(productId, defaultPrice)
      }
      return mockLatency(productSalePriceRows(productId).find(row => String(row.id) === String(created.id))!)
    },

    async activateSalePrice(productId, priceId): Promise<ProductSalePriceRow> {
      const rows = mockRecords('productSalePrices')
      const target = rows.find(row => String(row.id) === String(priceId)
        && String(row.productId ?? '') === String(productId))
      if (!target) throw new Error(`Sale price ${priceId} not found for product ${productId}`)
      for (const row of rows) {
        if (String(row.productId ?? '') !== String(productId)) continue
        // Only the same batch scope switches (batch-first resolution rule).
        if (String(row.batchNo ?? '') !== String(target.batchNo ?? '')) continue
        row.isActive = String(row.id) === String(priceId)
      }
      target.isActive = true
      if (!String(target.batchNo ?? '').trim()) {
        copyActivePriceOntoProduct(productId, Number(target.salePrice ?? 0))
      }
      return mockLatency(productSalePriceRows(productId).find(row => String(row.id) === String(priceId))!)
    },

    async setSalePriceActive(priceId, isActive): Promise<ProductSalePriceRow> {
      const rows = mockRecords('productSalePrices')
      const target = rows.find(row => String(row.id) === String(priceId))
      if (!target) throw new Error(`Sale price ${priceId} not found`)
      if (isActive) {
        return this.activateSalePrice(String(target.productId), priceId)
      }
      target.isActive = false
      return mockLatency(productSalePriceRows(String(target.productId)).find(row => String(row.id) === String(priceId))!)
    },
  }
}

function lastNDays(n: number): string[] {
  const days: string[] = []
  for (let i = n - 1; i >= 0; i -= 1) {
    const d = new Date()
    d.setDate(d.getDate() - i)
    days.push(d.toISOString().slice(0, 10))
  }
  return days
}

/** Currency-aware sum: KHR rows normalize to USD via the document exchange rate. */
function sumUsdBetween(rows: AppRecord[], amountKey: string, start: string, end: string): number {
  return rows.reduce((sum, row) => {
    const day = dayKey(String(row.date || row.createdAt || ''))
    if (day < start || day > end) return sum
    const rate = Number(row.exchangeRate ?? 1) || 1
    const amount = Number(row[amountKey] || 0)
    const usd = String(row.currency || 'USD') === 'KHR' ? divideDecimalSafe(amount, rate) : amount
    return sum + usd
  }, 0)
}

/** Mock dashboard/finance summaries computed from seeded sales, purchases and expenses. */
export function createMockFinanceRepository(): FinanceRepository {
  function summary(start: string, end: string): {
    income: number
    expense: number
    customerDebt: number
    supplierDebt: number
    grossProfit: number
  } {
    const db = useMockDb()
    const sales = db.collections.sales.filter(sale => ['Paid', 'Partial'].includes(String(sale.status)))
    // USD-normalized sums (KHR documents divide by their exchange rate).
    const income = sumUsdBetween(sales, 'paidAmount', start, end)
    // Expense = operating expenses only (spec: Finance Report expenses are
    // user-recorded rows; stock-in purchase amounts are not operating costs).
    const expense = sumUsdBetween(db.collections.expenses, 'amount', start, end)
    const customerDebt = db.collections.customers.reduce((sum, row) => sum + Number(row.debtBalance || 0), 0)
    const supplierDebt = db.collections.suppliers.reduce((sum, row) => sum + Number(row.totalDebt || 0), 0)
    // COGS from sold quantities valued at product cost price (same rule as the backend).
    const costByProduct = new Map(db.collections.products.map(product => [String(product.id), Number(product.costPrice || 0)]))
    const cogs = sales
      .filter(sale => dayKey(String(sale.date || sale.createdAt || '')) >= start
        && dayKey(String(sale.date || sale.createdAt || '')) <= end)
      .flatMap(sale => Array.isArray(sale.items) ? sale.items as AppRecord[] : [])
      .reduce((sum, item) => sum + Number(item.quantity || 0) * (costByProduct.get(String(item.productId)) || 0), 0)
    return {
      income: round2(income),
      expense: round2(expense),
      customerDebt: round2(customerDebt),
      supplierDebt: round2(supplierDebt),
      grossProfit: round2(income - cogs),
    }
  }

  return {
    async dashboard(startDate?: string, endDate?: string): Promise<DashboardSummary> {
      const db = useMockDb()
      const today = new Date().toISOString().slice(0, 10)
      const monthStart = `${today.slice(0, 7)}-01`
      const start = startDate || monthStart
      const end = endDate || today
      const totals = summary(start, end)
      const days = lastNDays(30)
      const salesByDay = days.map(date => ({
        date,
        count: db.collections.sales.filter(sale => dayKey(String(sale.date || sale.createdAt)) === date).length,
      }))
      const incomeByDay = days.map((date) => ({
        date,
        amount: round2(db.collections.sales
          .filter(sale => dayKey(String(sale.date || sale.createdAt)) === date)
          .reduce((sum, sale) => sum + Number(sale.paidAmount || 0), 0)),
      }))
      const expenseByDay = days.map((date) => ({
        date,
        // Operating expenses only (spec) — purchases are not expense rows.
        amount: round2(
          db.collections.expenses
            .filter(row => dayKey(String(row.date || row.createdAt)) === date)
            .reduce((sum, row) => sum + Number(row.amount || 0), 0),
        ),
      }))
      const salesThisMonth = db.collections.sales.filter(sale => dayKey(String(sale.date || sale.createdAt)) >= monthStart).length
      const salesThisMonthAmount = db.collections.sales
        .filter(sale => dayKey(String(sale.date || sale.createdAt)) >= monthStart)
        .reduce((sum, sale) => sum + Number(sale.paidAmount || 0), 0)
      const salesTodayAmount = db.collections.sales
        .filter(sale => dayKey(String(sale.date || sale.createdAt)) === today)
        .reduce((sum, sale) => sum + Number(sale.paidAmount || 0), 0)
      // Damage/expiry loss valued at product cost price for the selected period.
      const costByProduct = new Map(db.collections.products.map(product => [String(product.id), Number(product.costPrice || 0)]))
      const movementLoss = (type: string) => round2(db.collections.stockMovements
        .filter(row => String(row.type) === type
          && dayKey(String(row.date || row.createdAt || '')) >= start
          && dayKey(String(row.date || row.createdAt || '')) <= end)
        .reduce((sum, row) => sum + Math.abs(Number(row.quantity || 0)) * (costByProduct.get(String(row.productId)) || 0), 0))
      const damageLoss = movementLoss('Damage')
      const expiryLoss = movementLoss('Expiry')
      const pendingDeliveryNotes = db.collections.deliveryNotes
        .filter(note => !['Delivered', 'Cancelled'].includes(String(note.status || 'Draft'))).length
      return mockLatency({
        productsTotal: db.collections.products.length,
        lowStockCount: db.collections.products.filter(product => Number(product.quantity) <= 10).length,
        outOfStockCount: db.collections.products.filter(product => Number(product.quantity) <= 0).length,
        salesToday: db.collections.sales.filter(sale => dayKey(String(sale.date || sale.createdAt)) === today).length,
        salesTodayAmount: round2(salesTodayAmount),
        salesThisMonth,
        salesThisMonthAmount: round2(salesThisMonthAmount),
        damageLoss,
        expiryLoss,
        pendingDeliveryNotes,
        income: totals.income,
        expense: totals.expense,
        grossProfit: totals.grossProfit,
        // Same rule as the backend: net = gross profit - damage loss - expiry loss.
        netIncome: round2(totals.grossProfit - damageLoss - expiryLoss),
        customerDebt: totals.customerDebt,
        supplierDebt: totals.supplierDebt,
        salesByDay,
        incomeByDay,
        expenseByDay,
        startDate: start,
        endDate: end,
      })
    },

    async financeSummary(startDate?: string, endDate?: string): Promise<FinanceSummary> {
      const today = new Date().toISOString().slice(0, 10)
      const start = startDate || `${today.slice(0, 7)}-01`
      const end = endDate || today
      const totals = summary(start, end)
      return mockLatency({
        income: totals.income,
        expense: totals.expense,
        net: round2(totals.income - totals.expense),
        outstanding: round2(totals.customerDebt + totals.supplierDebt),
        startDate: start,
        endDate: end,
      })
    },

    async entries(startDate?: string, endDate?: string): Promise<FinanceEntry[]> {
      const today = new Date().toISOString().slice(0, 10)
      const start = startDate || `${today.slice(0, 7)}-01`
      const end = endDate || today
      return mockLatency(financeEntries(start, end))
    },

    async createExpense(input: Parameters<FinanceRepository['createExpense']>[0]): Promise<FinanceEntry> {
      const amount = Number(input.amount || 0)
      if (!Number.isFinite(amount) || amount <= 0) {
        throw new Error('Expense amount must be greater than zero')
      }
      if (!String(input.category || '').trim()) {
        throw new Error('Expense category is required')
      }
      const record = mockInsert('expenses', {
        date: String(input.date || new Date().toISOString().slice(0, 10)),
        category: String(input.category).trim(),
        description: String(input.description || '').trim(),
        amount: round2(amount),
        paymentMethod: String(input.paymentMethod || ''),
        reference: String(input.reference || ''),
        currency: input.currency ?? 'USD',
        exchangeRate: input.exchangeRate ?? 1,
        user: String(input.user || '—'),
      })
      return mockLatency({
        id: `fin-${record.id}`,
        date: dayKey(String(record.date || record.createdAt || '')),
        type: 'expense',
        reference: String(record.reference || ''),
        category: String(record.category || ''),
        description: String(record.description || ''),
        amount: round2(Number(record.amount || 0)),
        paymentMethod: String(record.paymentMethod || ''),
        currency: String(record.currency || 'USD'),
        exchangeRate: Number(record.exchangeRate ?? 1),
        user: String(record.user || '—'),
      })
    },
  }
}

/**
 * Combined Finance ledger rows. Income = confirmed POS sales / paid amounts
 * (system-derived); expenses = user-recorded operating expenses.
 */
function financeEntries(start: string, end: string): FinanceEntry[] {
  const db = useMockDb()
  const inRange = (row: AppRecord) => {
    const day = dayKey(String(row.date || row.createdAt || ''))
    return day >= start && day <= end
  }
  const income: FinanceEntry[] = db.collections.sales
    .filter(sale => ['Paid', 'Partial'].includes(String(sale.status))
      && Number(sale.paidAmount || 0) > 0
      && inRange(sale))
    .map(sale => ({
      id: `fin-${sale.id}`,
      date: dayKey(String(sale.date || sale.createdAt || '')),
      type: 'income' as const,
      reference: String(sale.saleNo || sale.invoiceNo || ''),
      category: 'Sales',
      description: String(sale.customer || ''),
      amount: round2(Number(sale.paidAmount || 0)),
      paymentMethod: String(sale.paymentMethod || ''),
      currency: String(sale.currency || 'USD'),
      exchangeRate: Number(sale.exchangeRate ?? 1),
      user: String(sale.cashier || '—'),
    }))
  const expense: FinanceEntry[] = db.collections.expenses
    .filter(row => inRange(row))
    .map(row => ({
      id: `fin-${row.id}`,
      date: dayKey(String(row.date || row.createdAt || '')),
      type: 'expense' as const,
      reference: String(row.reference || ''),
      category: String(row.category || ''),
      description: String(row.description || ''),
      amount: round2(Number(row.amount || 0)),
      paymentMethod: String(row.paymentMethod || ''),
      currency: String(row.currency || 'USD'),
      exchangeRate: Number(row.exchangeRate ?? 1),
      user: String(row.user || '—'),
    }))
  return [...income, ...expense].sort((a, b) =>
    a.date === b.date ? b.id.localeCompare(a.id) : b.date.localeCompare(a.date))
}

/** Mock search across products, customers, suppliers and sales. */
export function createMockSearchRepository(): SearchRepository {
  return {
    async search(q: string, limit = 12): Promise<SearchHitItem[]> {
      const needle = q.trim().toLowerCase()
      if (!needle) return []
      const db = useMockDb()
      const hits: Array<SearchHitItem & { score: number }> = []
      const push = (collection: string, type: string, title: string, subtitle: string | null, url: string) => {
        hits.push({ id: createId('hit'), type, title, subtitle, url, score: 0 })
      }
      const match = (value: unknown) => String(value ?? '').toLowerCase().includes(needle)

      for (const product of db.collections.products) {
        if (match(product.name) || match(product.code) || match(product.barcode)) {
          push('products', 'product', String(product.name), `${product.code} · Qty ${product.quantity}`, `/stock/${product.id}`)
        }
      }
      for (const customer of db.collections.customers) {
        if (match(customer.name) || match(customer.code) || match(customer.phone)) {
          push('customers', 'customer', String(customer.name), `${customer.code} · ${customer.phone}`, `/setup/customers/${customer.id}`)
        }
      }
      for (const supplier of db.collections.suppliers) {
        if (match(supplier.name) || match(supplier.code) || match(supplier.phone)) {
          push('suppliers', 'supplier', String(supplier.name), `${supplier.code} · ${supplier.phone}`, `/setup/suppliers/${supplier.id}`)
        }
      }
      for (const sale of db.collections.sales) {
        if (match(sale.saleNo) || match(sale.customer)) {
          push('sales', 'sale', String(sale.saleNo), `${sale.customer} · ${sale.total}`, `/reports/sales?q=${encodeURIComponent(String(sale.saleNo))}`)
        }
      }

      hits.sort((a, b) => Number(b.title.toLowerCase().startsWith(needle)) - Number(a.title.toLowerCase().startsWith(needle)))
      return mockLatency(hits.slice(0, limit).map(({ score: _score, ...hit }) => hit))
    },
  }
}

/**
 * Mock POS/stock operational commands. Each operation mutates several mock
 * collections the same way the real backend must commit them atomically.
 */
export function createMockPosRepository(): PosCommandRepository {
  function sequenceNext(documentType: string, prefix: string, padding: number): string {
    const db = useMockDb()
    const row = db.collections.documentSequences.find(seq => seq.documentType === documentType)
    const next = Number(row?.lastValue || 0) + 1
    if (row) row.lastValue = next
    return `${prefix}-${String(next).padStart(padding, '0')}`
  }

  function addAudit(eventType: string, action: string, entityType: string, entityId: string, entityLabel: string, result = 'SUCCESS') {
    const db = useMockDb()
    db.collections.auditLogs.unshift({
      id: createId('al'),
      occurredAt: nowIso(),
      userName: 'Sokha Chan',
      user: 'Sokha Chan',
      eventType,
      action,
      entityType,
      entityId,
      entityLabel,
      entity: entityLabel,
      result,
      ipAddress: '127.0.0.1',
      ipDevice: '127.0.0.1',
    } as AppRecord)
  }

  function applyMovement(
    productId: string,
    productName: string,
    type: string,
    quantity: number,
    reference: string,
    note: string,
    extra: { uom?: string, unitCost?: number, batchNo?: string, expiryDate?: string, documentNo?: string } = {},
  ) {
    const db = useMockDb()
    // Running balance display columns (ledger math stays in the base UOM).
    const balanceBefore = roundQty(db.collections.stockMovements
      .filter(row => String(row.productId ?? '') === String(productId))
      .reduce((sum, row) => sum + Number(row.quantity ?? 0), 0))
    const product = db.collections.products.find(row => String(row.id) === String(productId))
    db.collections.stockMovements.unshift({
      id: createId('mv'),
      createdAt: nowIso(),
      date: nowIso().slice(0, 10),
      productId,
      product: productName,
      barcode: String(product?.barcode ?? ''),
      type,
      quantity,
      reference,
      documentNo: extra.documentNo ?? reference,
      user: 'Sokha Chan',
      note,
      unit: extra.uom ?? String(product?.uomSymbol ?? ''),
      uomSymbol: extra.uom ?? String(product?.uomSymbol ?? ''),
      uom: extra.uom ?? String(product?.uomSymbol ?? ''),
      qtyIn: quantity > 0 ? quantity : 0,
      qtyOut: quantity < 0 ? Math.abs(quantity) : 0,
      balanceBefore,
      balanceAfter: roundQty(balanceBefore + quantity),
      ...(extra.unitCost != null ? { unitCost: extra.unitCost } : {}),
      ...(extra.batchNo ? { batchNo: extra.batchNo } : {}),
      ...(extra.expiryDate ? { expiryDate: extra.expiryDate } : {}),
    } as AppRecord)
  }

  function saleReceipt(saleId: string): SaleReceipt {
    const db = useMockDb()
    const sale = db.collections.sales.find(row => String(row.id) === String(saleId))
    if (!sale) throw new Error(`Sale ${saleId} not found`)
    const items = (Array.isArray(sale.items) ? sale.items : []) as AppRecord[]
    return {
      saleId: String(sale.id),
      saleNo: String(sale.saleNo ?? ''),
      invoiceNo: String(sale.invoiceNo || sale.saleNo || ''),
      date: String(sale.date || sale.createdAt || '').slice(0, 10),
      customer: String(sale.customer || 'Walk-in customer'),
      cashier: String(sale.cashier || '—'),
      paymentMethod: String(sale.paymentMethod || ''),
      note: String(sale.note ?? ''),
      items: items.map(item => ({
        name: String(item.name ?? ''),
        quantity: Number(item.quantity ?? 0),
        uom: String(item.uom ?? ''),
        unitPrice: Number(item.price ?? 0),
        discount: Number(item.discount ?? 0),
        total: Number(item.total ?? 0),
      })),
      subtotal: Number(sale.subtotal ?? 0),
      discount: Number(sale.discount ?? 0),
      deliveryPrice: Number(sale.deliveryPrice ?? 0),
      deposit: Number(sale.deposit ?? 0),
      total: Number(sale.total ?? 0),
      paidAmount: Number(sale.paidAmount ?? 0),
      remaining: Number(sale.remaining ?? 0),
    }
  }

  return {
    async completeSale(input: PosCompleteSaleInput): Promise<AppRecord> {
      const db = useMockDb()
      const items = input.items.map((item) => {
        const product = db.collections.products.find(row => String(row.id) === String(item.productId))
        if (!product) throw new Error(`Unknown product: ${item.productId}`)
        const quantity = Number(item.quantity)
        if (!Number.isFinite(quantity) || quantity <= 0) throw new Error('Quantity must be greater than zero')
        // Stock is always mutated in the product's base UOM (spec: Convert UOM).
        const factor = Number(item.factorToBase ?? 1)
        if (!Number.isFinite(factor) || factor <= 0) throw new Error('UOM factor must be greater than zero')
        const baseQty = convertToBase(quantity, factor)
        const available = Number(product.quantity || 0)
        if (baseQty > available) throw new Error(`Insufficient stock for ${product.name}`)
        const price = item.unitPrice == null ? Number(product.salePrice) : Number(item.unitPrice)
        if (!Number.isFinite(price) || price < 0) throw new Error('Unit price must be zero or greater')
        const discountPercent = Math.min(100, Math.max(0, Number(item.discountPercent || 0)))
        const gross = round2(price * quantity)
        const lineDiscount = round2(gross * (discountPercent / 100))
        const lineTotal = round2(gross - lineDiscount)
        const uomRecord = db.collections.uoms.find(row => String(row.id) === String(product.uomId || ''))
        return {
          // Sale line id — delivery-note lines reference it (sale_item_id).
          id: createId('line'),
          productId: product.id,
          name: product.name,
          // Snapshot of the selected line UOM (base or a Convert-UOM row).
          uom: String(item.uomSymbol || product.uomSymbol || uomRecord?.symbol || product.uom || uomRecord?.name || ''),
          uomId: item.uomId ? String(item.uomId) : String(product.uomId || ''),
          factorToBase: factor,
          quantity,
          baseQuantity: baseQty,
          // Batch allocation traceability (spec 12, internal only - FEFO
          // handled invisibly by the backend; snapshot for Sale detail).
          batchNo: 'FEFO',
          expiryDate: null,
          price,
          discountPercent,
          discount: lineDiscount,
          total: lineTotal,
        }
      })
      const subtotal = round2(items.reduce((sum, item) => sum + round2(Number(item.price) * Number(item.quantity)), 0))
      const lineDiscountTotal = round2(items.reduce((sum, item) => sum + Number(item.discount || 0), 0))
      const discount = round2(Number(input.discount ?? lineDiscountTotal))
      const deliveryPrice = round2(Math.max(0, Number(input.deliveryPrice || 0)))
      const total = round2(subtotal - discount + deliveryPrice)
      const customer = input.customerId
        ? db.collections.customers.find(row => String(row.id) === String(input.customerId)) || null
        : null
      const paidNow = round2(Number(input.paidAmount || 0))
      const includedDebtIds = new Set((input.includedDebtIds || []).map(String).filter(Boolean))
      const includedDebts = db.collections.customerDebts
        .filter(row => includedDebtIds.has(String(row.id)))
        .filter(row => Number(row.remainingAmount || 0) > 0)
        .filter(row => customer && String(row.customerId) === String(customer.id))
        .sort((a, b) => String(a.date || '').localeCompare(String(b.date || '')))
      const selectedDeposit = round2(includedDebts.reduce((sum, row) => sum + Number(row.remainingAmount || 0), 0))
      const depositTotal = round2(Math.max(0, input.deposit == null ? selectedDeposit : Number(input.deposit)))
      const credit = input.paymentMethod === 'Credit'
      // Walk-in cannot underpay the sale; prior-debt payment also needs a customer.
      if ((credit || total > paidNow || depositTotal > 0) && !customer) {
        throw new Error('Credit sales require a customer')
      }
      // Settle prior debts from deposit only (separate from sale payment).
      let debtBudget = depositTotal
      if (customer && debtBudget > 0 && includedDebts.length) {
        for (const debt of includedDebts) {
          if (debtBudget <= 0) break
          const open = round2(Number(debt.remainingAmount || 0))
          if (open <= 0) continue
          const applied = round2(Math.min(open, debtBudget))
          const paid = round2(Number(debt.paidAmount || 0) + applied)
          const stillOpen = round2(open - applied)
          debt.paidAmount = paid
          debt.remainingAmount = stillOpen
          debt.status = stillOpen <= 0 ? 'PAID' : 'PARTIAL'
          debtBudget = round2(debtBudget - applied)
          customer.debtBalance = round2(Number(customer.debtBalance || 0) - applied)
          const priorSale = db.collections.sales.find(row => String(row.id) === String(debt.saleId))
          if (priorSale) {
            priorSale.paidAmount = round2(Number(priorSale.paidAmount || 0) + applied)
            priorSale.remaining = stillOpen
            priorSale.status = stillOpen <= 0 ? 'Paid' : Number(priorSale.paidAmount) > 0 ? 'Partial' : 'Unpaid'
          }
        }
      }
      const salePaid = round2(Math.min(Math.max(0, paidNow), total))
      const remaining = round2(total - salePaid)

      const sale = mockInsert('sales', {
        saleNo: sequenceNext('SALE', 'SALE', 5),
        invoiceNo: sequenceNext('INV', 'INV', 6),
        date: nowIso().slice(0, 10),
        createdAt: nowIso(),
        customerId: customer?.id ?? null,
        customer: customer?.name ?? (input.customerName || 'Walk-in customer'),
        items,
        lineCount: items.length,
        subtotal,
        discount,
        deliveryPrice,
        total,
        paidAmount: salePaid,
        remaining,
        paymentMethod: input.paymentMethod,
        cashier: 'Sokha Chan',
        status: remaining <= 0 ? 'Paid' : salePaid > 0 ? 'Partial' : 'Unpaid',
        note: input.note ?? null,
        currency: input.currency ?? 'USD',
        exchangeRate: input.exchangeRate ?? 1,
      })

      for (const item of items) {
        const product = db.collections.products.find(row => String(row.id) === String(item.productId))!
        // Stock-out in the base UOM: quantity × factorToBase.
        product.quantity = roundQty(Number(product.quantity) - Number(item.baseQuantity))
        // Movement reference is the invoice number (matches the backend SALE movement).
        applyMovement(String(product.id), String(product.name), 'Sale', -Number(item.baseQuantity), String(sale.invoiceNo || sale.saleNo), 'POS sale', { uom: String(item.uom || '') })
      }
      if (customer && remaining > 0) {
        customer.debtBalance = round2(Number(customer.debtBalance || 0) + remaining)
        // Debt reports list document-level rows: record the credit invoice (spec 2.1.10).
        mockInsert('customerDebts', {
          saleId: sale.id,
          customerId: customer.id,
          customer: customer.name,
          invoiceNo: String(sale.invoiceNo || sale.saleNo),
          date: String(sale.date),
          invoiceTotal: total,
          paidAmount: salePaid,
          remainingAmount: remaining,
          dueDate: null,
          status: salePaid > 0 ? 'PARTIAL' : 'UNPAID',
          currency: input.currency ?? 'USD',
          exchangeRate: input.exchangeRate ?? 1,
        })
      }
      addAudit('SALE', 'create', 'Sale', String(sale.saleNo), String(sale.saleNo))
      return mockLatency(sale)
    },

    async updateSale(input): Promise<AppRecord> {
      const db = useMockDb()
      const sale = db.collections.sales.find(row => String(row.id) === String(input.saleId))
      if (!sale) throw new Error(`Sale ${input.saleId} not found`)
      if (db.collections.saleReturns.some(row => String(row.saleId) === String(sale.id))) {
        throw new Error('Sales with returns cannot be edited')
      }

      // Reverse the original lines back into stock.
      const previousItems = (Array.isArray(sale.items) ? sale.items : []) as AppRecord[]
      for (const item of previousItems) {
        const product = db.collections.products.find(row => String(row.id) === String(item.productId))
        const baseQuantity = Number(item.baseQuantity ?? item.quantity ?? 0)
        if (product && baseQuantity > 0) {
          product.quantity = roundQty(Number(product.quantity) + baseQuantity)
          applyMovement(String(product.id), String(product.name), 'Sale Return', baseQuantity, String(sale.invoiceNo || sale.saleNo), 'Sale edit reversal', { uom: String(item.uom || '') })
        }
      }
      const customer = sale.customerId
        ? db.collections.customers.find(row => String(row.id) === String(sale.customerId)) || null
        : null
      const previousRemaining = round2(Number(sale.remaining || 0))
      if (customer && previousRemaining > 0) {
        customer.debtBalance = round2(Math.max(0, Number(customer.debtBalance || 0) - previousRemaining))
      }
      for (const debt of db.collections.customerDebts) {
        if (String(debt.saleId) !== String(sale.id)) continue
        debt.paidAmount = Number(debt.invoiceTotal || 0)
        debt.remainingAmount = 0
        debt.status = 'PAID'
      }

      const items = input.items.map((item) => {
        const product = db.collections.products.find(row => String(row.id) === String(item.productId))
        if (!product) throw new Error(`Unknown product: ${item.productId}`)
        const quantity = Number(item.quantity)
        if (!Number.isFinite(quantity) || quantity <= 0) throw new Error('Quantity must be greater than zero')
        const factor = Number(item.factorToBase ?? 1)
        if (!Number.isFinite(factor) || factor <= 0) throw new Error('UOM factor must be greater than zero')
        const baseQty = convertToBase(quantity, factor)
        const price = item.unitPrice == null ? Number(product.salePrice) : Number(item.unitPrice)
        const discountPercent = Math.min(100, Math.max(0, Number(item.discountPercent || 0)))
        const gross = round2(price * quantity)
        const lineDiscount = round2(gross * (discountPercent / 100))
        return {
          id: createId('line'),
          productId: product.id,
          name: product.name,
          uom: String(item.uomSymbol || product.uomSymbol || product.uom || ''),
          uomId: item.uomId ? String(item.uomId) : String(product.uomId || ''),
          factorToBase: factor,
          quantity,
          baseQuantity: baseQty,
          batchNo: 'FEFO',
          expiryDate: null,
          price,
          discountPercent,
          discount: lineDiscount,
          total: round2(gross - lineDiscount),
        }
      })
      const subtotal = round2(items.reduce((sum, item) => sum + round2(Number(item.price) * Number(item.quantity)), 0))
      const lineDiscountTotal = round2(items.reduce((sum, item) => sum + Number(item.discount || 0), 0))
      const discount = round2(Number(input.discount ?? lineDiscountTotal))
      const deliveryPrice = round2(Math.max(0, Number(input.deliveryPrice || 0)))
      const total = round2(subtotal - discount + deliveryPrice)
      const paidNow = round2(Math.min(Number(sale.paidAmount || 0), total))
      const remaining = round2(total - paidNow)

      for (const item of items) {
        const product = db.collections.products.find(row => String(row.id) === String(item.productId))!
        product.quantity = roundQty(Number(product.quantity) - Number(item.baseQuantity))
        applyMovement(String(product.id), String(product.name), 'Sale', -Number(item.baseQuantity), String(sale.invoiceNo || sale.saleNo), 'POS sale (edited)', { uom: String(item.uom || '') })
      }

      Object.assign(sale, {
        items,
        lineCount: items.length,
        subtotal,
        discount,
        deliveryPrice,
        total,
        paidAmount: paidNow,
        remaining,
        status: remaining <= 0 ? 'Paid' : paidNow > 0 ? 'Partial' : 'Unpaid',
        note: input.note ?? null,
        currency: input.currency ?? 'USD',
        exchangeRate: input.exchangeRate ?? 1,
        customerId: customer?.id ?? null,
        customer: customer?.name ?? String(sale.customer || 'Walk-in customer'),
      })

      if (customer && remaining > 0) {
        customer.debtBalance = round2(Number(customer.debtBalance || 0) + remaining)
        const existing = db.collections.customerDebts.find(row => String(row.saleId) === String(sale.id))
        if (existing) {
          Object.assign(existing, {
            invoiceTotal: total,
            paidAmount: paidNow,
            remainingAmount: remaining,
            status: paidNow > 0 ? 'PARTIAL' : 'UNPAID',
            currency: input.currency ?? 'USD',
            exchangeRate: input.exchangeRate ?? 1,
          })
        }
        else {
          mockInsert('customerDebts', {
            saleId: sale.id,
            customerId: customer.id,
            customer: customer.name,
            invoiceNo: String(sale.invoiceNo || sale.saleNo),
            date: String(sale.date),
            invoiceTotal: total,
            paidAmount: paidNow,
            remainingAmount: remaining,
            dueDate: null,
            status: paidNow > 0 ? 'PARTIAL' : 'UNPAID',
            currency: input.currency ?? 'USD',
            exchangeRate: input.exchangeRate ?? 1,
          })
        }
      }
      addAudit('SALE', 'update', 'Sale', String(sale.saleNo), String(sale.saleNo))
      return mockLatency(sale)
    },

    async getSaleReceipt(saleId: string): Promise<SaleReceipt> {
      return mockLatency(saleReceipt(saleId))
    },

    async getSale(saleId: string): Promise<SaleDetail> {
      const db = useMockDb()
      const sale = db.collections.sales.find(row => String(row.id) === String(saleId))
      if (!sale) throw new Error(`Sale ${saleId} not found`)
      const items = (Array.isArray(sale.items) ? sale.items : []) as AppRecord[]
      return mockLatency({
        id: String(sale.id),
        invoiceNo: String(sale.invoiceNo || sale.saleNo || ''),
        customerId: sale.customerId ? String(sale.customerId) : null,
        customerName: String(sale.customer || ''),
        currency: String(sale.currency ?? 'USD') === 'KHR' ? 'KHR' : 'USD',
        exchangeRate: Number(sale.exchangeRate ?? 1) || 1,
        items: items.map((item) => {
          const quantity = Number(item.quantity || 0)
          const unitPrice = Number(item.price ?? item.unitPrice ?? 0)
          const discountAmount = Number(item.discount ?? item.discountAmount ?? 0)
          return {
            id: String(item.id || ''),
            productId: String(item.productId || ''),
            name: String(item.name || ''),
            uom: String(item.uom || item.uomSymbol || ''),
            uomId: item.uomId ? String(item.uomId) : undefined,
            factorToBase: Number(item.factorToBase ?? 1) || 1,
            quantity,
            returnedQuantity: Number(item.returnedQuantity || 0),
            unitPrice,
            discountPercent: Number(item.discountPercent || 0),
            discountAmount,
            lineTotal: Number(item.total ?? round2(unitPrice * quantity - discountAmount)),
          }
        }),
      } as SaleDetail)
    },

    async getProductByBarcode(barcode: string): Promise<AppRecord | null> {
      const db = useMockDb()
      const code = String(barcode || '').trim()
      if (!code) return null
      const product = db.collections.products.find(row =>
        String(row.barcode || '').trim() === code
        && String(row.status || 'Active') !== 'Inactive',
      )
      return mockLatency(product ? ({ ...product } as AppRecord) : null)
    },

    async createStockOperation(input): Promise<AppRecord> {
      const db = useMockDb()
      const product = db.collections.products.find(row => String(row.id) === String(input.productId))
      if (!product) throw new Error(`Unknown product: ${input.productId}`)
      const quantity = Number(input.quantity)
      if (!Number.isFinite(quantity) || quantity === 0) throw new Error('Quantity is required')
      // Received qty is converted to the product base/stock UOM before the
      // mutation (spec: Stock In line UOM). Non stock-in ops stay in base UOM.
      const factor = input.type === 'stock_in'
        ? Number(input.factorToBase ?? 1)
        : 1
      if (!Number.isFinite(factor) || factor <= 0) throw new Error('UOM factor must be greater than zero')
      const baseQty = roundQty(convertToBase(quantity, factor))
      const uomRecord = db.collections.uoms.find(row => String(row.id) === String(product.uomId || ''))
      const baseUomSymbol = String(product.uomSymbol || uomRecord?.symbol || uomRecord?.name || '')
      const lineUomSymbol = input.type === 'stock_in' ? String(input.uomSymbol || baseUomSymbol) : baseUomSymbol
      // Unit cost is per the selected line UOM; snapshot per base UOM.
      const lineUnitCost = input.unitCost != null ? Number(input.unitCost) : null
      const baseUnitCost = lineUnitCost != null ? divideDecimalSafe(lineUnitCost, factor) : null
      const typeByOp: Record<string, { label: string, sign: number, docType: string, prefix: string }> = {
        stock_in: { label: 'Stock In', sign: 1, docType: 'STOCK_IN', prefix: 'PIN' },
        adjustment: { label: 'Adjustment', sign: Math.sign(quantity) || 1, docType: 'ADJUSTMENT', prefix: 'ADJ' },
        damage: { label: 'Damage', sign: -1, docType: 'ADJUSTMENT', prefix: 'ADJ' },
        expiry: { label: 'Expiry', sign: -1, docType: 'ADJUSTMENT', prefix: 'ADJ' },
      }
      const meta = typeByOp[input.type]
      if (!meta) throw new Error(`Unsupported stock operation: ${input.type}`)
      const reference = sequenceNext(meta.docType, meta.prefix, 5)
      const signed = meta.sign < 0 ? -Math.abs(baseQty) : Math.abs(baseQty)
      // Movement label matches the approved movement-type filter values.
      const movementLabel = input.type === 'adjustment'
        ? (signed >= 0 ? 'Adjustment Increase' : 'Adjustment Decrease')
        : meta.label
      product.quantity = roundQty(Number(product.quantity) + signed)
      if (Number(product.quantity) <= 10) product.status = 'Low Stock'
      else if (String(product.status) === 'Low Stock') product.status = 'Active'
      applyMovement(String(product.id), String(product.name), movementLabel, signed, reference, input.note ?? '', {
        uom: lineUomSymbol,
        ...(baseUnitCost != null ? { unitCost: baseUnitCost } : {}),
        // Batch traceability: stock-in receives into the named lot; damage /
        // expiry drain that same lot (identity = product + batch_no).
        ...(input.batchNo ? { batchNo: String(input.batchNo) } : {}),
        ...(input.type === 'stock_in' && input.expiryDate ? { expiryDate: String(input.expiryDate) } : {}),
        ...(input.type === 'expiry' && input.expiryDate ? { expiryDate: String(input.expiryDate) } : {}),
      })
      addAudit('STOCK', input.type, 'Product', String(product.code), reference)
      return mockLatency({
        id: createId('op'),
        reference,
        productId: String(product.id),
        product: String(product.name),
        type: movementLabel,
        quantity: signed,
        uom: lineUomSymbol,
        factorToBase: factor,
        note: input.note ?? null,
        createdAt: nowIso(),
      } as AppRecord)
    },

    /**
     * Complete purchase (Stock In): every line lands on ONE document with one
     * reference; product quantities, movements and audit update per line.
     */
    async createPurchase(input): Promise<AppRecord> {
      const db = useMockDb()
      if (!input.lines?.length) throw new Error('At least one product line is required')
      const reference = sequenceNext('STOCK_IN', 'PIN', 5)
      let total = 0
      const productNames: string[] = []
      for (const line of input.lines) {
        const product = db.collections.products.find(row => String(row.id) === String(line.productId))
        if (!product) throw new Error(`Unknown product: ${line.productId}`)
        const quantity = Number(line.quantity)
        if (!Number.isFinite(quantity) || quantity <= 0) throw new Error(`Quantity is required for ${String(product.name)}`)
        const factor = Number(line.factorToBase ?? 1)
        if (!Number.isFinite(factor) || factor <= 0) throw new Error('UOM factor must be greater than zero')
        const baseQty = roundQty(convertToBase(quantity, factor))
        const uomRecord = db.collections.uoms.find(row => String(row.id) === String(product.uomId || ''))
        const baseUomSymbol = String(product.uomSymbol || uomRecord?.symbol || uomRecord?.name || '')
        const lineUomSymbol = String(line.uomSymbol || baseUomSymbol)
        const lineUnitCost = line.unitCost != null ? Number(line.unitCost) : null
        const baseUnitCost = lineUnitCost != null ? divideDecimalSafe(lineUnitCost, factor) : null
        product.quantity = roundQty(Number(product.quantity) + baseQty)
        if (Number(product.quantity) <= 10) product.status = 'Low Stock'
        else if (String(product.status) === 'Low Stock') product.status = 'Active'
        applyMovement(String(product.id), String(product.name), 'Stock In', baseQty, reference, input.note ?? '', {
          uom: lineUomSymbol,
          ...(baseUnitCost != null ? { unitCost: baseUnitCost } : {}),
          // Batch traceability: the line receives into its named lot.
          ...(line.batchNo ? { batchNo: String(line.batchNo) } : {}),
          ...(line.expiryDate ? { expiryDate: String(line.expiryDate) } : {}),
        })
        total = round2(total + round2(quantity * (lineUnitCost ?? 0)))
        productNames.push(String(product.name))
      }
      // Document-level purchase adjustments (discount then tax), matching
      // the backend total: subtotal − discount + tax. Amounts are in the
      // document currency (lines are sent already converted by the caller).
      const discount = round2(Math.max(0, Number(input.discountAmount ?? 0)))
      const tax = round2(Math.max(0, Number(input.taxAmount ?? 0)))
      total = round2(Math.max(0, total - discount + tax))
      const currency = input.currency ?? 'USD'
      const exchangeRate = Number(input.exchangeRate ?? 1)
      // Unpaid balance on a supplier purchase is recorded as supplier debt.
      const paid = round2(Math.min(Math.max(0, Number(input.paidAmount ?? total)), total))
      const outstanding = round2(total - paid)
      if (outstanding > 0 && input.supplierId) {
        const supplier = db.collections.suppliers.find(row => String(row.id) === String(input.supplierId))
        if (supplier) {
          supplier.totalDebt = round2(Number(supplier.totalDebt || 0) + outstanding)
          mockInsert('supplierDebts', {
            date: nowIso().slice(0, 10),
            supplierId: String(supplier.id),
            supplier: String(supplier.name),
            purchaseNo: reference,
            totalAmount: total,
            paidAmount: paid,
            remainingAmount: outstanding,
            status: paid > 0 ? 'PARTIAL' : 'UNPAID',
            currency,
            exchangeRate,
          } as unknown as Partial<AppRecord>)
        }
      }
      addAudit('STOCK', 'stock_in', 'Purchase', reference, reference)
      return mockLatency({
        id: createId('purchase'),
        reference,
        documentNo: reference,
        type: 'Stock In',
        products: productNames,
        // Batch traceability (spec 17): items carry their lot + expiry.
        items: input.lines.map((line, i) => ({
          id: createId('pline'),
          productId: String(line.productId),
          name: productNames[i] ?? '',
          batchNo: line.batchNo ?? null,
          expiryDate: line.expiryDate ?? null,
          uom: '',
          quantity: Number(line.quantity || 0),
          price: Number(line.unitCost ?? 0),
          total: round2(Number(line.quantity || 0) * Number(line.unitCost ?? 0)),
        })),
        quantity: input.lines.reduce((sum, line) => sum + Number(line.quantity || 0), 0),
        total,
        paidAmount: paid,
        outstanding,
        currency,
        exchangeRate,
        note: input.note ?? null,
        createdAt: nowIso(),
      } as AppRecord)
    },

    async updatePurchase(input): Promise<AppRecord> {
      const db = useMockDb()
      const purchase = db.collections.stockIns.find(row => String(row.id) === String(input.stockInId))
      if (!purchase) throw new Error(`Stock In ${input.stockInId} not found`)

      // Reverse the original receipt.
      const previousItems = (Array.isArray(purchase.items) ? purchase.items : []) as AppRecord[]
      for (const item of previousItems) {
        const product = db.collections.products.find(row => String(row.id) === String(item.productId))
        const qty = Number(item.baseQuantity ?? item.quantity ?? 0)
        if (product && qty > 0) {
          product.quantity = roundQty(Number(product.quantity) - qty)
          applyMovement(String(product.id), String(product.name), 'Purchase Return', -qty, String(purchase.purchaseNo || ''), 'Purchase edit reversal', { uom: String(item.uom || '') })
        }
      }
      const previousRemaining = round2(Number(purchase.remaining || 0))
      const supplier = purchase.supplierId
        ? db.collections.suppliers.find(row => String(row.id) === String(purchase.supplierId)) || null
        : null
      if (supplier && previousRemaining > 0) {
        supplier.totalDebt = round2(Math.max(0, Number(supplier.totalDebt || 0) - previousRemaining))
      }
      for (const debt of db.collections.supplierDebts) {
        if (String(debt.stockTransactionId) !== String(purchase.id)) continue
        debt.paidAmount = Number(debt.totalAmount || 0)
        debt.remainingAmount = 0
        debt.status = 'PAID'
      }

      let subtotal = 0
      const items = input.lines.map((line) => {
        const product = db.collections.products.find(row => String(row.id) === String(line.productId))
        if (!product) throw new Error(`Unknown product: ${line.productId}`)
        const quantity = Number(line.quantity)
        if (!Number.isFinite(quantity) || quantity <= 0) throw new Error(`Quantity is required for ${String(product.name)}`)
        const factor = Number(line.factorToBase ?? 1)
        if (!Number.isFinite(factor) || factor <= 0) throw new Error('UOM factor must be greater than zero')
        const baseQty = roundQty(convertToBase(quantity, factor))
        const unitCost = line.unitCost != null ? Number(line.unitCost) : 0
        product.quantity = roundQty(Number(product.quantity) + baseQty)
        applyMovement(String(product.id), String(product.name), 'Stock In', baseQty, String(purchase.purchaseNo || ''), input.note ?? '', {
          uom: String(line.uomSymbol || ''),
          ...(line.unitCost != null ? { unitCost: divideDecimalSafe(unitCost, factor) } : {}),
          ...(line.batchNo ? { batchNo: String(line.batchNo) } : {}),
          ...(line.expiryDate ? { expiryDate: String(line.expiryDate) } : {}),
        })
        subtotal = round2(subtotal + round2(quantity * unitCost))
        return {
          id: createId('pline'),
          productId: String(line.productId),
          name: String(product.name),
          batchNo: line.batchNo ?? null,
          expiryDate: line.expiryDate ?? null,
          uom: String(line.uomSymbol || ''),
          quantity,
          baseQuantity: baseQty,
          price: unitCost,
          total: round2(quantity * unitCost),
        }
      })
      const discount = round2(Math.max(0, Number(input.discountAmount ?? 0)))
      const tax = round2(Math.max(0, Number(input.taxAmount ?? 0)))
      const total = round2(Math.max(0, subtotal - discount + tax))
      const paid = round2(Math.min(Number(purchase.paidAmount ?? 0), total))
      const remaining = round2(total - paid)

      Object.assign(purchase, {
        items,
        lineCount: items.length,
        products: items.map(item => item.name),
        total,
        discountAmount: discount,
        taxAmount: tax,
        paidAmount: paid,
        remaining,
        status: remaining <= 0 ? 'Completed' : 'Partial',
        note: input.note ?? null,
        currency: input.currency ?? 'USD',
        exchangeRate: input.exchangeRate ?? 1,
      })

      if (supplier && remaining > 0) {
        supplier.totalDebt = round2(Number(supplier.totalDebt || 0) + remaining)
        const existing = db.collections.supplierDebts.find(row => String(row.stockTransactionId) === String(purchase.id))
        if (existing) {
          Object.assign(existing, {
            totalAmount: total,
            paidAmount: paid,
            remainingAmount: remaining,
            status: paid > 0 ? 'PARTIAL' : 'UNPAID',
            currency: input.currency ?? 'USD',
          })
        }
        else {
          mockInsert('supplierDebts', {
            date: nowIso().slice(0, 10),
            supplierId: String(supplier.id),
            supplier: String(supplier.name),
            purchaseNo: String(purchase.purchaseNo || ''),
            totalAmount: total,
            paidAmount: paid,
            remainingAmount: remaining,
            status: paid > 0 ? 'PARTIAL' : 'UNPAID',
            currency: input.currency ?? 'USD',
            exchangeRate: input.exchangeRate ?? 1,
          } as unknown as Partial<AppRecord>)
        }
      }
      addAudit('STOCK', 'stock_in_update', 'Purchase', String(purchase.purchaseNo), String(purchase.purchaseNo))
      return mockLatency(purchase)
    },

    async payCustomerDebt(input): Promise<AppRecord> {
      const db = useMockDb()
      const customer = db.collections.customers.find(row => String(row.id) === String(input.customerId))
      if (!customer) throw new Error(`Unknown customer: ${input.customerId}`)
      const amount = round2(Number(input.amount || 0))
      if (amount <= 0) throw new Error('Payment amount must be greater than zero')

      const openDebts = db.collections.customerDebts.filter(debt =>
        String(debt.customerId) === String(customer.id) && Number(debt.remainingAmount || 0) > 0)

      let targets = openDebts
        .slice()
        .sort((a, b) => String(a.date).localeCompare(String(b.date)))
      if (input.debtId) {
        const selected = openDebts.find(debt => String(debt.id) === String(input.debtId))
        if (!selected) throw new Error(`Unknown debt: ${input.debtId}`)
        if (amount > Number(selected.remainingAmount || 0)) {
          throw new Error('Payment exceeds the outstanding balance')
        }
        targets = [selected]
      }
      else if (amount > Number(customer.debtBalance || 0)) {
        throw new Error('Payment exceeds the outstanding balance')
      }

      customer.debtBalance = round2(Math.max(0, Number(customer.debtBalance || 0) - amount))
      let left = amount
      for (const debt of targets) {
        if (left <= 0) break
        const remaining = round2(Number(debt.remainingAmount || 0))
        if (remaining <= 0) continue
        const applied = round2(Math.min(remaining, left))
        const paid = round2(Number(debt.paidAmount || 0) + applied)
        const stillOpen = round2(remaining - applied)
        debt.paidAmount = paid
        debt.remainingAmount = stillOpen
        debt.status = stillOpen <= 0 ? 'PAID' : 'PARTIAL'
        left = round2(left - applied)
        const sale = db.collections.sales.find(row => String(row.id) === String(debt.saleId))
        if (sale) {
          sale.paidAmount = round2(Number(sale.paidAmount || 0) + applied)
          sale.remaining = stillOpen
          sale.status = stillOpen <= 0 ? 'Paid' : Number(sale.paidAmount) > 0 ? 'Partial' : 'Unpaid'
        }
      }

      const payment = mockInsert('customerDebtPayments', {
        date: nowIso().slice(0, 10),
        customerId: customer.id,
        customer: customer.name,
        debtId: input.debtId || null,
        amount,
        paymentMethod: input.paymentMethod,
        reference: input.reference || sequenceNext('PAYMENT', 'PAY', 5),
        user: 'Sokha Chan',
      })
      addAudit('DEBT', 'payment', 'Customer', String(customer.code), String(customer.name))
      return mockLatency(payment)
    },

    async paySupplierDebt(input): Promise<AppRecord> {
      const db = useMockDb()
      const supplier = db.collections.suppliers.find(row => String(row.id) === String(input.supplierId))
      if (!supplier) throw new Error(`Unknown supplier: ${input.supplierId}`)
      const amount = round2(Number(input.amount || 0))
      if (amount <= 0) throw new Error('Payment amount must be greater than zero')

      const openDebts = db.collections.supplierDebts.filter(debt =>
        String(debt.supplierId) === String(supplier.id) && Number(debt.remainingAmount || 0) > 0)

      let targets = openDebts
        .slice()
        .sort((a, b) => String(a.date).localeCompare(String(b.date)))
      if (input.debtId) {
        const selected = openDebts.find(debt => String(debt.id) === String(input.debtId))
        if (!selected) throw new Error(`Unknown debt: ${input.debtId}`)
        if (amount > Number(selected.remainingAmount || 0)) {
          throw new Error('Payment exceeds the outstanding balance')
        }
        targets = [selected]
      }
      else if (amount > Number(supplier.totalDebt || 0)) {
        throw new Error('Payment exceeds the outstanding balance')
      }

      supplier.totalDebt = round2(Math.max(0, Number(supplier.totalDebt || 0) - amount))
      let left = amount
      for (const debt of targets) {
        if (left <= 0) break
        const remaining = round2(Number(debt.remainingAmount || 0))
        if (remaining <= 0) continue
        const applied = round2(Math.min(remaining, left))
        const paid = round2(Number(debt.paidAmount || 0) + applied)
        const stillOpen = round2(remaining - applied)
        debt.paidAmount = paid
        debt.remainingAmount = stillOpen
        debt.status = stillOpen <= 0 ? 'PAID' : 'PARTIAL'
        left = round2(left - applied)
        const purchase = db.collections.stockIns.find(row => String(row.id) === String(debt.stockTransactionId))
        if (purchase) {
          purchase.paidAmount = round2(Number(purchase.paidAmount || 0) + applied)
          purchase.remaining = stillOpen
          purchase.status = stillOpen <= 0 ? 'Completed' : 'Partial'
        }
      }

      const payment = mockInsert('supplierDebtPayments', {
        date: nowIso().slice(0, 10),
        supplierId: supplier.id,
        supplier: supplier.name,
        debtId: input.debtId || null,
        amount,
        paymentMethod: input.paymentMethod,
        reference: input.reference || sequenceNext('PAYMENT', 'PAY', 5),
        user: 'Sokha Chan',
      })
      addAudit('DEBT', 'payment', 'Supplier', String(supplier.code), String(supplier.name))
      return mockLatency(payment)
    },

    async returnSale(input): Promise<AppRecord> {
      const db = useMockDb()
      const sale = db.collections.sales.find(row => String(row.id) === String(input.saleId))
      if (!sale) throw new Error(`Sale ${input.saleId} not found`)
      const reason = String(input.reason || '').trim()
      if (!reason) throw new Error('Return reason is required')
      const items = (Array.isArray(sale.items) ? sale.items : []) as AppRecord[]
      if (!input.lines.length) throw new Error('Select at least one return quantity')
      let refund = 0
      const returnItems: AppRecord[] = []
      for (const lineIn of input.lines) {
        const qty = Number(lineIn.quantity)
        if (!Number.isFinite(qty) || qty <= 0) throw new Error('Return quantity must be greater than zero')
        const item = items.find(row => String(row.id) === String(lineIn.lineId))
        if (!item) throw new Error(`Unknown sale line: ${lineIn.lineId}`)
        const sold = Number(item.quantity || 0)
        const already = Number(item.returnedQuantity || 0)
        const returnable = roundQty(sold - already)
        if (qty > returnable + 1e-9) throw new Error(`Return qty exceeds returnable for ${item.name}`)
        const unit = sold > 0 && item.total != null
          ? round2(Number(item.total) / sold)
          : round2(Number(item.price || 0))
        const lineRefund = round2(unit * qty)
        refund = round2(refund + lineRefund)
        item.returnedQuantity = roundQty(already + qty)
        const factor = Number(item.factorToBase ?? 1) || 1
        const baseQty = roundQty(convertToBase(qty, factor))
        if (lineIn.restock) {
          const product = db.collections.products.find(row => String(row.id) === String(item.productId))
          if (product) {
            product.quantity = roundQty(Number(product.quantity || 0) + baseQty)
            if (Number(product.quantity) > 10 && String(product.status) === 'Low Stock') product.status = 'Active'
          }
          applyMovement(
            String(item.productId),
            String(item.name),
            'Sale Return',
            baseQty,
            String(sale.saleNo || sale.id),
            reason,
            { uom: String(item.uom || '') },
          )
        }
        returnItems.push({
          id: createId('srit'),
          saleItemId: item.id,
          productId: item.productId,
          name: item.name,
          quantity: qty,
          refundAmount: lineRefund,
          restock: Boolean(lineIn.restock),
        })
      }
      const returnNo = sequenceNext('SALE_RETURN', 'SRT', 6)
      sale.returnAmount = round2(Number(sale.returnAmount || 0) + refund)
      // Apply refund against open remaining / customer debt first.
      const saleRemaining = round2(Number(sale.remaining || 0))
      if (saleRemaining > 0 && refund > 0) {
        const applied = round2(Math.min(saleRemaining, refund))
        sale.remaining = round2(saleRemaining - applied)
        if (sale.customerId) {
          const customer = db.collections.customers.find(row => String(row.id) === String(sale.customerId))
          if (customer) customer.debtBalance = round2(Math.max(0, Number(customer.debtBalance || 0) - applied))
          for (const debt of db.collections.customerDebts) {
            if (String(debt.saleId) !== String(sale.id)) continue
            const rem = round2(Number(debt.remainingAmount || 0))
            const cut = round2(Math.min(rem, applied))
            debt.remainingAmount = round2(rem - cut)
            debt.originalAmount = round2(Math.max(0, Number(debt.originalAmount || 0) - cut))
            debt.status = Number(debt.remainingAmount) <= 0 ? 'PAID' : Number(debt.paidAmount) > 0 ? 'PARTIAL' : 'UNPAID'
          }
        }
      }
      if (Number(sale.returnAmount || 0) >= Number(sale.total || 0) - 1e-9) {
        sale.status = 'Returned'
        sale.remaining = 0
      }
      else if (Number(sale.remaining || 0) > 0) {
        sale.status = Number(sale.paidAmount || 0) > 0 ? 'Partial' : 'Unpaid'
      }
      else {
        sale.status = 'Paid'
      }
      addAudit('SALE', 'return', 'Sale', String(sale.saleNo), returnNo)
      // Persist the return document for the Customer Returns history report.
      db.collections.saleReturns.unshift({
        id: createId('srt'),
        returnNo,
        saleId: String(sale.id),
        saleNo: String(sale.saleNo || ''),
        createdAt: nowIso(),
        date: nowIso().slice(0, 10),
        customer: String(sale.customer || ''),
        itemCount: returnItems.length,
        refundAmount: refund,
        restockedQuantity: roundQty(returnItems.reduce(
          (sum, item) => sum + (item.restock ? Number(item.quantity) : 0), 0,
        )),
        reason,
        user: 'You',
      } as AppRecord)
      return mockLatency({
        id: createId('srt'),
        returnNo,
        saleId: String(sale.id),
        refundAmount: refund,
        reason,
        items: returnItems,
        createdAt: nowIso(),
      } as AppRecord)
    },

    async returnPurchase(input): Promise<AppRecord> {
      const db = useMockDb()
      const purchase = db.collections.stockIns.find(row => String(row.id) === String(input.stockInId))
      if (!purchase) throw new Error(`Purchase ${input.stockInId} not found`)
      const reason = String(input.reason || '').trim()
      if (!reason) throw new Error('Return reason is required')
      const items = (Array.isArray(purchase.items) ? purchase.items : []) as AppRecord[]
      if (!input.lines.length) throw new Error('Select at least one return quantity')
      let refund = 0
      const returnItems: AppRecord[] = []
      for (const lineIn of input.lines) {
        const qty = Number(lineIn.quantity)
        if (!Number.isFinite(qty) || qty <= 0) throw new Error('Return quantity must be greater than zero')
        const item = items.find(row => String(row.id) === String(lineIn.lineId))
        if (!item) throw new Error(`Unknown purchase line: ${lineIn.lineId}`)
        const received = Number(item.quantity || 0)
        const already = Number(item.returnedQuantity || 0)
        const returnable = roundQty(received - already)
        if (qty > returnable + 1e-9) throw new Error(`Return qty exceeds returnable for ${item.name}`)
        const product = db.collections.products.find(row => String(row.id) === String(item.productId))
        const available = Number(product?.quantity || 0)
        if (qty > available + 1e-9) throw new Error(`Insufficient stock to return ${item.name}`)
        const unit = round2(Number(item.price || item.unitCost || 0))
        const lineRefund = round2(unit * qty)
        refund = round2(refund + lineRefund)
        item.returnedQuantity = roundQty(already + qty)
        if (product) {
          product.quantity = roundQty(available - qty)
          if (Number(product.quantity) <= 10) product.status = 'Low Stock'
        }
        applyMovement(
          String(item.productId),
          String(item.name),
          'Purchase Return',
          -Math.abs(qty),
          String(purchase.purchaseNo || purchase.id),
          reason,
          { uom: String(item.uom || ''), unitCost: unit },
        )
        returnItems.push({
          id: createId('prit'),
          stockItemId: item.id,
          productId: item.productId,
          name: item.name,
          quantity: qty,
          unitCost: unit,
          lineRefund,
        })
      }
      const returnNo = sequenceNext('PURCHASE_RETURN', 'PRT', 6)
      // Reduce unpaid remaining on the purchase / supplier debt.
      const remaining = round2(Number(purchase.remaining || 0))
      const debtCut = round2(Math.min(remaining, refund))
      purchase.remaining = round2(remaining - debtCut)
      if (Number(purchase.remaining) <= 0) purchase.status = 'Completed'
      else purchase.status = 'Partial'
      if (purchase.supplierId && debtCut > 0) {
        const supplier = db.collections.suppliers.find(row => String(row.id) === String(purchase.supplierId))
        if (supplier) supplier.totalDebt = round2(Math.max(0, Number(supplier.totalDebt || 0) - debtCut))
        for (const debt of db.collections.supplierDebts) {
          if (String(debt.stockTransactionId) !== String(purchase.id)) continue
          const rem = round2(Number(debt.remainingAmount || 0))
          const cut = round2(Math.min(rem, debtCut))
          debt.remainingAmount = round2(rem - cut)
          debt.status = Number(debt.remainingAmount) <= 0 ? 'PAID' : Number(debt.paidAmount) > 0 ? 'PARTIAL' : 'UNPAID'
        }
      }
      purchase.returnAmount = round2(Number(purchase.returnAmount || 0) + refund)
      addAudit('STOCK', 'purchase_return', 'Stock In', String(purchase.purchaseNo), returnNo)
      // Persist the return document for the Supplier Returns history report.
      db.collections.purchaseReturns.unshift({
        id: createId('prt'),
        returnNo,
        stockInId: String(purchase.id),
        purchaseNo: String(purchase.purchaseNo || ''),
        createdAt: nowIso(),
        date: nowIso().slice(0, 10),
        supplier: String(purchase.supplier || ''),
        itemCount: returnItems.length,
        refundAmount: refund,
        debtReduction: debtCut,
        creditAmount: round2(refund - debtCut),
        reason,
        user: 'You',
      } as AppRecord)
      return mockLatency({
        id: createId('prt'),
        returnNo,
        stockInId: String(purchase.id),
        refundAmount: refund,
        reason,
        items: returnItems,
        createdAt: nowIso(),
      } as AppRecord)
    },
  }
}