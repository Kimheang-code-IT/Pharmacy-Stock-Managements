import { describe, expect, it } from 'vitest'
import type { AppRecord } from '../app/config/admin-seed'
import type { SaleDetail } from '../app/repositories/contracts/entities'
import { saleReturnCartLines } from '../app/utils/pos/return'
import { buildPurchaseReturnLines, documentHasReturnableLines } from '../app/utils/reports/returns'

function product(overrides: Record<string, unknown> = {}): AppRecord {
  return {
    id: 'p1',
    name: 'Paracetamol',
    barcode: 'BC-1',
    uomId: 'uom-base',
    uomSymbol: 'pcs',
    ...overrides,
  } as AppRecord
}

describe('POS sale return mode', () => {
  const sale: SaleDetail = {
    id: 'sale1',
    invoiceNo: 'INV-001',
    customerId: 'c1',
    customerName: 'Nita',
    currency: 'KHR',
    exchangeRate: 4100,
    items: [
      {
        id: 'item1',
        productId: 'p1',
        name: 'Paracetamol',
        uom: 'pcs',
        uomId: 'uom-base',
        factorToBase: 1,
        quantity: 5,
        returnedQuantity: 0,
        unitPrice: 1000,
        discountPercent: 10,
        discountAmount: 500,
        lineTotal: 4500,
      },
      {
        id: 'item2',
        productId: 'p2',
        name: 'Fully Returned',
        uom: 'box',
        uomId: 'uom-box',
        factorToBase: 10,
        quantity: 2,
        returnedQuantity: 2,
        unitPrice: 5000,
        discountPercent: 0,
        discountAmount: 0,
        lineTotal: 10000,
      },
    ],
  }

  it('preloads only returnable lines with original price, UOM, currency and qty', () => {
    const lines = saleReturnCartLines(sale, new Map([['p1', product()]]))
    expect(lines).toHaveLength(1)
    const line = lines[0]!
    expect(line.saleItemId).toBe('item1')
    expect(line.productId).toBe('p1')
    expect(line.quantity).toBe(5)
    expect(line.availableStock).toBe(5)
    expect(line.unitPrice).toBe(1000)
    expect(line.discountPercent).toBe(10)
    expect(line.uom).toBe('pcs')
    expect(line.uomId).toBe('uom-base')
    expect(line.factorToBase).toBe(1)
    // UOM options come from the product Pricing rows.
    expect(line.uomOptions.some(option => option.value === 'uom-base')).toBe(true)
  })

  it('falls back to the original UOM when the product is unknown', () => {
    const lines = saleReturnCartLines(sale, new Map())
    expect(lines[0]!.uomOptions).toEqual([{ label: 'pcs', value: 'uom-base' }])
  })

  it('uses only the still-returnable remainder when part of a line was returned', () => {
    const partiallyReturned: SaleDetail = {
      ...sale,
      items: [{ ...sale.items[0]!, quantity: 5, returnedQuantity: 2 }],
    }
    const lines = saleReturnCartLines(partiallyReturned, new Map())
    expect(lines[0]!.quantity).toBe(3)
    expect(lines[0]!.availableStock).toBe(3)
  })
})

describe('Purchase return mode lines', () => {
  const doc = {
    id: 'tx1',
    purchaseNo: 'PIN-00001',
    currency: 'KHR',
    exchangeRate: 4100,
    items: [
      { id: 'line1', productId: 'p1', name: 'Paracetamol', batchNo: 'B-1', expiryDate: '2027-01-01', quantity: 10, returnedQuantity: 4, returnableQuantity: 6, price: 2 },
      { id: 'line2', productId: 'p2', name: 'Fully Returned', quantity: 3, returnedQuantity: 3, returnableQuantity: 0, price: 5 },
    ],
  } as unknown as AppRecord

  it('keeps original batch / expiry / cost and defaults qty to the returnable amount', () => {
    const lines = buildPurchaseReturnLines(doc, new Map([['p1', product()]]))
    expect(lines).toHaveLength(1)
    const line = lines[0]!
    expect(line.lineId).toBe('line1')
    expect(line.batchNo).toBe('B-1')
    expect(line.expiryDate).toBe('2027-01-01')
    expect(line.uomId).toBe('uom-base')
    expect(line.unitAmount).toBe(2)
    expect(line.quantity).toBe(6)
    expect(line.amount).toBe(12)
    expect(line.returnableQuantity).toBe(6)
  })

  it('reports no returnable lines when everything was already returned', () => {
    expect(documentHasReturnableLines({ items: [{ quantity: 2, returnedQuantity: 2 }] } as unknown as AppRecord)).toBe(false)
  })

  it('caps the return at the quantity still in stock', () => {
    const partlySold = {
      ...doc,
      items: [
        { id: 'line1', productId: 'p1', name: 'Paracetamol', batchNo: 'B-1', expiryDate: '2027-01-01', quantity: 10, returnedQuantity: 4, returnableQuantity: 6, availableQuantity: 2, price: 2 },
      ],
    } as unknown as AppRecord
    const lines = buildPurchaseReturnLines(partlySold, new Map([['p1', product()]]))
    expect(lines).toHaveLength(1)
    expect(lines[0]!.quantity).toBe(2)
    expect(lines[0]!.returnableQuantity).toBe(2)
    expect(lines[0]!.amount).toBe(4)
  })

  it('drops a line whose stock was fully sold', () => {
    const soldOut = {
      ...doc,
      items: [
        { id: 'line1', productId: 'p1', name: 'Paracetamol', quantity: 10, returnedQuantity: 0, returnableQuantity: 10, availableQuantity: 0, price: 2 },
      ],
    } as unknown as AppRecord
    expect(buildPurchaseReturnLines(soldOut, new Map())).toHaveLength(0)
  })
})
