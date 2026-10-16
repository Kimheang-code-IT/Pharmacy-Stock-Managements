import { describe, expect, it } from 'vitest'
import {
  convertAmount,
  convertCartLines,
  currencyFactor,
  type PosCartLine,
} from '../app/utils/pos/cart'

function line(partial: Partial<PosCartLine>): PosCartLine {
  return {
    productId: 'p1',
    name: 'Widget',
    barcode: '',
    uom: 'PCS',
    uomId: 'u1',
    factorToBase: 1,
    uomOptions: [],
    imageUrl: null,
    availableStock: 10,
    unitPrice: 0,
    discountPercent: 0,
    quantity: 1,
    ...partial,
  }
}

describe('POS paid-currency conversion (invoice stored in the paid currency)', () => {
  it('USD → KHR multiplies by the rate; KHR → USD divides by it', () => {
    expect(currencyFactor('USD', 'KHR', 4100)).toBe(4100)
    expect(currencyFactor('KHR', 'USD', 4100)).toBeCloseTo(1 / 4100, 10)
    expect(currencyFactor('USD', 'USD', 4100)).toBe(1)
    expect(currencyFactor('KHR', 'KHR', 4100)).toBe(1)
    // No valid rate → identity (never a zeroed document).
    expect(currencyFactor('USD', 'KHR', 0)).toBe(1)
  })

  it('converts cart line prices + FEFO allocations once, both directions', () => {
    const lines = [line({
      unitPrice: 15,
      quantity: 1,
      batchAllocations: [{ batchNo: 'B1', qty: 1, unitPrice: 15 }],
    })]

    convertCartLines(lines, 'USD', 'KHR', 4100)
    expect(lines[0]!.unitPrice).toBe(61500)
    expect(lines[0]!.batchAllocations![0]!.unitPrice).toBe(61500)

    convertCartLines(lines, 'KHR', 'USD', 4100)
    expect(lines[0]!.unitPrice).toBe(15)
    expect(lines[0]!.batchAllocations![0]!.unitPrice).toBe(15)
  })

  it('converts header amounts (delivery, discount, paid) with the same factor', () => {
    expect(convertAmount(1.5, 'USD', 'KHR', 4100)).toBe(6150)
    expect(convertAmount(6150, 'KHR', 'USD', 4100)).toBe(1.5)
    // Same currency / no rate never changes an amount.
    expect(convertAmount(10, 'USD', 'USD', 4100)).toBe(10)
    expect(convertAmount(10, 'USD', 'KHR', 0)).toBe(10)
  })

  it('a riel payment at 1 USD = 4,100 KHR stores whole-riel amounts', () => {
    // $15 invoice → KHR at the keypad rate: 61,500៛ (no float drift).
    expect(convertAmount(15, 'USD', 'KHR', 4100)).toBe(61500)
    expect(convertAmount(61_500, 'KHR', 'USD', 4100)).toBe(15)
  })

  it('converts a debt collection into the debt\u2019s own settlement currency', () => {
    // Collecting riel for a USD 20 debt: 82,000៛ settles exactly 20.00.
    expect(convertAmount(82_000, 'KHR', 'USD', 4100)).toBe(20)
    // A round riel amount settles the converted value (4 dp, never over).
    expect(convertAmount(80_000, 'KHR', 'USD', 4100)).toBe(19.5122)
    // Collecting dollars for a KHR debt at its historical rate.
    expect(convertAmount(20, 'USD', 'KHR', 4100)).toBe(82000)
  })
})
