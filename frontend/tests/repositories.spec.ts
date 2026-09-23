import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiEndpoints, CollectionEndpoints, isApiCollection } from '../app/utils/constants/api-endpoints'
import { createHttpEntityRepository, createHttpFinanceRepository, createHttpPosCommandRepository, createHttpStockQueryRepository } from '../app/repositories/http/entities'

interface CapturedRequest {
  method: string
  url: string
  query?: Record<string, unknown>
  body?: unknown
  options?: Record<string, unknown>
}

function withFakeApi(handler: (request: CapturedRequest) => unknown) {
  const captured: CapturedRequest[] = []
  const fakeApi = () => ({
    get: async (url: string, options?: { query?: Record<string, unknown> }) => {
      captured.push({ method: 'GET', url, query: options?.query })
      return handler(captured[captured.length - 1]!)
    },
    post: async (url: string, body?: unknown) => {
      captured.push({ method: 'POST', url, body })
      return handler(captured[captured.length - 1]!)
    },
    put: async (url: string, body?: unknown) => {
      captured.push({ method: 'PUT', url, body })
      return handler(captured[captured.length - 1]!)
    },
    patch: async (url: string, body?: unknown) => {
      captured.push({ method: 'PATCH', url, body })
      return handler(captured[captured.length - 1]!)
    },
    delete: async (url: string, options?: Record<string, unknown>) => {
      captured.push({ method: 'DELETE', url, options })
      return handler(captured[captured.length - 1]!)
    },
  })
  vi.stubGlobal('useApi', fakeApi)
  return captured
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('collection → endpoint mapping', () => {
  it('maps every frontend collection to its /api/v1 resource', () => {
    expect(CollectionEndpoints.categories).toBe('/api/v1/categories')
    expect(CollectionEndpoints.products).toBe('/api/v1/products')
    expect(CollectionEndpoints.suppliers).toBe('/api/v1/suppliers')
    expect(CollectionEndpoints.customers).toBe('/api/v1/customers')
    expect(CollectionEndpoints.sales).toBe('/api/v1/reports/sales')
    expect(CollectionEndpoints.stockMovements).toBe('/api/v1/stock/movements')
    expect(CollectionEndpoints.users).toBe('/api/v1/admin/users')
    expect(CollectionEndpoints.roles).toBe('/api/v1/admin/roles')
    expect(CollectionEndpoints.documentSequences).toBe('/api/v1/admin/document-sequences')
    expect(CollectionEndpoints.auditLogs).toBe('/api/v1/admin/audit-logs')
  })

  it('matches the spec §7 paths (spec: one create path per stock operation)', () => {
    expect(ApiEndpoints.POS_SALE_COMPLETE).toBe('/api/v1/pos/sales')
    expect(ApiEndpoints.STOCK_IN).toBe('/api/v1/stock/in')
    expect(ApiEndpoints.STOCK_ADJUST).toBe('/api/v1/stock/adjust')
    expect(ApiEndpoints.STOCK_DAMAGE).toBe('/api/v1/stock/damage')
    expect(ApiEndpoints.STOCK_EXPIRE).toBe('/api/v1/stock/expire')
    expect(ApiEndpoints.PRODUCT_SALE_PRICES('prd1')).toBe('/api/v1/products/prd1/sale-prices')
    expect(ApiEndpoints.PRODUCT_SALE_PRICE_ACTIVATE('prd1', 'psp1')).toBe('/api/v1/products/prd1/sale-prices/psp1/activate')
    expect(ApiEndpoints.PRODUCT_HISTORY('prd1')).toBe('/api/v1/stock/products/prd1/history')
    expect(ApiEndpoints.PRODUCT_COST_HISTORY('prd1')).toBe('/api/v1/stock/products/prd1/cost-history')
    expect(ApiEndpoints.POS_RECEIPT('sale1')).toBe('/api/v1/pos/sales/sale1/receipt')
    expect(ApiEndpoints.POS_PRODUCT_SEARCH).toBe('/api/v1/pos/products/search')
    expect(ApiEndpoints.POS_PRODUCT_BARCODE('8801001234501')).toBe('/api/v1/pos/products/barcode/8801001234501')
    expect(ApiEndpoints.CUSTOMER_DEBT_PAYMENTS('cus1', 'cdebt1')).toBe('/api/v1/customers/cus1/debts/cdebt1/payments')
    expect(ApiEndpoints.SUPPLIER_DEBT_PAYMENTS('sup1', 'sdebt1')).toBe('/api/v1/suppliers/sup1/debts/sdebt1/payments')
    expect(ApiEndpoints.FINANCE).toBe('/api/v1/reports/finance')
    expect(CollectionEndpoints.expenses).toBe('/api/v1/reports/finance/entries')
  })

  it('rejects unknown collections', () => {
    expect(isApiCollection('products')).toBe(true)
    expect(isApiCollection('motorcycles')).toBe(false)
    expect(isApiCollection('unknownCollection')).toBe(false)
  })
})

describe('http entity repository', () => {
  it('translates list queries into named parameters and keeps pagination meta', async () => {
    const captured = withFakeApi(() => ({
      data: [{ id: 'prd-001', code: 'P-001' }],
      meta: { page: 2, limit: 50, total: 123, totalPages: 3 },
    }))
    const repository = createHttpEntityRepository()
    const result = await repository.list('products', {
      q: 'widget',
      status: 'Active',
      startDate: '2026-01-01',
      endDate: '2026-02-01',
      page: 2,
      limit: 50,
    })

    expect(captured[0]?.url).toBe('/api/v1/products')
    expect(captured[0]?.query).toMatchObject({
      q: 'widget',
      status: 'Active',
      startDate: '2026-01-01',
      endDate: '2026-02-01',
      page: 2,
      limit: 50,
    })
    expect(result.items).toHaveLength(1)
    expect(result.items[0]?.id).toBe('prd-001')
    expect(result.meta?.total).toBe(123)
    expect(result.meta?.page).toBe(2)
  })

  it('maps UI camelCase list filters to backend snake_case query params', async () => {
    const captured = withFakeApi(() => ({ data: [], meta: { page: 1, limit: 100, total: 0 } }))
    const repository = createHttpEntityRepository()
    await repository.list('customerDebts', {
      customerId: 'cus-1',
      userId: 'usr-1',
      startDate: '2026-01-01',
      endDate: '2026-01-31',
      currency: 'USD',
    })
    expect(captured[0]?.query).toMatchObject({
      customer_id: 'cus-1',
      user_id: 'usr-1',
      startDate: '2026-01-01',
      endDate: '2026-01-31',
      currency: 'USD',
      limit: 100,
    })
    expect('customerId' in (captured[0]?.query ?? {})).toBe(false)
    expect('userId' in (captured[0]?.query ?? {})).toBe(false)
  })

  it('unwraps single-record envelopes on create', async () => {
    withFakeApi(() => ({ data: { id: 'cus-099', code: 'CUS-099' }, meta: { page: 1, limit: 1, total: 1 } }))
    const repository = createHttpEntityRepository()
    const created = await repository.create('customers', { code: 'CUS-099', name: 'New Customer' })
    expect(created.id).toBe('cus-099')
  })

  it('updates with PATCH, never PUT (spec §7)', async () => {
    const captured = withFakeApi(() => ({ data: { id: 'prd-001', name: 'Renamed' } }))
    const repository = createHttpEntityRepository()
    await repository.update('products', 'prd-001', { name: 'Renamed' })
    expect(captured[0]?.method).toBe('PATCH')
    expect(captured[0]?.url).toBe('/api/v1/products/prd-001')
  })

  it('normalizes the Active/Inactive UI dialect to canonical ACTIVE/INACTIVE', async () => {
    const captured = withFakeApi(() => ({ data: { id: 'cat-1', code: 'CAT-1', status: 'ACTIVE' } }))
    const repository = createHttpEntityRepository()

    await repository.create('categories', { name: 'Drinks', status: 'Active' })
    expect(captured[0]?.body).toMatchObject({ name: 'Drinks', status: 'ACTIVE' })

    await repository.update('categories', 'cat-1', { status: 'Inactive' })
    expect(captured[1]?.body).toMatchObject({ status: 'INACTIVE' })
  })

  it('maps setup-record status back to the Active/Inactive UI dialect', async () => {
    withFakeApi(() => ({
      data: [
        { id: 'cat-1', code: 'CAT-1', status: 'ACTIVE' },
        { id: 'cat-2', code: 'CAT-2', status: 'INACTIVE' },
      ],
      meta: { page: 1, limit: 100, total: 2 },
    }))
    const repository = createHttpEntityRepository()
    const result = await repository.list('categories')
    expect(result.items.map(row => row.status)).toEqual(['Active', 'Inactive'])
  })

  it('suppresses the generic API toast on delete so callers show the reason', async () => {
    const captured = withFakeApi(() => ({ data: { message: 'deleted' } }))
    const repository = createHttpEntityRepository()
    await repository.remove('uoms', 'uom-1')
    expect(captured[0]?.method).toBe('DELETE')
    expect(captured[0]?.url).toBe('/api/v1/uoms/uom-1')
    expect(captured[0]?.options).toMatchObject({ suppressErrorToast: true })
  })
})

describe('http POS/stock command endpoints (spec §7)', () => {
  it('posts checkout to /pos/sales with a snake_case body', async () => {
    const captured = withFakeApi(() => ({ data: { id: 'sale-1', invoice_no: 'INV-000001' } }))
    const commands = createHttpPosCommandRepository()
    await commands.completeSale({
      customerId: 'cus-1',
      customerName: null,
      items: [{
        productId: 'prd-1',
        quantity: 2,
        discountPercent: 10,
        uomId: 'uom-2',
        uomSymbol: 'box',
        factorToBase: 12,
      }],
      paymentMethod: 'Cash',
      paidAmount: 20,
      discount: 1,
      note: 'leave at desk',
      includedDebtIds: ['debt-9'],
      deliveryPrice: 2.5,
      deposit: 0,
      currency: 'KHR',
      exchangeRate: 41000,
    })
    expect(captured[0]?.method).toBe('POST')
    expect(captured[0]?.url).toBe('/api/v1/pos/sales')
    expect(captured[0]?.body).toMatchObject({
      customer_id: 'cus-1',
      payment_method: 'CASH',
      amount_received: 20,
      discount: 1,
      note: 'leave at desk',
      included_debt_ids: ['debt-9'],
      delivery_price: 2.5,
      deposit: 0,
      currency: 'KHR',
      exchange_rate: 41000,
      items: [{
        product_id: 'prd-1',
        quantity: 2,
        discount_percent: 10,
        uom_id: 'uom-2',
        uom_symbol: 'box',
        factor_to_base: 12,
      }],
    })
  })

  it('posts each stock operation to its own /stock path', async () => {
    const captured = withFakeApi(() => ({ data: { id: 'op-1' } }))
    const commands = createHttpPosCommandRepository()
    await commands.createStockOperation({ type: 'stock_in', productId: 'prd-1', quantity: 2, uomId: 'uom-2', uomSymbol: 'box', factorToBase: 12, unitCost: 6, supplierId: 'sup-1', paidAmount: 12 })
    await commands.createStockOperation({ type: 'adjustment', productId: 'prd-1', quantity: 3 })
    await commands.createStockOperation({ type: 'damage', productId: 'prd-1', quantity: 1 })
    await commands.createStockOperation({ type: 'expiry', productId: 'prd-1', quantity: 2 })
    expect(captured.map(request => request.url)).toEqual([
      '/api/v1/stock/in',
      '/api/v1/stock/operations',
      '/api/v1/stock/damage',
      '/api/v1/stock/expire',
    ])
    // Stock In = purchase: POST /stock/in takes a StockInRequest (items[],
    // supplier, paid amount) with line UOM conversion metadata.
    expect(captured[0]?.body).toMatchObject({
      supplier_id: 'sup-1',
      paid_amount: 12,
      payment_method: 'CASH',
      items: [{
        product_id: 'prd-1',
        quantity: 2,
        uom_id: 'uom-2',
        uom_symbol: 'box',
        factor_to_base: 12,
        unit_cost: 6,
      }],
    })
    // Adjustment is a signed delta handled by the quick-operation endpoint.
    expect(captured[1]?.body).toMatchObject({ type: 'adjustment', product_id: 'prd-1', quantity: 3 })
    // Damage/Expiry are absolute quantities inside an items[] envelope.
    expect(captured[2]?.body).toMatchObject({ items: [{ product_id: 'prd-1', quantity: 1 }] })
    expect(captured[3]?.body).toMatchObject({ items: [{ product_id: 'prd-1', quantity: 2 }] })
  })

  it('pays debts through the nested spec paths when the debt id is known', async () => {
    const captured = withFakeApi(() => ({ data: { id: 'pay-1' } }))
    const commands = createHttpPosCommandRepository()
    await commands.payCustomerDebt({ customerId: 'cus-1', debtId: 'debt-7', amount: 5, paymentMethod: 'Cash' })
    await commands.paySupplierDebt({ supplierId: 'sup-1', debtId: 'debt-8', amount: 6, paymentMethod: 'Cash' })
    expect(captured[0]?.url).toBe('/api/v1/customers/cus-1/debts/debt-7/payments')
    expect(captured[1]?.url).toBe('/api/v1/suppliers/sup-1/debts/debt-8/payments')
    expect(captured[0]?.body).toMatchObject({ amount: 5, payment_method: 'CASH' })
  })
})

describe('http stock query endpoints (spec §7 product-scoped)', () => {
  it('fetches product history from the product-scoped URL with a kind filter', async () => {
    const captured = withFakeApi(() => ({
      data: [{
        id: 'mv-1', date: '2026-02-01', type: 'Sale', quantity: -2,
        reference: 'SALE-00001', user: 'Sokha', note: 'POS sale',
      }],
      meta: { page: 1, limit: 20, total: 1, totalPages: 1 },
    }))
    const queries = createHttpStockQueryRepository()
    const result = await queries.listProductHistory('prd-1', { type: 'stock_out', limit: 20 })
    expect(captured[0]?.url).toBe('/api/v1/stock/products/prd-1/history')
    expect(captured[0]?.query).toMatchObject({ type: 'stock_out', limit: 20 })
    expect(result.items[0]).toMatchObject({
      id: 'mv-1',
      date: '2026-02-01',
      quantity: -2,
      reference: 'SALE-00001',
      user: 'Sokha',
      kind: 'stock_out',
    })
    expect(result.meta?.total).toBe(1)
  })

  it('adapts cost history and sale-price rows to camelCase', async () => {
    const captured = withFakeApi(handler => handler.url.includes('cost-history')
      ? { data: [{ id: 'lot-1', date: '2026-01-05', product: 'Coca-Cola', unit_cost: 0.5, quantity: 24, amount: 12, version: 1, document_no: 'PIN-00080' }] }
      : handler.method === 'POST' && handler.url.endsWith('/sale-prices/psp-2/activate')
        ? { data: { id: 'psp-2', product_id: 'prd-1', product: 'Coca-Cola', sale_price: 0.9, date: '2026-02-01', is_active: true, version: 2 } }
        : handler.method === 'POST' && handler.url.endsWith('/sale-prices')
        ? { data: { id: 'psp-3', product_id: 'prd-1', product: 'Coca-Cola', sale_price: 1.1, date: '2026-03-01', is_active: true, version: 3 } }
        : { data: [{ id: 'psp-2', product_id: 'prd-1', product: 'Coca-Cola', sale_price: 0.9, date: '2026-02-01', is_active: true, version: 2 }] })
    const queries = createHttpStockQueryRepository()

    const costs = await queries.listProductCostHistory('prd-1')
    expect(captured[0]?.url).toBe('/api/v1/stock/products/prd-1/cost-history')
    expect(costs.items[0]).toMatchObject({ unitCost: 0.5, quantity: 24, amount: 12, version: 1, documentNo: 'PIN-00080' })

    const prices = await queries.listSalePrices('prd-1')
    expect(captured[1]?.url).toBe('/api/v1/products/prd-1/sale-prices')
    expect(prices.items[0]).toMatchObject({ productId: 'prd-1', salePrice: 0.9, isActive: true, version: 2 })

    const added = await queries.addSalePrice('prd-1', { date: '2026-03-01', salePrice: 1.1 })
    expect(captured[2]?.method).toBe('POST')
    expect(captured[2]?.url).toBe('/api/v1/products/prd-1/sale-prices')
    expect(captured[2]?.body).toMatchObject({ date: '2026-03-01', sale_price: 1.1 })
    expect(added.salePrice).toBe(1.1) // adapted response body

    const activated = await queries.activateSalePrice('prd-1', 'psp-2')
    expect(captured[3]?.method).toBe('POST')
    expect(captured[3]?.url).toBe('/api/v1/products/prd-1/sale-prices/psp-2/activate')
    expect(activated.isActive).toBe(true)
  })
})

describe('http finance endpoints (spec §7 reports)', () => {
  it('reads the canonical finance path and maps snake_case entry rows', async () => {
    const captured = withFakeApi(handler => handler.url === '/api/v1/reports/finance'
      ? { data: { income: 100, expense: 40, net: 60, outstanding: 25 } }
      : handler.url === '/api/v1/reports/finance/entries'
        ? { data: [{
            id: 'e-1', date: '2026-02-01', type: 'EXPENSE', category: 'Rent',
            description: 'Shop rent', amount: 40, payment_method: 'Cash',
            created_by_name: 'Sokha', reference: '',
          }] }
        : { data: [] })
    const repository = createHttpFinanceRepository()

    const summary = await repository.financeSummary('2026-02-01', '2026-02-28')
    expect(captured[0]?.url).toBe('/api/v1/reports/finance')
    expect(summary).toMatchObject({ income: 100, expense: 40, net: 60, outstanding: 25 })

    const entries = await repository.entries('2026-02-01', '2026-02-28')
    expect(captured[1]?.url).toBe('/api/v1/reports/finance/entries')
    expect(entries[0]).toMatchObject({
      type: 'expense',
      category: 'Rent',
      paymentMethod: 'Cash',
      user: 'Sokha',
    })
  })

  it('maps the split profit_and_loss and cash_flow summary views', async () => {
    withFakeApi(() => ({
      data: {
        total_sales: 100,
        total_expense: 40,
        net_result: 60,
        outstanding: 25,
        report_currency: 'USD',
        profit_and_loss: {
          gross_sales: 120, sale_returns: 20, net_sales: 100, cost_of_goods_sold: 40,
          gross_profit: 60, operating_expenses: 10, stock_damage_loss: 2,
          stock_expire_loss: 1, operating_profit: 47,
        },
        cash_flow: {
          sale_receipts: 90, debt_collections: 5, supplier_refunds_received: 0,
          total_inflow: 95, supplier_payments: 30, customer_refunds_paid: 8,
          operating_expenses: 10, total_outflow: 48, net_cash_flow: 47,
        },
      },
    }))
    const repository = createHttpFinanceRepository()
    const summary = await repository.financeSummary()
    expect(summary.reportCurrency).toBe('USD')
    expect(summary.profitAndLoss).toMatchObject({ netSales: 100, grossProfit: 60, operatingProfit: 47 })
    expect(summary.cashFlow).toMatchObject({ totalInflow: 95, totalOutflow: 48, netCashFlow: 47 })
  })

  it('creates expenses via POST /reports/finance/expenses with snake_case body', async () => {
    const captured = withFakeApi(() => ({
      data: { id: 'exp-1', date: '2026-02-01', type: 'expense', category: 'Rent', description: 'Rent', amount: 90, payment_method: 'Cash', created_by_name: 'Sokha' },
    }))
    const repository = createHttpFinanceRepository()
    const created = await repository.createExpense({
      date: '2026-02-01',
      category: 'Rent',
      description: 'Rent',
      amount: 90,
      paymentMethod: 'Cash',
    })
    expect(captured[0]?.url).toBe('/api/v1/reports/finance/expenses')
    expect(captured[0]?.body).toMatchObject({ date: '2026-02-01', payment_method: 'CASH', amount: 90 })
    expect(created).toMatchObject({ type: 'expense', paymentMethod: 'Cash', user: 'Sokha' })
  })
})

describe('complete purchase (Stock In) commands', () => {
  it('posts the whole purchase basket as ONE /stock/in request with every line', async () => {
    const captured = withFakeApi(() => ({ data: { id: 'sti-1', document_no: 'STI-000042' } }))
    const commands = createHttpPosCommandRepository()
    const record = await commands.createPurchase({
      lines: [
        { productId: 'prd-1', quantity: 2, uomId: 'uom-2', uomSymbol: 'box', factorToBase: 12, unitCost: 6 },
        { productId: 'prd-2', quantity: 5, unitCost: 1.5 },
      ],
      supplierId: 'sup-1',
      paidAmount: 10,
      paymentMethod: 'BANK_QR',
      note: 'weekly order',
    })
    expect(captured).toHaveLength(1)
    expect(captured[0]?.url).toBe('/api/v1/stock/in')
    expect(captured[0]?.body).toMatchObject({
      supplier_id: 'sup-1',
      paid_amount: 10,
      payment_method: 'BANK_QR',
      note: 'weekly order',
      items: [
        { product_id: 'prd-1', quantity: 2, uom_id: 'uom-2', uom_symbol: 'box', factor_to_base: 12, unit_cost: 6 },
        { product_id: 'prd-2', quantity: 5, unit_cost: 1.5 },
      ],
    })
    expect(record).toMatchObject({ id: 'sti-1' })
  })

  it('sends document currency and exchange rate with the purchase', async () => {
    const captured = withFakeApi(() => ({ data: { id: 'sti-4' } }))
    const commands = createHttpPosCommandRepository()
    await commands.createPurchase({
      lines: [{ productId: 'prd-1', quantity: 1, unitCost: 410000 }],
      currency: 'KHR',
      exchangeRate: 41000,
    })
    expect(captured[0]?.body).toMatchObject({ currency: 'KHR', exchange_rate: 41000 })
  })

  it('sends document-level discount and tax with the purchase', async () => {
    const captured = withFakeApi(() => ({ data: { id: 'sti-3' } }))
    const commands = createHttpPosCommandRepository()
    await commands.createPurchase({
      lines: [{ productId: 'prd-1', quantity: 10, unitCost: 2 }],
      supplierId: 'sup-1',
      paidAmount: 9,
      discountAmount: 5,
      taxAmount: 4,
    })
    expect(captured[0]?.body).toMatchObject({
      discount_amount: 5,
      tax_amount: 4,
      paid_amount: 9,
    })
  })

  it('omits optional purchase fields instead of sending nulls/zeroes', async () => {
    const captured = withFakeApi(() => ({ data: { id: 'sti-2' } }))
    const commands = createHttpPosCommandRepository()
    await commands.createPurchase({
      lines: [{ productId: 'prd-1', quantity: 1 }],
    })
    const body = captured[0]?.body as Record<string, unknown>
    expect('supplier_id' in body).toBe(false)
    expect('uom_id' in (body.items as Array<Record<string, unknown>>)[0]!).toBe(false)
    expect('unit_cost' in (body.items as Array<Record<string, unknown>>)[0]!).toBe(false)
  })

  it('looks a product up by exact barcode and normalizes the response', async () => {
    const captured = withFakeApi(() => ({
      data: { id: 'prd-9', barcode: '8801001234501', name: 'Glove', selling_price: 3.15 },
    }))
    const commands = createHttpPosCommandRepository()
    const product = await commands.getProductByBarcode('8801001234501')
    expect(captured[0]?.method).toBe('GET')
    expect(captured[0]?.url).toBe('/api/v1/pos/products/barcode/8801001234501')
    expect(product).toMatchObject({ id: 'prd-9', barcode: '8801001234501', salePrice: 3.15 })
  })

  it('returns null when no active product matches the scanned barcode (404)', async () => {
    withFakeApi(() => {
      throw new Error('API Error: 404')
    })
    const commands = createHttpPosCommandRepository()
    await expect(commands.getProductByBarcode('nope')).resolves.toBeNull()
  })
})
