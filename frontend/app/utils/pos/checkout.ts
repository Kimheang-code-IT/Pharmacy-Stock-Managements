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

/** Subtotal − discount + delivery — the current sale only (never includes old debts). */
export function checkoutSaleNet(subtotal: number, discount: number, deliveryPrice = 0) {
  return roundMoney(Math.max(0, subtotal - discount + deliveryPrice))
}

/** Selected open invoices to settle at checkout (separate from sale grand total). */
export function checkoutDepositTotal(remainings: number[]) {
  return roundMoney(remainings.reduce((sum, value) => sum + (Number(value) || 0), 0))
}

/**
 * Amount due for THIS sale (grand total). Old-debt / deposit payments are
 * settled separately and must not inflate this figure.
 */
export function checkoutDue(saleNet: number, _depositTotal = 0) {
  return roundMoney(Math.max(0, Number(saleNet) || 0))
}

/** Remaining on the current sale after Paid now (never below zero). */
export function checkoutOutstanding(grandTotal: number, paidNow: number) {
  return roundMoney(Math.max(0, (Number(grandTotal) || 0) - (Number(paidNow) || 0)))
}

/** Cash change when Paid now exceeds the sale grand total. */
export function checkoutChange(paidNow: number, grandTotal: number) {
  return roundMoney(Math.max(0, (Number(paidNow) || 0) - Math.max(0, Number(grandTotal) || 0)))
}

/**
 * Paid-now amount for THIS sale only. An **untouched** input (undefined / NaN)
 * defaults to the grand total so a walk-in cash sale submits without typing
 * tender. Credit tenders nothing (balance becomes customer debt). Overpay is
 * allowed and surfaces as change — deposit / old-debt payments are never added.
 */
export function checkoutPaidNow(paidInput: number | undefined, grandTotal: number, isCredit: boolean): number {
  if (isCredit) return 0
  const due = roundMoney(Math.max(0, Number(grandTotal) || 0))
  if (paidInput == null) return due
  const typed = Number(paidInput)
  if (!Number.isFinite(typed)) return due
  return roundMoney(Math.max(0, typed))
}

/**
 * Split one combined tender from the payment keypad into the part that pays
 * THIS sale and the part that pays existing debt (deposit). The keypad Total
 * is `saleDue + debtBudget`, so cash tends the sale first and any excess (up
 * to the debt budget) settles prior invoices. Credit tenders nothing on the
 * sale; its tender only covers debt.
 */
export function checkoutTenderSplit(
  entered: number,
  saleDue: number,
  debtBudget: number,
  isCredit: boolean,
): { paid: number, deposit: number } {
  const total = roundMoney(Math.max(0, Number(entered) || 0))
  const due = roundMoney(Math.max(0, Number(saleDue) || 0))
  const budget = roundMoney(Math.max(0, Number(debtBudget) || 0))
  if (isCredit) return { paid: 0, deposit: roundMoney(Math.min(total, budget)) }
  const paid = roundMoney(Math.min(total, due))
  const deposit = roundMoney(Math.min(Math.max(0, total - paid), budget))
  return { paid, deposit }
}
