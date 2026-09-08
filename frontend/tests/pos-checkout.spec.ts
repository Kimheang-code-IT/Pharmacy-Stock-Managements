import { describe, expect, it } from 'vitest'
import {
  checkoutDeliveryFee,
  checkoutDepositTotal,
  checkoutDue,
  checkoutOutstanding,
  checkoutSaleNet,
} from '../app/utils/pos/checkout'

describe('POS checkout totals', () => {
  it('builds sale net with delivery price, deposit total, due, and outstanding from paid now', () => {
    const saleNet = checkoutSaleNet(100, 10, 5)
    const deposit = checkoutDepositTotal([25, 15])
    const due = checkoutDue(saleNet, deposit)
    expect(saleNet).toBe(95)
    expect(deposit).toBe(40)
    expect(due).toBe(135)
    expect(checkoutOutstanding(due, 80)).toBe(55)
    expect(checkoutOutstanding(due, 135)).toBe(0)
    expect(checkoutOutstanding(due, 200)).toBe(0)
  })

  it('ignores delivery price when Delivery is not checked', () => {
    expect(checkoutDeliveryFee(false, 12)).toBe(0)
    expect(checkoutDeliveryFee(true, 12)).toBe(12)
    expect(checkoutSaleNet(100, 10, checkoutDeliveryFee(false, 12))).toBe(90)
  })
})
