import { roundMoney } from '~/utils/pos/cart'

export type CheckoutDebtRow = Record<string, unknown> & {
  id: string
  date: string
  invoiceNo: string
  paidAmount: number
  remainingAmount: number
  paymentMethod: string
}

export function checkoutDeliveryFee(needsDelivery: boolean, deliveryPrice: number) {
  if (!needsDelivery) return 0
  return roundMoney(Math.max(0, Number(deliveryPrice) || 0))
}

export function checkoutSaleNet(subtotal: number, discount: number, deliveryPrice = 0) {
  return roundMoney(Math.max(0, subtotal - discount + deliveryPrice))
}

/** Selected open invoices included on this checkout (added to amount due). */
export function checkoutDepositTotal(remainings: number[]) {
  return roundMoney(remainings.reduce((sum, value) => sum + (Number(value) || 0), 0))
}

export function checkoutDue(saleNet: number, depositTotal: number) {
  return roundMoney(saleNet + depositTotal)
}

export function checkoutOutstanding(due: number, paidNow: number) {
  return roundMoney(Math.max(0, due - (Number(paidNow) || 0)))
}
