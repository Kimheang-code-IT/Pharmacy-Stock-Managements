/**
 * Party (customer / supplier) history helpers shared by the party detail
 * **History** tab. Pure projections of backend rows — no amounts are invented.
 */

export type PartyKind = 'customer' | 'supplier'

/** One sale (customer) or stock-in (supplier) history row. */
export interface PartyHistory {
  id: string
  documentNo: string
  date: string | null
  total: number
  paidAmount: number
  debtAmount: number
  status: string
  /** Document currency snapshot (amounts render in their own currency). */
  currency: string
  /** Staff user who created the sale / stock-in (audit tracking). */
  user: string
}

function asNumber(value: unknown): number {
  const parsed = Number(value ?? 0)
  return Number.isFinite(parsed) ? Math.round((parsed + Number.EPSILON) * 100) / 100 : 0
}

function asText(value: unknown): string {
  return String(value ?? '').trim()
}

/** `YYYY-MM-DD` day bucket for inclusive date comparisons. */
export function partyDay(value: unknown): string {
  return asText(value).slice(0, 10)
}

export function normalizePartyHistory(
  kind: PartyKind,
  row: Record<string, unknown>,
): PartyHistory {
  return {
    id: asText(row.id),
    documentNo: asText(kind === 'customer' ? row.invoice_no : row.document_no),
    date: asText(row.sale_date ?? row.transaction_date) || null,
    total: asNumber(kind === 'customer' ? row.grand_total : row.total),
    paidAmount: asNumber(row.paid_amount),
    // Customer rows carry the invoice debt; supplier rows the remaining debt.
    debtAmount: asNumber(kind === 'customer' ? row.debt_amount : row.remaining_amount),
    status: asText(kind === 'customer' ? row.payment_status || row.sale_status : row.status),
    currency: asText(row.currency) || 'USD',
    user: asText(kind === 'customer' ? row.cashier_name : row.user_name),
  }
}
