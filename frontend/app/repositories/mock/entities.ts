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
  ProductCostHistoryRow,
  ProductHistoryRow,
  ProductSalePriceRow,
  ProductScopedQuery,
  SaleReceipt,
  SearchHitItem,
  SearchRepository,
  StockHistoryKind,
  StockQueryRepository,
} from '~/repositories/contracts/entities'
import { applyListQuery, createId, mockLatency, nowIso, paginateMeta } from '~/mocks/query'
import { mockInsert, mockRecords, mockRemove, mockUpdate, useMockDb } from '~/mocks/db'
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
        .map(row => ({
          id: String(row.id),
          date: dayKey(String(row.date || row.createdAt || '')),
          type: String(row.type ?? ''),
          quantity: Number(row.quantity ?? 0),
          reference: String(row.reference ?? ''),
          user: String(row.user ?? ''),
          note: String(row.note ?? ''),
          kind: historyKindOf(String(row.type ?? '')) ?? 'stock_in',
        }))
        .sort((a, b) => b.date.localeCompare(a.date))
      return mockLatency(paginateScopedRows(rows, query, ['type', 'reference', 'user', 'note']))
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

    async addSalePrice(productId, input): Promise<ProductSalePriceRow> {
      const salePrice = Number(input.salePrice)
      if (!Number.isFinite(salePrice) || salePrice <= 0) throw new Error('Sale price must be greater than zero')
      if (!String(input.date || '').trim()) throw new Error('Date is required')
      const product = mockRecords('products').find(row => String(row.id) === String(productId))
      if (!product) throw new Error(`Unknown product: ${productId}`)
      const existing = productSalePriceRows(productId)
      // Spec: exactly one POS-active version per product — retire the current one.
      for (const row of mockRecords('productSalePrices')) {
        if (String(row.productId) === String(productId) && row.isActive) row.isActive = false
      }
      const nextVersion = existing.reduce((max, row) => Math.max(max, row.version), 0) + 1
      const created = mockInsert('productSalePrices', {
        productId: String(productId),
        product: String(product.name ?? ''),
        salePrice: round2(salePrice),
        date: String(input.date).slice(0, 10),
        isActive: true,
        version: nextVersion,
      })
      copyActivePriceOntoProduct(productId, salePrice)
      return mockLatency({
        id: String(created.id),
        productId: String(created.productId),
        product: String(created.product ?? ''),
        salePrice: Number(created.salePrice ?? 0),
        date: String(created.date ?? '').slice(0, 10),
        isActive: created.isActive === true,
        version: Number(created.version ?? 0),
      })
    },

    async activateSalePrice(productId, priceId): Promise<ProductSalePriceRow> {
      const rows = mockRecords('productSalePrices')
      const target = rows.find(row => String(row.id) === String(priceId)
        && String(row.productId ?? '') === String(productId))
      if (!target) throw new Error(`Sale price ${priceId} not found for product ${productId}`)
      for (const row of rows) {
        if (String(row.productId ?? '') !== String(productId)) continue
        row.isActive = String(row.id) === String(priceId)
      }
      target.isActive = true
      copyActivePriceOntoProduct(productId, Number(target.salePrice ?? 0))
      return mockLatency({
        id: String(target.id),
        productId: String(target.productId),
        product: String(target.product ?? ''),
        salePrice: Number(target.salePrice ?? 0),
        date: String(target.date ?? '').slice(0, 10),
        isActive: true,
        version: Number(target.version ?? 0),
      })
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

function sumBetween(rows: AppRecord[], amountKey: string, start: string, end: string): number {
  return rows.reduce((sum, row) => {
    const day = dayKey(String(row.date || row.createdAt || ''))
    if (day >= start && day <= end) return sum + Number(row[amountKey] || 0)
    return sum
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
    const income = sumBetween(sales, 'paidAmount', start, end)
    // Expense = operating expenses only (spec: Finance Report expenses are
    // user-recorded rows; stock-in purchase amounts are not operating costs).
    const expense = sumBetween(db.collections.expenses, 'amount', start, end)
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
    extra: { uom?: string, unitCost?: number } = {},
  ) {
    const db = useMockDb()
    db.collections.stockMovements.unshift({
      id: createId('mv'),
      createdAt: nowIso(),
      date: nowIso().slice(0, 10),
      productId,
      product: productName,
      type,
      quantity,
      reference,
      user: 'Sokha Chan',
      note,
      ...(extra.uom ? { uom: extra.uom } : {}),
      ...(extra.unitCost != null ? { unitCost: extra.unitCost } : {}),
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
      const combinedDue = round2(total + depositTotal)
      const credit = input.paymentMethod === 'Credit'
      if ((credit || combinedDue > paidNow || depositTotal > 0) && !customer) {
        throw new Error('Credit sales require a customer')
      }
      if (paidNow > combinedDue) throw new Error('Paid amount exceeds the amount due')
      let left = paidNow
      const salePaid = round2(Math.min(left, total))
      left = round2(left - salePaid)
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
      })

      for (const item of items) {
        const product = db.collections.products.find(row => String(row.id) === String(item.productId))!
        // Stock-out in the base UOM: quantity × factorToBase.
        product.quantity = roundQty(Number(product.quantity) - Number(item.baseQuantity))
        applyMovement(String(product.id), String(product.name), 'Sale', -Number(item.baseQuantity), String(sale.saleNo), 'POS sale', { uom: String(item.uom || '') })
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
        })
      }
      if (customer && left > 0 && includedDebts.length) {
        for (const debt of includedDebts) {
          if (left <= 0) break
          const open = round2(Number(debt.remainingAmount || 0))
          if (open <= 0) continue
          const applied = round2(Math.min(open, left))
          const paid = round2(Number(debt.paidAmount || 0) + applied)
          const stillOpen = round2(open - applied)
          debt.paidAmount = paid
          debt.remainingAmount = stillOpen
          debt.status = stillOpen <= 0 ? 'PAID' : 'PARTIAL'
          left = round2(left - applied)
          customer.debtBalance = round2(Number(customer.debtBalance || 0) - applied)
          const priorSale = db.collections.sales.find(row => String(row.id) === String(debt.saleId))
          if (priorSale) {
            priorSale.paidAmount = round2(Number(priorSale.paidAmount || 0) + applied)
            priorSale.remaining = stillOpen
            priorSale.status = stillOpen <= 0 ? 'Paid' : Number(priorSale.paidAmount) > 0 ? 'Partial' : 'Unpaid'
          }
        }
      }
      addAudit('SALE', 'create', 'Sale', String(sale.saleNo), String(sale.saleNo))
      return mockLatency(sale)
    },

    async getSaleReceipt(saleId: string): Promise<SaleReceipt> {
      return mockLatency(saleReceipt(saleId))
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
      product.quantity = roundQty(Number(product.quantity) + signed)
      if (Number(product.quantity) <= 10) product.status = 'Low Stock'
      else if (String(product.status) === 'Low Stock') product.status = 'Active'
      applyMovement(String(product.id), String(product.name), meta.label, signed, reference, input.note ?? '', {
        uom: lineUomSymbol,
        ...(baseUnitCost != null ? { unitCost: baseUnitCost } : {}),
      })
      addAudit('STOCK', input.type, 'Product', String(product.code), reference)
      return mockLatency({
        id: createId('op'),
        reference,
        productId: String(product.id),
        product: String(product.name),
        type: meta.label,
        quantity: signed,
        uom: lineUomSymbol,
        factorToBase: factor,
        note: input.note ?? null,
        createdAt: nowIso(),
      } as AppRecord)
    },

    async payCustomerDebt(input): Promise<AppRecord> {
      const db = useMockDb()
      const customer = db.collections.customers.find(row => String(row.id) === String(input.customerId))
      if (!customer) throw new Error(`Unknown customer: ${input.customerId}`)
      const amount = round2(Number(input.amount || 0))
      if (amount <= 0) throw new Error('Payment amount must be greater than zero')
      if (amount > Number(customer.debtBalance || 0)) throw new Error('Payment exceeds the outstanding balance')
      customer.debtBalance = round2(Number(customer.debtBalance || 0) - amount)
      // Settle the customer's open debt documents oldest-first (immutable rows).
      let left = amount
      for (const debt of db.collections.customerDebts) {
        if (left <= 0) break
        if (String(debt.customerId) !== String(customer.id)) continue
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
      if (amount > Number(supplier.totalDebt || 0)) throw new Error('Payment exceeds the outstanding balance')
      supplier.totalDebt = round2(Number(supplier.totalDebt || 0) - amount)
      // Settle the supplier's open debt documents oldest-first (immutable rows).
      let left = amount
      for (const debt of db.collections.supplierDebts) {
        if (left <= 0) break
        if (String(debt.supplierId) !== String(supplier.id)) continue
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