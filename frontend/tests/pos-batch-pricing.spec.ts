import { describe, expect, it } from 'vitest'
import type { PosCartLine } from '~/utils/pos/cart'
import {
  allocateBatches,
  allocationUnitPrice,
  cartSubtotal,
  lineGross,
} from '~/utils/pos/cart'

/**
 * Batch-based POS pricing (spec: FEFO cart allocation). The server recomputes
 * the authoritative allocation at checkout; these cover the displayed
 * breakdown and its blended line totals.
 */

function line(partial: Partial<PosCartLine> & { batchAllocations?: PosCartLine['batchAllocations'] }): PosCartLine {
  return {
    productId: 'p1',
    name: 'aaa',
    barcode: '1',
    uom: 'ea',
    uomId: 'u1',
    factorToBase: 1,
    uomOptions: [],
    imageUrl: null,
    availableStock: 22,
    unitPrice: 30,
    discountPercent: 0,
    quantity: 7,
    ...partial,
  }
}

describe('allocateBatches (FEFO)', () => {
  const lots = [
    { batchNo: 'BATCH-001', remainingQty: 5, unitPrice: 10 },
    { batchNo: 'BATCH-002', remainingQty: 17, unitPrice: 30 },
  ]

  it('splits a quantity across lots first-expiry first', () => {
    expect(allocateBatches(lots, 7, 1)).toEqual([
      { batchNo: 'BATCH-001', qty: 5, unitPrice: 10 },
      { batchNo: 'BATCH-002', qty: 2, unitPrice: 30 },
    ])
  })

  it('uses one lot when it can cover the whole quantity', () => {
    expect(allocateBatches(lots, 3, 1)).toEqual([
      { batchNo: 'BATCH-001', qty: 3, unitPrice: 10 },
    ])
  })

  it('allocates in the selected UOM by dividing lot stock by the factor', () => {
    const packs = [{ batchNo: 'P1', remainingQty: 20, unitPrice: 100 }]
    expect(allocateBatches(packs, 2, 10)).toEqual([
      { batchNo: 'P1', qty: 2, unitPrice: 100 },
    ])
  })

  it('returns nothing when no lots are provided', () => {
    expect(allocateBatches(undefined, 3, 1)).toEqual([])
  })
})

describe('blended line total', () => {
  it('prices a 7-unit line as 5×$10 + 2×$30 = $110', () => {
    const allocations = allocateBatches([
      { batchNo: 'BATCH-001', remainingQty: 5, unitPrice: 10 },
      { batchNo: 'BATCH-002', remainingQty: 17, unitPrice: 30 },
    ], 7, 1)
    expect(lineGross(line({ batchAllocations: allocations }))).toBe(110)
    expect(allocationUnitPrice(allocations, 7)).toBeCloseTo(15.71, 2)
    expect(cartSubtotal([line({ batchAllocations: allocations })])).toBe(110)
  })

  it('falls back to unitPrice × qty without allocations', () => {
    expect(lineGross(line({ unitPrice: 30, quantity: 7 }))).toBe(210)
  })
})
