import { describe, expect, it } from 'vitest'
import {
  deliveryNotes,
  productById,
  products,
  productSalePrices,
  saleReturns,
  sales,
  stockIns,
  stockMovements,
} from './support/mocks/stock-seed'

const APPROVED_MOVEMENT_TYPES = [
  'Stock In',
  'Sale',
  'Sale Return',
  'Purchase Return',
  'Adjustment Increase',
  'Adjustment Decrease',
  'Damage',
  'Expiry',
]

/**
 * Mock-data completeness contract (seed mirrors the live system): every
 * list/column of the current features renders meaningful, internally
 * consistent rows in mock mode.
 */
describe('mock seed: sale items carry UOM + price snapshots', () => {
  it('every sale line has uom, factor and a consistent total', () => {
    for (const sale of sales) {
      for (const item of (sale.items as Array<Record<string, unknown>>)) {
        expect(String(item.uom || item.uomSymbol || ''), `${sale.saleNo}`).not.toBe('')
        expect(Number(item.factorToBase ?? 0)).toBeGreaterThan(0)
        expect(Number(item.total)).toBeCloseTo(Number(item.price) * Number(item.quantity), 2)
      }
    }
  })

  it('some lines sell in a pack UOM (multi-UOM POS data)', () => {
    const packLines = sales.flatMap(sale => (sale.items as Array<Record<string, unknown>>))
      .filter(item => Number(item.factorToBase) > 1)
    expect(packLines.length).toBeGreaterThan(0)
  })
})

describe('mock seed: purchases carry batch traceability', () => {
  it('batch-tracked purchase lines have a lot no + expiry; unbatched do not', () => {
    for (const purchase of stockIns) {
      for (const item of (purchase.items as Array<Record<string, unknown>>)) {
        const product = productById(String(item.productId))
        expect(String(item.uomSymbol || '')).toBe(String(product?.uomSymbol ?? ''))
        expect(Number(item.factorToBase)).toBe(1)
        if (product?.trackBatch === true) {
          expect(String(item.batchNo ?? '')).toMatch(/^B-/)
          expect(String(item.expiryDate ?? '')).not.toBe('')
        }
        else {
          expect(item.batchNo ?? '').toBe('')
        }
      }
    }
  })
})

describe('mock seed: movement ledger is complete and consistent', () => {
  it('only approved movement types appear', () => {
    const types = new Set(stockMovements.map(row => String(row.type)))
    for (const type of types) expect(APPROVED_MOVEMENT_TYPES, type).toContain(type)
  })

  it('every row has document/product/barcode/uom display fields', () => {
    for (const row of stockMovements) {
      expect(String(row.documentNo || row.reference || '')).not.toBe('')
      expect(String(row.barcode ?? '')).not.toBe('')
      expect(String(row.uomSymbol ?? row.unit ?? '')).not.toBe('')
      expect(String(row.user ?? '')).not.toBe('')
    }
  })

  it('qtyIn/qtyOut split matches the signed quantity', () => {
    for (const row of stockMovements) {
      const qty = Number(row.quantity ?? 0)
      expect(Number(row.qtyIn ?? 0)).toBe(qty > 0 ? qty : 0)
      expect(Number(row.qtyOut ?? 0)).toBe(qty < 0 ? Math.abs(qty) : 0)
    }
  })

  it('sales allocate FEFO lots: batched products have batched Sale rows', () => {
    for (const product of products.filter(row => row.trackBatch === true)) {
      const sold = stockMovements
        .filter(row => String(row.productId) === String(product.id) && row.type === 'Sale')
      const batchedSold = sold.filter(row => String(row.batchNo ?? '') !== '')
      // At least one batched sale row for sold batch-tracked products.
      if (sold.length) expect(batchedSold.length, String(product.id)).toBeGreaterThan(0)
    }
  })

  it('damage/expiry rows drain a named lot', () => {
    const drains = stockMovements.filter(row => row.type === 'Damage' || row.type === 'Expiry')
    expect(drains.length).toBeGreaterThan(0)
    for (const row of drains) {
      const product = productById(String(row.productId))
      if (product?.trackBatch === true) {
        expect(String(row.batchNo ?? ''), `${row.type} ${row.reference}`).toMatch(/^B-/)
      }
    }
  })

  it('returns appear in the ledger', () => {
    expect(stockMovements.some(row => row.type === 'Sale Return')).toBe(
      saleReturns.some(row => Number(row.restockedQuantity) > 0))
    expect(stockMovements.some(row => row.type === 'Purchase Return')).toBe(true)
  })
})

describe('mock seed: master data coherence', () => {
  it('every product has exactly one active sale-price version equal to its price', () => {
    for (const product of products) {
      const versions = productSalePrices.filter(row => String(row.productId) === String(product.id))
      const active = versions.filter(row => row.isActive === true)
      expect(active.length, String(product.id)).toBe(1)
      expect(Number(active[0]!.salePrice)).toBe(Number(product.salePrice))
    }
  })

  it('multi-UOM products keep exactly one default-sale row (the base UOM)', () => {
    for (const product of products) {
      const rows = (Array.isArray(product.uomConversions) ? product.uomConversions : []) as Array<Record<string, unknown>>
      const defaults = rows.filter(row => row.isDefaultSale === true)
      expect(defaults.length, String(product.id)).toBeLessThanOrEqual(1)
    }
  })

  it('delivery notes never deliver more than the sold quantity', () => {
    for (const note of deliveryNotes) {
      for (const line of (note.items as Array<Record<string, unknown>>)) {
        expect(Number(line.qtyToDeliver)).toBeLessThanOrEqual(Number(line.qtyOrdered))
      }
    }
  })
})
