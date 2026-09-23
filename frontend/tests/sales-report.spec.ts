import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createHttpEntityRepository,
  createHttpPosCommandRepository,
} from '../app/repositories/http/entities'

interface CapturedRequest {
  method: string
  url: string
  query?: Record<string, unknown>
  body?: unknown
}

/** Minimal fake `useApi` matching repositories.spec.ts. */
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
    patch: async (url: string, body?: unknown) => {
      captured.push({ method: 'PATCH', url, body })
      return handler(captured[captured.length - 1]!)
    },
  })
  vi.stubGlobal('useApi', fakeApi)
  return captured
}

afterEach(() => {
  vi.unstubAllGlobals()
})

/** One raw GET /reports/sales line row (the backend `SalesReportRow` shape). */
function saleLine(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    sale_id: 'sale-1',
    sale_item_id: 'item-1',
    product_id: 'prd-1',
    sale_date: '2026-09-15T10:00:00Z',
    invoice_no: 'INV-000015',
    customer_name: 'Walk-in',
    product_name: 'Product A',
    quantity: '1.0000',
    returned_quantity: '0',
    returnable_quantity: '1',
    selling_price: '2.00',
    discount_amount: '0.00',
    sales_amount: '2.00',
    return_amount: '0.00',
    net_quantity: '1',
    cost: '0.00',
    gross_profit: '0.00',
    debt_amount: '0.00',
    cashier_name: 'admin',
    payment_method: 'CASH',
    currency: 'USD',
    exchange_rate: '1',
    // Saved sale header (authoritative checkout values).
    subtotal: '2.00',
    sale_discount: '0.00',
    delivery_price: '0.00',
    grand_total: '2.00',
    paid_amount: '2.00',
    payment_status: 'PAID',
    note: null,
    due_date: null,
    ...overrides,
  }
}

async function loadSalesReport(rows: Record<string, unknown>[]) {
  withFakeApi(() => ({ data: rows, meta: { page: 1, limit: 500, total: rows.length } }))
  const repository = createHttpEntityRepository()
  const result = await repository.list('sales')
  return result.items
}

describe('sales report adapter (completed POS sale → report row)', () => {
  it('maps a 1 × $2.00 cash sale with the real checkout values', async () => {
    const [row] = await loadSalesReport([saleLine()])
    expect(row).toBeTruthy()
    expect(row!.invoiceNo).toBe('INV-000015')
    expect(row!.date).toBe('2026-09-15T10:00:00Z')
    expect(row!.customer).toBe('Walk-in')
    expect(row!.lineCount).toBe(1)
    expect(row!.subtotal).toBe(2)
    expect(row!.discount).toBe(0)
    expect(row!.total).toBe(2)
    expect(row!.paidAmount).toBe(2)
    expect(row!.remaining).toBe(0)
    expect(row!.paymentMethod).toBe('CASH')
    expect(row!.paymentMethodLabel).toBe('Cash')
    expect(row!.currency).toBe('USD')
    expect(row!.status).toBe('Paid')
  })

  it('keeps the saved header discount instead of double-counting line discounts', async () => {
    const [row] = await loadSalesReport([saleLine({
      invoice_no: 'INV-000016',
      selling_price: '10.00',
      discount_amount: '2.00',
      sales_amount: '8.00',
      subtotal: '10.00',
      sale_discount: '2.00',
      grand_total: '8.00',
      paid_amount: '8.00',
    })])
    expect(row!.subtotal).toBe(10)
    expect(row!.discount).toBe(2)
    expect(row!.discountAmount).toBe(2)
    expect(row!.total).toBe(8)
    expect(row!.paidAmount).toBe(8)
    expect(row!.remaining).toBe(0)
    expect(row!.status).toBe('Paid')
  })

  it('adds the delivery fee into the grand total', async () => {
    const [row] = await loadSalesReport([saleLine({
      invoice_no: 'INV-000017',
      subtotal: '20.00',
      sales_amount: '20.00',
      selling_price: '10.00',
      quantity: '2.0000',
      delivery_price: '2.00',
      grand_total: '22.00',
      paid_amount: '22.00',
    })])
    expect(row!.subtotal).toBe(20)
    expect(row!.deliveryPrice).toBe(2)
    expect(row!.total).toBe(22)
    expect(row!.paidAmount).toBe(22)
  })

  it('maps a partial/debt sale to Partial with the real remaining balance', async () => {
    const [row] = await loadSalesReport([saleLine({
      invoice_no: 'INV-000018',
      payment_method: 'CUSTOMER_DEBT',
      payment_status: 'PARTIAL',
      subtotal: '10.00',
      grand_total: '10.00',
      paid_amount: '5.00',
      debt_amount: '5.00',
      selling_price: '10.00',
      sales_amount: '10.00',
      due_date: '2026-10-15',
    })])
    expect(row!.paymentMethod).toBe('CUSTOMER_DEBT')
    expect(row!.paymentMethodLabel).toBe('Credit')
    expect(row!.status).toBe('Partial')
    expect(row!.total).toBe(10)
    expect(row!.paidAmount).toBe(5)
    expect(row!.remaining).toBe(5)
    expect(row!.remainingAmount).toBe(5)
    expect(row!.dueDate).toBe('2026-10-15')
  })

  it('maps an unpaid debt sale to Unpaid', async () => {
    const [row] = await loadSalesReport([saleLine({
      payment_method: 'CUSTOMER_DEBT',
      payment_status: 'UNPAID',
      subtotal: '10.00',
      grand_total: '10.00',
      paid_amount: '0.00',
      debt_amount: '10.00',
    })])
    expect(row!.status).toBe('Unpaid')
    expect(row!.paidAmount).toBe(0)
    expect(row!.remaining).toBe(10)
  })

  it('renders a KHR sale in its own saved currency (never the live rate)', async () => {
    const [row] = await loadSalesReport([saleLine({
      invoice_no: 'INV-000019',
      currency: 'KHR',
      exchange_rate: '4100',
      subtotal: '8200.00',
      sales_amount: '8200.00',
      selling_price: '4100.00',
      quantity: '2.0000',
      grand_total: '8200.00',
      paid_amount: '8200.00',
    })])
    expect(row!.currency).toBe('KHR')
    expect(row!.exchangeRate).toBe(4100)
    expect(row!.subtotal).toBe(8200)
    expect(row!.total).toBe(8200)
    expect(row!.paidAmount).toBe(8200)
  })

  it('labels a Bank/QR tender', async () => {
    const [row] = await loadSalesReport([saleLine({ payment_method: 'BANK_QR' })])
    expect(row!.paymentMethod).toBe('BANK_QR')
    expect(row!.paymentMethodLabel).toBe('Bank/QR')
  })

  it('groups multiple line rows of one invoice into a single document row', async () => {
    const rows = await loadSalesReport([
      saleLine({ sale_item_id: 'item-1', selling_price: '2.00', sales_amount: '2.00', subtotal: '5.00', grand_total: '5.00', paid_amount: '5.00' }),
      saleLine({ sale_item_id: 'item-2', product_name: 'Product B', selling_price: '3.00', sales_amount: '3.00', subtotal: '5.00', grand_total: '5.00', paid_amount: '5.00' }),
    ])
    expect(rows).toHaveLength(1)
    expect(rows[0]!.lineCount).toBe(2)
    expect(rows[0]!.subtotal).toBe(5)
    expect(rows[0]!.total).toBe(5)
  })

  it('falls back to line sums when the saved header is absent (legacy rows)', async () => {
    const legacy = saleLine()
    delete legacy.subtotal
    delete legacy.sale_discount
    delete legacy.delivery_price
    delete legacy.grand_total
    delete legacy.paid_amount
    const [row] = await loadSalesReport([legacy])
    expect(row!.subtotal).toBe(2)
    expect(row!.total).toBe(2)
    expect(row!.paidAmount).toBe(2)
    expect(row!.remaining).toBe(0)
    expect(row!.status).toBe('Paid')
  })
})

describe('purchase report adapter (double-adaptation regression)', () => {
  it('maps the saved purchase totals instead of zeroing them', async () => {
    withFakeApi(() => ({
      data: [{
        transaction_id: 'tx-1',
        stock_transaction_item_id: 'txi-1',
        product_id: 'prd-1',
        document_no: 'PIN-000001',
        transaction_date: '2026-09-15T10:00:00Z',
        supplier_name: 'Supplier A',
        product_name: 'Product A',
        quantity: '10.0000',
        returned_quantity: '0',
        returnable_quantity: '10',
        return_amount: '0.00',
        cost_price: '2.00',
        total_cost: '20.00',
        paid_amount: '5.00',
        remaining_debt: '15.00',
        status: 'PARTIAL',
        currency: 'USD',
        exchange_rate: '1',
        note: null,
        discount_amount: '0.00',
        tax_amount: '0.00',
      }],
      meta: { page: 1, limit: 500, total: 1 },
    }))
    const repository = createHttpEntityRepository()
    const { items: rows } = await repository.list('stockIns')
    expect(rows).toHaveLength(1)
    expect(rows[0]!.purchaseNo).toBe('PIN-000001')
    expect(rows[0]!.total).toBe(20)
    expect(rows[0]!.paidAmount).toBe(5)
    expect(rows[0]!.remaining).toBe(15)
  })
})

describe('sale detail adapter (POS edit source)', () => {
  it('loads the saved checkout fields for editSaleId', async () => {
    withFakeApi(() => ({
      data: {
        id: 'sale-1',
        invoice_no: 'INV-000020',
        customer_id: 'cus-1',
        customer_name: 'Dara',
        currency: 'USD',
        exchange_rate: '1',
        subtotal: '20.00',
        discount_amount: '2.00',
        delivery_price: '1.50',
        grand_total: '19.50',
        paid_amount: '9.50',
        debt_amount: '10.00',
        payment_status: 'PARTIAL',
        payment_method: 'CUSTOMER_DEBT',
        note: 'deliver after 5pm',
        due_date: '2026-10-01',
        items: [{
          id: 'item-1',
          product_id: 'prd-1',
          product_name: 'Product A',
          uom_symbol: 'pcs',
          factor_to_base: '1',
          quantity: '2',
          returned_quantity: '0',
          unit_price: '10.00',
          discount_percent: '10',
          discount_amount: '2.00',
          line_total: '18.00',
        }],
      },
    }))
    const commands = createHttpPosCommandRepository()
    const sale = await commands.getSale('sale-1')
    expect(sale.paymentMethod).toBe('CUSTOMER_DEBT')
    expect(sale.paymentStatus).toBe('PARTIAL')
    expect(sale.subtotal).toBe(20)
    expect(sale.discount).toBe(2)
    expect(sale.deliveryPrice).toBe(1.5)
    expect(sale.paidAmount).toBe(9.5)
    expect(sale.debtAmount).toBe(10)
    expect(sale.note).toBe('deliver after 5pm')
    expect(sale.dueDate).toBe('2026-10-01')
    expect(sale.items[0]?.unitPrice).toBe(10)
    expect(sale.items[0]?.discountPercent).toBe(10)
  })
})
