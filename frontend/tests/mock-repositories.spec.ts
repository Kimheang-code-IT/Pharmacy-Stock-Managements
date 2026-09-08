import { describe, expect, it } from 'vitest'
import {
  createMockEntityRepository,
  createMockFinanceRepository,
  createMockPosRepository,
  createMockStockQueryRepository,
} from '../app/repositories/mock/entities'
import { mockRecords } from '../app/mocks/db'
import {
  convertToBase,
  multiplyDecimalSafe,
  normalizeUomConversions,
} from '../app/utils/stock/uom-conversions'

describe('mock entity repository', () => {
  it('lists seeded collections with pagination meta', async () => {
    const repository = createMockEntityRepository()
    const result = await repository.list('categories')
    expect(result.items.length).toBeGreaterThan(0)
    expect(result.meta?.total).toBe(result.items.length)
    expect(result.items[0]).toMatchObject({ id: expect.any(String), name: expect.any(String) })
  })

  it('creates, updates and removes records in-memory', async () => {
    const repository = createMockEntityRepository()
    const created = await repository.create('categories', { code: 'CAT-TEST', name: 'Test Category', status: 'Active' })
    expect(created.id).toBeTruthy()

    const updated = await repository.update('categories', created.id, { name: 'Renamed Category' })
    expect(updated.name).toBe('Renamed Category')

    await repository.remove('categories', created.id)
    const after = await repository.get('categories', created.id)
    expect(after).toBeNull()
  })

  it('supports brands CRUD and lists only active brands for product selectors', async () => {
    const repository = createMockEntityRepository()
    const created = await repository.create('brands', { code: 'BR-TEST', name: 'Test Brand', status: 'Active' })
    expect(created.id).toBeTruthy()

    const updated = await repository.update('brands', created.id, { name: 'Renamed Brand' })
    expect(updated.name).toBe('Renamed Brand')

    const activeOnly = await repository.list('brands', { status: 'Active' })
    expect(activeOnly.items.some(row => String(row.id) === created.id && row.status === 'Active')).toBe(true)
    expect(activeOnly.items.every(row => row.status === 'Active')).toBe(true)

    await repository.setStatus('brands', created.id, 'Inactive')
    const afterDisable = await repository.list('brands', { status: 'Active' })
    expect(afterDisable.items.some(row => String(row.id) === created.id)).toBe(false)

    await repository.remove('brands', created.id)
    const after = await repository.get('brands', created.id)
    expect(after).toBeNull()
  })

  it('does not write outstanding debt from customer or supplier Setup forms', async () => {
    const repository = createMockEntityRepository()
    const customer = await repository.create('customers', {
      name: 'Debt Form Test',
      phone: '012 000 000',
      location: 'Phnom Penh',
      status: 'Active',
      debtBalance: 1850,
    })
    expect(Number(customer.debtBalance)).toBe(0)

    const supplier = await repository.create('suppliers', {
      name: 'Debt Form Supplier',
      phone: '012 000 001',
      location: 'Phnom Penh',
      status: 'Active',
      totalDebt: 1850,
    })
    expect(Number(supplier.totalDebt)).toBe(0)

    const seeded = mockRecords('customers').find(row => row.id === 'cus1')!
    const debtBefore = Number(seeded.debtBalance || 0)
    const updated = await repository.update('customers', 'cus1', {
      name: String(seeded.name),
      phone: String(seeded.phone),
      location: String(seeded.location || ''),
      debtBalance: 1,
    })
    expect(Number(updated.debtBalance)).toBe(debtBefore)
  })
})

describe('mock dashboard summary', () => {
  it('exposes the full Business Summary snapshot fields (spec 2.1.1)', async () => {
    const repository = createMockFinanceRepository()
    // Wide range so period-based metrics cover every seeded movement.
    const summary = await repository.dashboard('2000-01-01', '2100-01-01')

    // KPI row: exactly four cards worth of data (Sales This Month lives in summary, not KPI).
    expect(summary.salesToday).toBeGreaterThanOrEqual(0)
    expect(summary.income).toBeGreaterThanOrEqual(0)
    expect(summary.expense).toBeGreaterThanOrEqual(0)
    expect(summary.customerDebt + summary.supplierDebt).toBeGreaterThanOrEqual(0)

    // Income = paid/confirmed sales in range; Expense = operating expenses only
    // (spec) — stock-in purchase amounts are never expense rows.
    const paidIncome = mockRecords('sales')
      .filter(row => ['Paid', 'Partial'].includes(String(row.status)))
      .reduce((sum, row) => sum + Number(row.paidAmount || 0), 0)
    expect(summary.income).toBeCloseTo(paidIncome, 2)
    const operatingExpense = mockRecords('expenses')
      .reduce((sum, row) => sum + Number(row.amount || 0), 0)
    expect(summary.expense).toBeCloseTo(operatingExpense, 2)

    // Sales & money.
    expect(summary.salesThisMonth).toBeGreaterThan(0)
    expect(summary.salesThisMonthAmount).toBeGreaterThan(0)
    expect(summary.salesTodayAmount).toBeGreaterThanOrEqual(0)
    // Same rule as the backend: gross = income - COGS, net = gross - losses.
    expect(summary.grossProfit).not.toBeNull()
    expect(summary.netIncome).not.toBeNull()
    expect(summary.netIncome).toBeCloseTo(summary.grossProfit! - summary.damageLoss - summary.expiryLoss, 2)

    // Debts.
    const customerDebt = mockRecords('customers').reduce((sum, row) => sum + Number(row.debtBalance || 0), 0)
    expect(summary.customerDebt).toBeCloseTo(customerDebt, 2)

    // Stock health.
    const products = mockRecords('products')
    expect(summary.productsTotal).toBe(products.length)
    expect(summary.lowStockCount).toBe(products.filter(row => Number(row.quantity) <= 10).length)
    expect(summary.outOfStockCount).toBe(products.filter(row => Number(row.quantity) <= 0).length)

    // Damage/expiry loss valued at product cost price from movements.
    const productsById = new Map(products.map(row => [String(row.id), Number(row.costPrice || 0)]))
    const movementLoss = (type: string) => mockRecords('stockMovements')
      .filter(row => String(row.type) === type)
      .reduce((sum, row) => sum + Math.abs(Number(row.quantity || 0)) * (productsById.get(String(row.productId)) || 0), 0)
    expect(summary.damageLoss).toBeGreaterThan(0)
    expect(summary.damageLoss).toBeCloseTo(movementLoss('Damage'), 2)
    expect(summary.expiryLoss).toBeGreaterThan(0)
    expect(summary.expiryLoss).toBeCloseTo(movementLoss('Expiry'), 2)

    // Operations: delivery notes not yet Delivered/Cancelled.
    const pending = mockRecords('deliveryNotes')
      .filter(note => !['Delivered', 'Cancelled'].includes(String(note.status || 'Draft'))).length
    expect(summary.pendingDeliveryNotes).toBe(pending)

    // Month-to-date amounts only include sales inside the calendar month.
    const monthStart = new Date().toISOString().slice(0, 7)
    const monthAmount = mockRecords('sales')
      .filter(sale => String(sale.date || sale.createdAt || '').slice(0, 7) === monthStart)
      .reduce((sum, sale) => sum + Number(sale.paidAmount || 0), 0)
    expect(summary.salesThisMonthAmount).toBeCloseTo(monthAmount, 2)
  })
})

describe('mock debt report rows (spec 2.1.10)', () => {
  it('derives invoice-level customer debt rows from open credit sales', () => {
    const debts = mockRecords('customerDebts')
    const openCreditSales = mockRecords('sales')
      .filter(sale => Number(sale.remaining) > 0 || sale.paymentMethod === 'Credit')
    expect(openCreditSales.length).toBeGreaterThan(0)
    expect(debts).toHaveLength(openCreditSales.length)
    for (const row of debts) {
      expect(String(row.invoiceNo)).toBeTruthy()
      expect(String(row.date)).toBeTruthy()
      expect(Number(row.invoiceTotal)).toBeGreaterThan(0)
      expect(['UNPAID', 'PARTIAL', 'PAID']).toContain(row.status)
    }
    // Newest first, matching the report ordering.
    const dates = debts.map(row => String(row.date))
    expect([...dates].sort().reverse()).toEqual(dates)
  })

  it('derives document-level supplier debt rows from partially paid purchases', () => {
    const debts = mockRecords('supplierDebts')
    const openPurchases = mockRecords('stockIns').filter(row => Number(row.remaining) > 0)
    expect(openPurchases.length).toBeGreaterThan(0)
    expect(debts).toHaveLength(openPurchases.length)
    for (const row of debts) {
      expect(String(row.purchaseNo)).toBeTruthy()
      expect(String(row.date)).toBeTruthy()
      expect(Number(row.remainingAmount)).toBeGreaterThan(0)
      expect(['UNPAID', 'PARTIAL', 'PAID']).toContain(row.status)
    }
  })

  it('records a debt document on credit sale and settles debt rows on payment', async () => {
    const commands = createMockPosRepository()
    const customer = mockRecords('customers').find(row => row.id === 'cus1')!
    const product = mockRecords('products')[0]!

    const sale = await commands.completeSale({
      customerId: 'cus1',
      customerName: null,
      items: [{ productId: String(product.id), quantity: 1 }],
      paymentMethod: 'Credit',
      paidAmount: 0,
    })
    const created = mockRecords('customerDebts')
      .find(row => String(row.invoiceNo) === String(sale.invoiceNo || sale.saleNo))
    expect(created).toBeTruthy()
    expect(created!.status).toBe('UNPAID')
    expect(Number(created!.remainingAmount)).toBe(Number(sale.remaining))

    const openDebts = mockRecords('customerDebts')
      .filter(row => String(row.customerId) === 'cus1' && Number(row.remainingAmount) > 0)
    customer.debtBalance = openDebts.reduce((sum, row) => sum + Number(row.remainingAmount || 0), 0)
    await commands.payCustomerDebt({
      customerId: 'cus1',
      amount: Number(customer.debtBalance),
      paymentMethod: 'Cash',
    })
    const stillOpen = mockRecords('customerDebts')
      .filter(row => String(row.customerId) === 'cus1' && row.status !== 'PAID')
    expect(stillOpen).toHaveLength(0)
    expect(Number(created!.remainingAmount)).toBe(0)
  })
})

describe('mock POS commands', () => {
  it('completes a credit sale atomically: sale, movements, product quantity, debt and sequence', async () => {
    const commands = createMockPosRepository()

    const productsBefore = mockRecords('products')
    const product = productsBefore[0]!
    const quantityBefore = Number(product.quantity)
    const saleCountBefore = mockRecords('sales').length
    const movementCountBefore = mockRecords('stockMovements').length
    const saleSeqBefore = mockRecords('documentSequences').find(seq => seq.documentType === 'SALE')!.lastValue
    const debtBefore = Number(mockRecords('customers').find(row => row.id === 'cus1')!.debtBalance || 0)

    const sale = await commands.completeSale({
      customerId: 'cus1',
      customerName: null,
      items: [{ productId: String(product.id), quantity: 2 }],
      paymentMethod: 'Credit',
      paidAmount: 0,
    })

    expect(sale.saleNo).toBe(`SALE-${String(Number(saleSeqBefore) + 1).padStart(5, '0')}`)
    expect(mockRecords('sales')).toHaveLength(saleCountBefore + 1)
    expect(mockRecords('stockMovements')).toHaveLength(movementCountBefore + 1)
    expect(Number(product.quantity)).toBe(quantityBefore - 2)

    const customer = mockRecords('customers').find(row => row.id === 'cus1')!
    expect(Number(customer.debtBalance)).toBe(debtBefore + Number(sale.remaining))
  })

  it('defaults the line price to the product salePrice when unitPrice is omitted', async () => {
    const commands = createMockPosRepository()
    const product = mockRecords('products').find(row => String(row.id) === 'prd1')!
    const before = Number(product.quantity)

    const sale = await commands.completeSale({
      items: [{ productId: 'prd1', quantity: 3 }],
      paymentMethod: 'Cash',
      paidAmount: Number(product.salePrice) * 3,
    })
    const line = (sale.items as Array<Record<string, unknown>>)[0]!
    expect(Number(line.price)).toBe(Number(product.salePrice))
    expect(Number(sale.total)).toBeCloseTo(Number(product.salePrice) * 3, 2)
    expect(Number(product.quantity)).toBe(before - 3)
  })

  it('adds deliveryPrice into the sale total', async () => {
    const commands = createMockPosRepository()
    const product = mockRecords('products').find(row => String(row.id) === 'prd1')!
    const salePrice = Number(product.salePrice)

    const sale = await commands.completeSale({
      items: [{ productId: String(product.id), quantity: 1 }],
      paymentMethod: 'Cash',
      paidAmount: salePrice + 2.5,
      deliveryPrice: 2.5,
    })
    expect(Number(sale.deliveryPrice)).toBe(2.5)
    expect(Number(sale.total)).toBeCloseTo(salePrice + 2.5, 2)
    expect(Number(sale.paidAmount)).toBeCloseTo(salePrice + 2.5, 2)
    expect(String(sale.status)).toBe('Paid')
  })

  it('returns a receipt payload derived from the stored sale', async () => {
    const commands = createMockPosRepository()
    const product = mockRecords('products').find(row => String(row.id) === 'prd1')!
    const sale = await commands.completeSale({
      items: [{ productId: String(product.id), quantity: 2 }],
      paymentMethod: 'Cash',
      paidAmount: Number(product.salePrice) * 2,
    })
    const receipt = await commands.getSaleReceipt(String(sale.id))
    expect(receipt.invoiceNo).toBe(String(sale.invoiceNo || sale.saleNo))
    expect(receipt.items).toHaveLength(1)
    expect(receipt.items[0]).toMatchObject({
      name: String(product.name),
      quantity: 2,
      unitPrice: Number(product.salePrice),
    })
    expect(receipt.total).toBeCloseTo(Number(product.salePrice) * 2, 2)
  })

  it('records a customer sale return with restock and rejects over-return', async () => {
    const commands = createMockPosRepository()
    const product = mockRecords('products').find(row => String(row.id) === 'prd1')!
    const beforeQty = Number(product.quantity)
    const sale = await commands.completeSale({
      items: [{ productId: String(product.id), quantity: 2 }],
      paymentMethod: 'Cash',
      paidAmount: Number(product.salePrice) * 2,
    })
    const lineId = String((sale.items as Array<{ id: string }>)[0]!.id)
    const afterSaleQty = Number(product.quantity)

    await expect(commands.returnSale({
      saleId: String(sale.id),
      reason: 'Damaged bottle',
      lines: [{ lineId, quantity: 5, restock: true }],
    })).rejects.toThrow(/returnable/i)

    const result = await commands.returnSale({
      saleId: String(sale.id),
      reason: 'Customer changed mind',
      lines: [{ lineId, quantity: 1, restock: true }],
    })
    expect(String(result.returnNo || '')).toMatch(/^SRT-/)
    expect(Number(result.refundAmount)).toBeCloseTo(Number(product.salePrice), 2)
    expect(Number(product.quantity)).toBe(afterSaleQty + 1)
    expect(Number((sale.items as Array<{ returnedQuantity?: number }>)[0]!.returnedQuantity)).toBe(1)
    expect(mockRecords('stockMovements')[0]).toMatchObject({ type: 'Sale Return', quantity: 1 })
    expect(beforeQty).toBeGreaterThan(afterSaleQty)
  })

  it('records a purchase return to supplier and stocks out', async () => {
    const commands = createMockPosRepository()
    const purchase = mockRecords('stockIns')[0]!
    const item = (purchase.items as Array<Record<string, unknown>>)[0]!
    const product = mockRecords('products').find(row => String(row.id) === String(item.productId))!
    const beforeQty = Number(product.quantity)
    const returnQty = 1

    const result = await commands.returnPurchase({
      stockInId: String(purchase.id),
      reason: 'Wrong shipment',
      lines: [{ lineId: String(item.id), quantity: returnQty }],
    })
    expect(String(result.returnNo || '')).toMatch(/^PRT-/)
    expect(Number(product.quantity)).toBe(beforeQty - returnQty)
    expect(Number(item.returnedQuantity)).toBe(returnQty)
    expect(mockRecords('stockMovements')[0]).toMatchObject({ type: 'Purchase Return' })
  })

  it('rejects customer debt overpayment and applies valid payments', async () => {
    const commands = createMockPosRepository()
    const customer = mockRecords('customers').find(row => row.id === 'cus1')!
    customer.debtBalance = 100

    await expect(commands.payCustomerDebt({
      customerId: 'cus1',
      amount: 150,
      paymentMethod: 'Cash',
    })).rejects.toThrow(/exceeds/i)

    await commands.payCustomerDebt({ customerId: 'cus1', amount: 40, paymentMethod: 'Cash' })
    expect(Number(customer.debtBalance)).toBe(60)
    expect(mockRecords('customerDebtPayments').some(row => Number(row.amount) === 40)).toBe(true)
  })

  it('applies damage operations as negative stock movements', async () => {
    const commands = createMockPosRepository()
    const product = mockRecords('products')[0]!
    const quantityBefore = Number(product.quantity)
    const movementCountBefore = mockRecords('stockMovements').length

    const record = await commands.createStockOperation({
      type: 'damage',
      productId: String(product.id),
      quantity: 3,
      note: 'Broken',
    })

    expect(Number(record.quantity)).toBe(-3)
    expect(Number(product.quantity)).toBe(quantityBefore - 3)
    expect(mockRecords('stockMovements')).toHaveLength(movementCountBefore + 1)
  })

  it('audits completed sales', async () => {
    const commands = createMockPosRepository()
    const product = mockRecords('products')[0]!
    const auditCountBefore = mockRecords('auditLogs').length
    await commands.completeSale({
      customerId: null,
      customerName: null,
      items: [{ productId: String(product.id), quantity: 1 }],
      paymentMethod: 'Cash',
      paidAmount: Number(product.salePrice),
    })
    expect(mockRecords('auditLogs')).toHaveLength(auditCountBefore + 1)
  })

  it('settles selected open invoices from paid now on complete sale', async () => {
    const commands = createMockPosRepository()
    const product = mockRecords('products')[0]!
    const salePrice = Number(product.salePrice)

    const creditSale = await commands.completeSale({
      customerId: 'cus1',
      customerName: null,
      items: [{ productId: String(product.id), quantity: 1 }],
      paymentMethod: 'Credit',
      paidAmount: 0,
    })
    const debt = mockRecords('customerDebts').find(row => String(row.saleId) === String(creditSale.id))
    expect(debt).toBeTruthy()
    const openBefore = Number(debt!.remainingAmount)
    expect(openBefore).toBeGreaterThan(0)
    const customer = mockRecords('customers').find(row => row.id === 'cus1')!
    const debtBalanceBefore = Number(customer.debtBalance || 0)

    const sale = await commands.completeSale({
      customerId: 'cus1',
      customerName: null,
      items: [{ productId: String(product.id), quantity: 1 }],
      paymentMethod: 'Cash',
      paidAmount: salePrice + openBefore,
      includedDebtIds: [String(debt!.id)],
    })

    expect(Number(sale.remaining)).toBe(0)
    expect(Number(debt!.remainingAmount)).toBe(0)
    expect(debt!.status).toBe('PAID')
    expect(Number(customer.debtBalance)).toBeCloseTo(debtBalanceBefore - openBefore, 2)
  })
})

describe('mock finance entries (Finance Report table)', () => {
  it('derives income rows from paid sales and lists expense rows', async () => {
    const repository = createMockFinanceRepository()
    const entries = await repository.entries('2000-01-01', '2100-01-01')

    const income = entries.filter(row => row.type === 'income')
    const expense = entries.filter(row => row.type === 'expense')

    expect(income.length).toBeGreaterThan(0)
    expect(expense.length).toBeGreaterThan(0)

    // Income mirrors confirmed sales paid amounts, one row per paid sale.
    const paidSales = mockRecords('sales').filter(
      row => ['Paid', 'Partial'].includes(String(row.status)) && Number(row.paidAmount || 0) > 0,
    )
    expect(income).toHaveLength(paidSales.length)
    const incomeTotal = income.reduce((sum, row) => sum + Number(row.amount), 0)
    const paidTotal = paidSales.reduce((sum, row) => sum + Number(row.paidAmount), 0)
    expect(incomeTotal).toBeCloseTo(paidTotal, 2)
    for (const row of income) {
      expect(row.reference).toMatch(/^SALE-/)
      expect(row.user).toBeTruthy()
      expect(row.paymentMethod).toBeTruthy()
    }

    // Expenses carry category/description and stay user-managed rows.
    for (const row of expense) {
      expect(row.category).toBeTruthy()
      expect(Number(row.amount)).toBeGreaterThan(0)
    }

    // Sorted newest first for the ledger table.
    for (let i = 1; i < entries.length; i += 1) {
      expect(entries[i - 1]!.date >= entries[i]!.date).toBe(true)
    }
  })

  it('filters entries by date range', async () => {
    const repository = createMockFinanceRepository()
    const sales = mockRecords('sales')
    const firstSale = sales.find(row => Number(row.paidAmount || 0) > 0)!
    const day = String(firstSale.date || firstSale.createdAt).slice(0, 10)

    const dayEntries = await repository.entries(day, day)
    expect(dayEntries.length).toBeGreaterThan(0)
    expect(dayEntries.every(row => row.date === day)).toBe(true)

    const emptyDay = await repository.entries('1990-01-01', '1990-01-02')
    expect(emptyDay).toHaveLength(0)
  })

  it('creates an expense that appears in entries and lowers the net result', async () => {
    const repository = createMockFinanceRepository()
    const start = '2000-01-01'
    const end = '2100-01-01'
    const before = await repository.entries(start, end)
    const netBefore = before.reduce(
      (sum, row) => sum + (row.type === 'income' ? Number(row.amount) : -Number(row.amount)),
      0,
    )

    const created = await repository.createExpense({
      date: '2100-01-01',
      category: 'Utilities',
      description: 'Test expense entry',
      amount: 25.5,
      paymentMethod: 'Cash',
      reference: 'EXP-TEST-1',
    })

    expect(created.type).toBe('expense')
    expect(Number(created.amount)).toBeCloseTo(25.5, 2)
    expect(mockRecords('expenses').some(row => String(row.reference) === 'EXP-TEST-1')).toBe(true)

    const after = await repository.entries(start, end)
    const netAfter = after.reduce(
      (sum, row) => sum + (row.type === 'income' ? Number(row.amount) : -Number(row.amount)),
      0,
    )
    expect(netAfter).toBeCloseTo(netBefore - 25.5, 2)
    expect(after.some(row => row.id === created.id)).toBe(true)
  })

  it('rejects expenses without a positive amount or category', async () => {
    const repository = createMockFinanceRepository()
    const expensesBefore = mockRecords('expenses').length

    await expect(repository.createExpense({
      date: '2100-01-01',
      category: 'Rent',
      description: 'Zero amount',
      amount: 0,
      paymentMethod: 'Cash',
    })).rejects.toThrow(/greater than zero/i)

    await expect(repository.createExpense({
      date: '2100-01-01',
      category: '  ',
      description: 'No category',
      amount: 10,
      paymentMethod: 'Cash',
    })).rejects.toThrow(/category/i)

    expect(mockRecords('expenses')).toHaveLength(expensesBefore)
  })
})

describe('sale price versions (spec: product_sale_prices)', () => {
  it('seeds exactly one POS-active version per product, matching product.salePrice', () => {
    const prices = mockRecords('productSalePrices')
    const products = mockRecords('products')
    expect(prices.length).toBeGreaterThanOrEqual(products.length)

    for (const product of products) {
      const rows = prices.filter(row => String(row.productId) === String(product.id))
      expect(rows.length).toBeGreaterThanOrEqual(1)
      const active = rows.filter(row => row.isActive === true)
      expect(active).toHaveLength(1)
      expect(Number(active[0]!.salePrice)).toBe(Number(product.salePrice))
      expect(rows.every(row => Number(row.version) >= 1)).toBe(true)
      expect(new Set(rows.map(row => Number(row.version))).size).toBe(rows.length)
    }
  })

  it('seeds multiple versions on some products (history is not always one row)', () => {
    const products = mockRecords('products')
    const multi = products.filter(product =>
      mockRecords('productSalePrices').filter(row => String(row.productId) === String(product.id)).length > 1)
    expect(multi.length).toBeGreaterThan(0)
  })

  it('inserts active sale-price version 1 when a product is created', async () => {
    const repository = createMockEntityRepository()
    const created = await repository.create('products', {
      code: 'PRD-TEST', name: 'Test Product', costPrice: 1, salePrice: 2.5, quantity: 10, status: 'Active',
    })
    const rows = mockRecords('productSalePrices').filter(row => String(row.productId) === String(created.id))
    expect(rows).toHaveLength(1)
    expect(rows[0]).toMatchObject({ version: 1, isActive: true, salePrice: 2.5 })
  })

  it('persists activation: unchecking others, copying the price onto the product', async () => {
    const queries = createMockStockQueryRepository()
    const product = mockRecords('products').find(row =>
      mockRecords('productSalePrices').filter(p => String(p.productId) === String(row.id)).length > 1)!
    const rows = mockRecords('productSalePrices').filter(row => String(row.productId) === String(product.id))
    const next = rows.find(row => !row.isActive)!

    const activated = await queries.activateSalePrice(String(product.id), String(next.id))

    expect(activated.isActive).toBe(true)
    const after = mockRecords('productSalePrices').filter(row => String(row.productId) === String(product.id))
    expect(after.filter(row => row.isActive === true)).toHaveLength(1)
    expect(after.find(row => row.isActive)?.version).toBe(Number(next.version))
    expect(Number(mockRecords('products').find(row => row.id === product.id)?.salePrice)).toBe(Number(next.salePrice))
    // Repository list matches the persisted state (newest version first).
    const listed = await queries.listSalePrices(String(product.id))
    expect(listed.items[0]!.version).toBe(Math.max(...after.map(row => Number(row.version))))
  })

  it('adds a sale price as version MAX+1, active, and copies it onto the product', async () => {
    const queries = createMockStockQueryRepository()
    const product = mockRecords('products').find(row =>
      mockRecords('productSalePrices').filter(p => String(p.productId) === String(row.id)).length > 1)!
    const before = mockRecords('productSalePrices').filter(row => String(row.productId) === String(product.id))
    const maxVersion = Math.max(...before.map(row => Number(row.version)))

    const created = await queries.addSalePrice(String(product.id), { date: '2100-01-01', salePrice: 12.34 })

    expect(created.version).toBe(maxVersion + 1)
    expect(created.isActive).toBe(true)
    const after = mockRecords('productSalePrices').filter(row => String(row.productId) === String(product.id))
    expect(after.filter(row => row.isActive === true)).toHaveLength(1)
    expect(Number(after.find(row => row.isActive)?.salePrice)).toBe(12.34)
    expect(Number(mockRecords('products').find(row => row.id === product.id)?.salePrice)).toBe(12.34)
  })

  it('rejects sale prices that are not positive', async () => {
    const queries = createMockStockQueryRepository()
    const product = mockRecords('products')[0]!
    await expect(queries.addSalePrice(String(product.id), { date: '2100-01-01', salePrice: 0 }))
      .rejects.toThrow(/greater than zero/i)
  })

  it('lists product history filtered by kind without fetching every movement', async () => {
    const queries = createMockStockQueryRepository()
    const product = mockRecords('products').find(row =>
      mockRecords('stockMovements').some(mv => String(mv.productId) === String(row.id)
        && String(mv.type) === 'Damage'))!

    const damage = await queries.listProductHistory(String(product.id), { type: 'damage', limit: 500 })
    expect(damage.items.length).toBeGreaterThan(0)
    expect(damage.items.every(row => row.kind === 'damage' && row.type === 'Damage')).toBe(true)
    expect(damage.items.every(row => Number(row.quantity) < 0)).toBe(true)

    const sales = await queries.listProductHistory(String(product.id), { type: 'stock_out', limit: 500 })
    expect(sales.items.every(row => row.type === 'Sale' && row.kind === 'stock_out')).toBe(true)

    const stockIn = await queries.listProductHistory(String(product.id), { type: 'stock_in', limit: 500 })
    expect(stockIn.items.every(row => ['Stock In', 'Sale Return'].includes(row.type))).toBe(true)
    expect(stockIn.items.every(row => row.kind === 'stock_in')).toBe(true)

    // Date filtering is honored by the repository contract.
    const day = damage.items[0]!.date
    const oneDay = await queries.listProductHistory(String(product.id), { type: 'damage', startDate: day, endDate: day, limit: 500 })
    expect(oneDay.items.every(row => row.date === day)).toBe(true)
  })

  it('versions cost history oldest → newest and amounts are decimal-safe', async () => {
    const queries = createMockStockQueryRepository()
    // Pick a product purchased in multiple stock-in lots.
    const counts = new Map<string, number>()
    for (const purchase of mockRecords('stockIns')) {
      for (const item of (purchase.items as Array<Record<string, unknown>>) || []) {
        const id = String(item.productId)
        counts.set(id, (counts.get(id) || 0) + 1)
      }
    }
    const productId = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]![0]
    const expectedLots = counts.get(productId)!

    const result = await queries.listProductCostHistory(productId, { limit: 500 })
    expect(result.items.length).toBe(expectedLots)
    expect(result.items.length).toBeGreaterThan(1)
    // Newest first, so versions descend.
    for (let i = 1; i < result.items.length; i += 1) {
      expect(result.items[i - 1]!.version).toBeGreaterThan(result.items[i]!.version)
    }
    expect(result.items[0]!.version).toBe(expectedLots)
    expect(result.items.at(-1)!.version).toBe(1)
    for (const row of result.items) {
      expect(Number(row.amount)).toBeCloseTo(Number(row.unitCost) * Number(row.quantity), 2)
      expect(String(row.documentNo)).toMatch(/^PIN-/)
    }
  })
})

describe('UOM Pricing rows (spec §2.1.3: Convert UOM, stock always in base UOM)', () => {
  it('rejects duplicate Original UOMs', () => {
    const rows = [
      { uomId: 'uom2', uomSymbol: 'box', convertUomId: 'uom3', factorToBase: 12, costPrice: null, salePrice: 9.6, isDefaultSale: false },
    ]
    expect(() => normalizeUomConversions(
      [...rows, { ...rows[0] }],
      'uom3',
    )).toThrow(/duplicate/i)
  })

  it('derives and persists cost from base cost × factor when cost is empty', () => {
    const rows = normalizeUomConversions(
      [{ uomId: 'uom2', uomSymbol: 'box', convertUomId: 'uom3', factorToBase: 12, costPrice: null, salePrice: 9.6, isDefaultSale: false }],
      'uom3',
      { baseCostPrice: 0.5 },
    )
    expect(rows).toHaveLength(1)
    expect(rows[0]!.costPrice).toBe(6)
    expect(rows[0]!.salePrice).toBe(9.6)
  })

  it('keeps decimal factors exact (no binary-float drift)', () => {
    expect(multiplyDecimalSafe('1.1', 3)).toBe(3.3)
    expect(convertToBase(2, '1.5')).toBe(3)
    expect(convertToBase('0.1', 3)).toBe(0.3)
    expect(multiplyDecimalSafe('0.1', 0.2)).toBe(0.02)
  })

  it('stock in 2 box (factor 12) adds +24 in the base UOM and snapshots the line UOM', async () => {
    const repository = createMockPosRepository()
    const product = mockRecords('products').find(row => String(row.id) === 'prd1')!
    const before = Number(product.quantity)
    expect(Number(product.quantity)).toBeGreaterThan(0)

    const record = await repository.createStockOperation({
      type: 'stock_in',
      productId: 'prd1',
      quantity: 2,
      uomId: 'uom2',
      uomSymbol: 'box',
      factorToBase: 12,
      unitCost: 6,
    })
    expect(Number(record.quantity)).toBe(24)
    expect(Number(product.quantity)).toBe(before + 24)

    const movement = mockRecords('stockMovements')[0]!
    expect(Number(movement.quantity)).toBe(24)
    expect(String(movement.uom)).toBe('box')
    expect(Number(movement.unitCost)).toBe(0.5)
  })

  it('POS sell 1 box stocks out -12 base and prices the line at the box price', async () => {
    const repository = createMockPosRepository()
    const product = mockRecords('products').find(row => String(row.id) === 'prd1')!
    const before = Number(product.quantity)

    const sale = await repository.completeSale({
      items: [{ productId: 'prd1', quantity: 1, unitPrice: 9.6, uomId: 'uom2', uomSymbol: 'box', factorToBase: 12 }],
      paymentMethod: 'Cash',
      paidAmount: 9.6,
    })
    const line = (sale.items as Array<Record<string, unknown>>)[0]!
    expect(Number(line.quantity)).toBe(1)
    expect(Number(line.price)).toBe(9.6)
    expect(String(line.uom)).toBe('box')
    expect(Number(product.quantity)).toBe(before - 12)

    const movement = mockRecords('stockMovements')[0]!
    expect(Number(movement.quantity)).toBe(-12)
    expect(String(movement.uom)).toBe('box')
  })

  it('still blocks oversell against base stock when a large factor is used', async () => {
    const repository = createMockPosRepository()
    const product = mockRecords('products').find(row => String(row.id) === 'prd1')!
    const baseStock = Number(product.quantity)
    await expect(repository.completeSale({
      items: [{ productId: 'prd1', quantity: baseStock, unitPrice: 9.6, uomId: 'uom2', uomSymbol: 'box', factorToBase: 12 }],
      paymentMethod: 'Cash',
      paidAmount: 0,
    })).rejects.toThrow(/insufficient stock/i)
  })
})
