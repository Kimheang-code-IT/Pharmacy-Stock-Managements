import { describe, expect, it } from 'vitest'
import {
  availableStockInUom,
  defaultLineUomFor,
  uomOptionsFor,
} from '../app/utils/pos/cart'
import {
  conversionForUom,
  divideDecimalSafe,
  normalizeUomConversions,
  salePriceForUom,
} from '../app/utils/stock/uom-conversions'

const BASE_UOM = 'uom3'
const packRow = {
  uomId: 'uom2',
  uomSymbol: 'box',
  convertUomId: BASE_UOM,
  convertUomSymbol: 'pcs',
  factorToBase: 12,
  costPrice: null,
  salePrice: 9.6,
  isDefaultSale: false,
}
const baseRow = {
  uomId: BASE_UOM,
  uomSymbol: 'pcs',
  convertUomId: BASE_UOM,
  convertUomSymbol: 'pcs',
  factorToBase: 1,
  costPrice: null,
  salePrice: 0.8,
  isDefaultSale: true,
}

function productWith(rows: unknown) {
  return {
    id: 'prd1',
    uomId: BASE_UOM,
    uomSymbol: 'pcs',
    salePrice: 0.8,
    quantity: 24,
    uomConversions: rows,
  }
}

describe('Pricing validation (product form, spec §2.1.3)', () => {
  it('rejects missing UOM, factor ≤ 0, and non-positive sale prices', () => {
    expect(() => normalizeUomConversions([{ uomSymbol: 'box', factorToBase: 12, salePrice: 1 }], BASE_UOM))
      .toThrow(/required/i)
    expect(() => normalizeUomConversions([{ ...packRow, factorToBase: 0 }], BASE_UOM))
      .toThrow(/greater than zero/i)
    expect(() => normalizeUomConversions([{ ...packRow, salePrice: 0 }], BASE_UOM))
      .toThrow(/sale price/i)
    expect(() => normalizeUomConversions([{ ...baseRow, salePrice: 0 }], BASE_UOM))
      .toThrow(/sale price/i)
  })

  it('rejects duplicate Original UOMs', () => {
    expect(() => normalizeUomConversions([baseRow, packRow, packRow], BASE_UOM))
      .toThrow(/duplicate/i)
  })

  it('locks the base=base row at factor 1 and rejects self-converting pack rows', () => {
    const rows = normalizeUomConversions([{ ...baseRow, factorToBase: 7 }], BASE_UOM)
    expect(rows[0]!.factorToBase).toBe(1)
    expect(() => normalizeUomConversions(
      [baseRow, { ...packRow, convertUomId: 'uom2' }],
      BASE_UOM,
    )).toThrow(/Convert UOM/i)
  })

  it('accepts valid rows, defaults Convert UOM to the base, and enforces exactly one Default sale', () => {
    const rows = normalizeUomConversions([
      { ...baseRow, isDefaultSale: false },
      packRow,
      { ...packRow, uomId: 'uom1', uomSymbol: 'btl', factorToBase: 1.5, salePrice: 1.2, isDefaultSale: true },
    ], BASE_UOM)
    expect(rows).toHaveLength(3)
    expect(rows.filter(row => row.isDefaultSale)).toEqual([rows[2]])
    expect(rows[0]!.convertUomId).toBe(BASE_UOM)
    expect(rows[1]!.salePrice).toBe(9.6)
    expect(rows[2]!.factorToBase).toBe(1.5)
  })

  it('marks the base row as Default sale when nothing is marked', () => {
    const rows = normalizeUomConversions([baseRow, packRow], BASE_UOM)
    expect(rows[0]!.isDefaultSale).toBe(true)
    expect(rows[1]!.isDefaultSale).toBe(false)
  })

  it('materializes a missing base row so the product keeps one sellable row', () => {
    const rows = normalizeUomConversions([packRow], BASE_UOM, { baseSalePrice: 0.8, baseUomSymbol: 'pcs' })
    expect(rows).toHaveLength(2)
    expect(rows[0]).toMatchObject({ uomId: BASE_UOM, factorToBase: 1, salePrice: 0.8, isDefaultSale: true, uomSymbol: 'pcs' })
    expect(rows[1]!.isDefaultSale).toBe(false)
  })

  it('derives and persists cost from base cost × factor when cost is empty', () => {
    const rows = normalizeUomConversions([baseRow, packRow], BASE_UOM, { baseCostPrice: 0.5 })
    expect(rows[1]!.costPrice).toBe(6)
    expect(rows[1]!.salePrice).toBe(9.6)
  })
})

describe('decimal-safe conversion math', () => {
  it('multiplies and divides without binary-float drift', () => {
    expect(divideDecimalSafe(24, 12)).toBe(2)
    expect(divideDecimalSafe(1, 3)).toBeCloseTo(0.333333, 6)
    expect(divideDecimalSafe(3, '1.5')).toBe(2)
    expect(divideDecimalSafe(3.3, '1.1')).toBe(3)
  })

  it('treats non-positive factors as no stock (never divides by zero)', () => {
    expect(availableStockInUom(24, 0)).toBe(0)
    expect(availableStockInUom(24, -12)).toBe(0)
  })
})

describe('per-product UOM lookup (POS cart price/stock helpers)', () => {
  it('resolves Pricing-row sale prices (base row included)', () => {
    const product = productWith([baseRow, packRow])
    expect(salePriceForUom(product, 'uom2')).toBe(9.6)
    expect(salePriceForUom(product, BASE_UOM)).toBe(0.8)
    expect(salePriceForUom(product, 'uom-other')).toBeNull()
    expect(conversionForUom(product, 'uom2')?.factorToBase).toBe(12)
    expect(conversionForUom(product, BASE_UOM)?.factorToBase).toBe(1)
  })

  it('uses only the product\'s own Pricing rows — not a global list', () => {
    const other = productWith([])
    expect(salePriceForUom(other, 'uom2')).toBeNull()
  })

  it('resolves the base UOM to the POS-active mirror sale price (stale base row)', () => {
    // Activating a sale-price version copies onto products.salePrice; a stored
    // base Pricing row may hold an older snapshot — the mirror must win.
    const product = productWith([baseRow, packRow])
    const activated = { ...product, salePrice: 0.95 }
    expect(salePriceForUom(activated, BASE_UOM)).toBe(0.95)
    // Pack rows still follow their own Pricing row.
    expect(salePriceForUom(activated, 'uom2')).toBe(9.6)
  })
})

describe('POS cart UOM select (spec §2.1.3 / §5.11)', () => {
  it('offers exactly the product\'s Pricing rows (every Original UOM, base included)', () => {
    const product = productWith([
      baseRow,
      packRow,
      { ...packRow, uomId: 'uom1', uomSymbol: 'btl', factorToBase: 1.5, salePrice: 1.2 },
    ])
    expect(uomOptionsFor(product)).toEqual([
      { label: 'pcs', value: BASE_UOM },
      { label: 'box', value: 'uom2' },
      { label: 'btl', value: 'uom1' },
    ])
  })

  it('falls back to the base UOM for products without Pricing rows', () => {
    expect(uomOptionsFor(productWith([]))).toEqual([{ label: 'pcs', value: BASE_UOM }])
  })

  it('pre-selects the Default sale row on add-to-cart (price + factor from that row)', () => {
    const product = productWith([
      { ...baseRow, isDefaultSale: false },
      { ...packRow, isDefaultSale: true },
    ])
    expect(defaultLineUomFor(product)).toEqual({ uomId: 'uom2', uomSymbol: 'box', factorToBase: 12 })
  })

  it('falls back to the base UOM line when no Default sale row exists', () => {
    const product = productWith([])
    expect(defaultLineUomFor(product)).toEqual({ uomId: BASE_UOM, uomSymbol: 'pcs', factorToBase: 1 })
  })

  it('shows remaining stock in the selected UOM (base stock ÷ factor, base factor = 1)', () => {
    expect(availableStockInUom(24, 1)).toBe(24)
    expect(availableStockInUom(24, 12)).toBe(2)
    expect(availableStockInUom(25, '1.5')).toBeCloseTo(16.666667, 5)
  })
})
