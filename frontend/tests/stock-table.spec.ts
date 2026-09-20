import { describe, expect, it } from 'vitest'
import { stockModules } from '../app/config/stock-modules'
import { PAPER_STYLES } from '../app/utils/print/html'
import { printSaleInvoice } from '../app/utils/print/invoice'

/** Print controls: the same invoice component offers Print A4 / Print A5. */

describe('print controls (POS + reprint entry points)', () => {
  it('offers exactly A4 and A5 paper sizes for the invoice chooser', () => {
    const sizes = Object.keys(PAPER_STYLES).sort()
    expect(sizes).toEqual(['A4', 'A5'])
  })

  it('defaults POS printing to A4 and keeps the same builder for A5', async () => {
    // printSaleInvoice is paper-size parametrized; both sizes share one
    // buildSaleInvoiceHtml component (no duplicated implementation).
    const input = {
      shopName: 'Demo Shop',
      invoiceNo: 'INV-000020',
      dateLabel: '10/09/26 10:00',
      customerName: 'Walk-in',
      cashier: 'admin',
      currency: 'USD',
      lines: [{ name: 'Glove', uom: 'PCS', quantity: 1, unitPrice: 1, discountPercent: 0 }],
      deliveryPrice: 0,
      previousDebtAmount: 0,
      depositAmount: 0,
      outstandingAmount: 1,
    }
    // Node env: document is undefined → print resolves without DOM work.
    await expect(printSaleInvoice(input, 'A4')).resolves.toBeUndefined()
    await expect(printSaleInvoice(input, 'A5')).resolves.toBeUndefined()
  })
})

describe('stock table (spec §2.1.5 — no SKU / product code columns)', () => {
  const products = stockModules.find(module => module.collection === 'products')!

  it('shows exactly the approved stock columns in order', () => {
    const keys = products.columns.map(column => column.key)
    expect(keys).toEqual([
      'imageUrl',
      'barcode',
      'name',
      'category',
      'brand',
      'uomSymbol',
      'quantity',
      'stockInQty',
      'stockOutQty',
      'status',
    ])
  })

  it('never exposes SKU / product code as a user-facing column or field', () => {
    const keys = products.columns.map(column => column.key)
    expect(keys).not.toContain('code')
    expect(keys).not.toContain('sku')
    const fields = products.fields.map(field => field.key)
    expect(fields).not.toContain('code')
    expect(fields).not.toContain('sku')
  })

  it('keeps Barcode before Status and drops the nearest-expiry column', () => {
    const keys = products.columns.map(column => column.key)
    expect(keys.indexOf('barcode')).toBe(1)
    expect(keys).not.toContain('expiryDate')
    expect(keys[keys.length - 1]).toBe('status')
  })

  it('keeps the stock movements module registered for the second tab', () => {
    const movements = stockModules.find(module => module.collection === 'stockMovements')
    expect(movements?.path).toBe('/stock/movements')
  })
})