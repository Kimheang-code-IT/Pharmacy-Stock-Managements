import { describe, expect, it } from 'vitest'
import { stockModules } from '../app/config/stock-modules'
import { getModule } from '../app/config/modules'
import { STOCK_OPERATION_META } from '../app/config/pos-options'

/** Stock navigation: Purchase Stock (Stock In) + movements; no Adjustment. */

describe('stock module routes', () => {
  const products = stockModules.find(module => module.collection === 'products')!
  const movements = stockModules.find(module => module.collection === 'stockMovements')!

  it('registers the product list at /stock/products', () => {
    expect(products.path).toBe('/stock/products')
  })

  it('keeps the read-only movements list at /stock/movements', () => {
    expect(movements.path).toBe('/stock/movements')
    expect(movements.readOnly).toBe(true)
    expect(movements.tableOnly).toBe(true)
    expect(movements.canCreate).toBe(false)
    expect(movements.fields).toEqual([])
  })

  it('resolves the products module from its detail and create routes', () => {
    expect(getModule('/stock/products/prd-1')?.collection).toBe('products')
    expect(getModule('/stock/products/new')?.collection).toBe('products')
  })

  it('does not register stock in/adjustment/damage/expiry pages', () => {
    const paths = stockModules.map(module => module.path)
    expect(paths).not.toContain('/stock/in')
    expect(paths).not.toContain('/stock/adjustment')
    expect(paths).not.toContain('/stock/damage')
    expect(paths).not.toContain('/stock/expiry')
  })
})

describe('purchase stock (stock in as full-page purchase flow)', () => {
  it('labels the Stock In operation Purchase Stock (no Adjustment on products)', () => {
    expect(STOCK_OPERATION_META.stock_in.label).toBe('Purchase Stock')
    expect(STOCK_OPERATION_META.adjustment.label).toBe('Adjustment')
  })
})

describe('stock movements table (read-only history)', () => {
  const movements = stockModules.find(module => module.collection === 'stockMovements')!

  it('shows exactly the approved movement columns in order', () => {
    const keys = movements.columns.map(column => column.key)
    expect(keys).toEqual([
      'date',
      'documentNo',
      'product',
      'barcode',
      // Batch traceability (spec: movements expose the lot the change hit).
      'batchNo',
      'expiryDate',
      'type',
      'uomSymbol',
      'qtyIn',
      'qtyOut',
      'user',
    ])
  })

  it('keeps Reference out of the table when it duplicates Document No.', () => {
    const keys = movements.columns.map(column => column.key)
    expect(keys).not.toContain('reference')
  })

  it('exposes no edit/delete surface (immutable history)', () => {
    expect(movements.fields).toHaveLength(0)
    expect(movements.canCreate).toBe(false)
    const keys = movements.columns.map(column => column.key)
    expect(keys).not.toContain('code')
    expect(keys).not.toContain('sku')
  })

  it('offers the approved movement type filter values', () => {
    const filter = movements.filters?.find(item => item.key === 'type')
    expect(filter?.options).toEqual([
      'Stock In',
      'Sale',
      'Sale Return',
      'Purchase Return',
      'Damage',
      'Expiry',
    ])
  })
})