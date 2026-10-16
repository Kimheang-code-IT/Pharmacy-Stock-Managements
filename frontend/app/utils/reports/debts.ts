import type { AppRecord } from '~/config/admin-seed'

/** Customer or supplier debt scope. */
export type DebtKind = 'customer' | 'supplier'

/**
 * The debt's own document currency always wins over any UI preference —
 * historical debts must never be re-displayed in the current preference.
 */
export function debtCurrency(row: AppRecord | null | undefined, fallback = 'USD'): string {
  return String(row?.currency || fallback || 'USD')
}

/**
 * True when every selected row belongs to the same party **and** currency,
 * i.e. it is safe to settle them in one backend operation (the backend settles
 * that party's open debts oldest-first and rejects overpayment).
 */
export function selectedDebtsShareScope(rows: readonly AppRecord[], kind: DebtKind): boolean {
  if (rows.length <= 1) return true
  const partyKey = (row: AppRecord) => String(kind === 'customer' ? row.customerId : row.supplierId)
  const firstParty = partyKey(rows[0]!)
  const firstCurrency = debtCurrency(rows[0])
  return rows.every(row => partyKey(row) === firstParty && debtCurrency(row) === firstCurrency)
}

/** Combined remaining balance of the selected open debts (2 dp). */
export function selectedDebtsTotal(rows: readonly AppRecord[]): number {
  return Math.round(rows.reduce((sum, row) => sum + Number(row.remainingAmount || 0), 0) * 10000) / 10000
}

/**
 * A debt still has an outstanding balance. Fully settled debts (status
 * `PAID` or `remainingAmount <= 0`) are dropped from the customer/supplier
 * debt report tables.
 */
export function isOpenDebt(row: AppRecord | null | undefined): boolean {
  if (!row) return false
  if (String(row.status || '').toUpperCase() === 'PAID') return false
  return Number(row.remainingAmount || 0) > 0
}

/** Open (unpaid / partially paid) debt rows only. */
export function openDebts(rows: readonly AppRecord[]): AppRecord[] {
  return rows.filter(isOpenDebt)
}

/** One grouped debt row: a party (customer/supplier) + currency summary. */
export type PartyDebtSummary = AppRecord

/** Positive per-currency open balances of a customer/supplier list row. Falls
 *  back to the stored scalar (`debtBalance` / `totalDebt`) when the row has no
 *  per-currency map (local/mock mode). Amounts of different currencies are
 *  never added together — each entry renders in its own currency. */
export function debtBalanceEntries(row: AppRecord | null | undefined): Array<{ currency: string, amount: number }> {
  const balances = row?.debtBalances
  const entries: Array<{ currency: string, amount: number }> = []
  if (balances && typeof balances === 'object') {
    for (const [currency, value] of Object.entries(balances as Record<string, unknown>)) {
      const amount = Number(value || 0)
      if (Number.isFinite(amount) && amount > 0) entries.push({ currency: String(currency).toUpperCase(), amount })
    }
  }
  if (!entries.length) {
    const scalar = Number(row?.debtBalance ?? row?.totalDebt ?? 0)
    if (Number.isFinite(scalar) && scalar > 0) {
      entries.push({ currency: String(row?.currency || 'USD'), amount: scalar })
    }
  }
  return entries.sort((a, b) => a.currency.localeCompare(b.currency))
}

/** Round to 4 dp to keep aggregated money exact (report math). */
function q4(value: number): number {
  return Math.round((Number(value) + Number.EPSILON) * 10000) / 10000
}

/** Oldest-first order used by the backend's party-level payments
 *  (`created_at asc, id asc`) so on-screen allocation matches the ledger. */
function oldestFirst(a: AppRecord, b: AppRecord): number {
  const left = String(a.createdAt ?? a.date ?? '')
  const right = String(b.createdAt ?? b.date ?? '')
  const byDate = left.localeCompare(right)
  return byDate !== 0 ? byDate : String(a.id ?? '').localeCompare(String(b.id ?? ''))
}

/**
 * Customer/Supplier Debt Report: group open debt documents into ONE summary
 * row per party **and currency** (an amount may only be summed with its own
 * currency). The row keeps its source documents in `debts` (oldest-first) so
 * the page can allocate a lump payment exactly the way the backend will and
 * print a receipt listing the settled documents.
 */
export function summarizeDebtsByParty(rows: readonly AppRecord[], kind: DebtKind): PartyDebtSummary[] {
  const groups = new Map<string, { partyId: string, name: string, currency: string, debts: AppRecord[] }>()
  for (const row of openDebts(rows)) {
    const partyId = String(kind === 'customer' ? row.customerId : row.supplierId || '')
    if (!partyId) continue
    const currency = debtCurrency(row)
    const key = `${partyId}::${currency}`
    let group = groups.get(key)
    if (!group) {
      group = {
        partyId,
        name: String((kind === 'customer' ? row.customer : row.supplier) || ''),
        currency,
        debts: [],
      }
      groups.set(key, group)
    }
    group.debts.push(row)
  }

  const summaries: PartyDebtSummary[] = []
  for (const [key, group] of groups) {
    const debts = [...group.debts].sort(oldestFirst)
    let invoiceTotal = 0
    let paidAmount = 0
    let remainingAmount = 0
    for (const debt of debts) {
      const remaining = Number(debt.remainingAmount || 0)
      const paid = Number(debt.paidAmount || 0)
      // Legacy rows without an explicit total fall back to paid + remaining.
      const total = debt.invoiceTotal ?? debt.totalAmount ?? (paid + remaining)
      invoiceTotal += Number(total || 0)
      paidAmount += paid
      remainingAmount += remaining
    }
    // Fully settled aggregates are dropped like any closed debt row.
    if (remainingAmount <= 0) continue
    const status = paidAmount > 0 ? 'PARTIAL' : 'UNPAID'
    const base = {
      id: key,
      currency: group.currency,
      // Source documents (oldest-first) — used for allocation + the receipt.
      debts,
      invoiceTotal: q4(invoiceTotal),
      totalAmount: q4(invoiceTotal),
      paidAmount: q4(paidAmount),
      remainingAmount: q4(remainingAmount),
      status,
      // Historical KHR-per-USD snapshot (oldest document) — prefills a dollar
      // collection against a KHR debt at the rate it was sold.
      exchangeRate: Number(debts[0]?.exchangeRate || 1) || 1,
      createdAt: debts[0]?.createdAt ?? debts[0]?.date ?? null,
      date: debts[0]?.date ?? null,
    }
    summaries.push(kind === 'customer'
      ? { ...base, customerId: group.partyId, customer: group.name }
      : { ...base, supplierId: group.partyId, supplier: group.name })
  }
  // Stable, predictable order: party name (then currency).
  return summaries.sort((a, b) => {
    const nameKey = kind === 'customer' ? 'customer' : 'supplier'
    const byName = String(a[nameKey] || '').localeCompare(String(b[nameKey] || ''))
    return byName !== 0 ? byName : String(a.currency).localeCompare(String(b.currency))
  })
}

/** One document settled by a lump debt payment (oldest-first allocation). */
export type DebtSettlementAllocation = {
  id: string
  docNo: string
  date: string
  amount: number
  remainingAfter: number
}

/**
 * Allocate a lump payment over a summary row's open documents oldest-first —
 * the exact order the backend settles them — so the receipt shows which
 * invoices the money covered. Amount over the outstanding is clamped.
 */
export function allocateDebtPayment(
  row: AppRecord | null | undefined,
  amount: number,
): DebtSettlementAllocation[] {
  const debts = Array.isArray(row?.debts) ? [...(row!.debts as AppRecord[])].sort(oldestFirst) : []
  let left = Math.max(0, Number(amount) || 0)
  const allocations: DebtSettlementAllocation[] = []
  for (const debt of debts) {
    if (left <= 0) break
    const remaining = Number(debt.remainingAmount || 0)
    if (remaining <= 0) continue
    const applied = Math.min(remaining, left)
    allocations.push({
      id: String(debt.id ?? ''),
      docNo: String(debt.invoiceNo ?? debt.purchaseNo ?? ''),
      date: String(debt.date ?? '').slice(0, 10),
      amount: q4(applied),
      remainingAfter: q4(remaining - applied),
    })
    left = q4(left - applied)
  }
  return allocations
}
