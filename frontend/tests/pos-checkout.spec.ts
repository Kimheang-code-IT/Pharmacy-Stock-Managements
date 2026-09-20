import { describe, expect, it } from 'vitest'
import {
  checkoutChange,
  checkoutDeliveryFee,
  checkoutDepositTotal,
  checkoutDue,
  checkoutOutstanding,
  checkoutPaidNow,
  checkoutSaleNet,
  checkoutTenderSplit,
} from '../app/utils/pos/checkout'

describe('POS checkout totals', () => {
  it('keeps grand total separate from existing debt payment (USD)', () => {
    // Subtotal 10, discount 1 → Grand Total 9; deposit 2 must not inflate due.
    const grandTotal = checkoutSaleNet(10, 1, 0)
    const deposit = checkoutDepositTotal([2])
    const due = checkoutDue(grandTotal, deposit)
    expect(grandTotal).toBe(9)
    expect(deposit).toBe(2)
    expect(due).toBe(9)
    expect(checkoutPaidNow(undefined, due, false)).toBe(9)
    expect(checkoutOutstanding(due, 9)).toBe(0)
    expect(checkoutChange(11, due)).toBe(2)
    expect(checkoutOutstanding(due, 11)).toBe(0)
  })

  it('builds sale net with delivery; deposit stays off the sale due', () => {
    const saleNet = checkoutSaleNet(100, 10, 5)
    const deposit = checkoutDepositTotal([25, 15])
    const due = checkoutDue(saleNet, deposit)
    expect(saleNet).toBe(95)
    expect(deposit).toBe(40)
    expect(due).toBe(95)
    expect(checkoutOutstanding(due, 80)).toBe(15)
    expect(checkoutOutstanding(due, 95)).toBe(0)
    expect(checkoutChange(200, due)).toBe(105)
  })

  it('ignores delivery price when Delivery is not checked', () => {
    expect(checkoutDeliveryFee(false, 12)).toBe(0)
    expect(checkoutDeliveryFee(true, 12)).toBe(12)
    expect(checkoutSaleNet(100, 10, checkoutDeliveryFee(false, 12))).toBe(90)
  })

  it('pays the grand total in full when Paid now is untouched (walk-in cash sale)', () => {
    expect(checkoutPaidNow(undefined, 9, false)).toBe(9)
    expect(checkoutOutstanding(9, checkoutPaidNow(undefined, 9, false))).toBe(0)
    expect(checkoutPaidNow(undefined, 0, false)).toBe(0)
    expect(checkoutPaidNow(Number.NaN, 9840, false)).toBe(9840)
  })

  it('allows overpay for change and credits nothing on Credit', () => {
    expect(checkoutPaidNow(80, 95, false)).toBe(80)
    expect(checkoutPaidNow(200, 95, false)).toBe(200)
    expect(checkoutChange(200, 95)).toBe(105)
    expect(checkoutPaidNow(undefined, 95, true)).toBe(0)
    expect(checkoutPaidNow(50, 95, true)).toBe(0)
  })

  it('splits one keypad tender into sale payment and existing-debt payment', () => {
    // Sale 95, old debt 40 → keypad Total 135.
    // Cash tends the sale first, then the debt up to the budget.
    expect(checkoutTenderSplit(135, 95, 40, false)).toEqual({ paid: 95, deposit: 40 })
    expect(checkoutTenderSplit(100, 95, 40, false)).toEqual({ paid: 95, deposit: 5 })
    expect(checkoutTenderSplit(80, 95, 40, false)).toEqual({ paid: 80, deposit: 0 })
    // Overpay beyond sale + debt is change, never extra debt payment.
    expect(checkoutTenderSplit(200, 95, 40, false)).toEqual({ paid: 95, deposit: 40 })
    // No existing debt → the whole tender pays the sale.
    expect(checkoutTenderSplit(95, 95, 0, false)).toEqual({ paid: 95, deposit: 0 })
  })

  it('credits the sale but still settles existing debt on a combined Credit tender', () => {
    expect(checkoutTenderSplit(40, 95, 40, true)).toEqual({ paid: 0, deposit: 40 })
    expect(checkoutTenderSplit(10, 95, 40, true)).toEqual({ paid: 0, deposit: 10 })
    expect(checkoutTenderSplit(0, 95, 40, true)).toEqual({ paid: 0, deposit: 0 })
  })

  it('keeps the same grand-total rules in KHR', () => {
    const grandTotal = checkoutSaleNet(41000, 4100, 0)
    const deposit = checkoutDepositTotal([8200])
    const due = checkoutDue(grandTotal, deposit)
    expect(grandTotal).toBe(36900)
    expect(due).toBe(36900)
    expect(checkoutPaidNow(undefined, due, false)).toBe(36900)
    expect(checkoutChange(41000, due)).toBe(4100)
    expect(checkoutOutstanding(due, 30000)).toBe(6900)
  })
})
