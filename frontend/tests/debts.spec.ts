import { describe, expect, it } from 'vitest'
import { allocateDebtPayment, debtBalanceEntries, debtCurrency, isOpenDebt, openDebts, selectedDebtsShareScope, selectedDebtsTotal, summarizeDebtsByParty } from '../app/utils/reports/debts'
import type { AppRecord } from '../app/config/admin-seed'

function row(partial: Partial<AppRecord>): AppRecord {
  return partial as AppRecord
}

describe('debt currency + multi-pay scope', () => {
  it('uses the debt document currency over the UI fallback', () => {
    expect(debtCurrency(row({ currency: 'KHR' }), 'USD')).toBe('KHR')
    expect(debtCurrency(row({}), 'KHR')).toBe('KHR')
    expect(debtCurrency(row({}), '')).toBe('USD')
    expect(debtCurrency(null, 'KHR')).toBe('KHR')
  })

  it('allows batching only same customer + currency', () => {
    const c1 = row({ customerId: 'c1', currency: 'USD' })
    const c1b = row({ customerId: 'c1', currency: 'USD' })
    const c2 = row({ customerId: 'c2', currency: 'USD' })
    const c1Khr = row({ customerId: 'c1', currency: 'KHR' })

    expect(selectedDebtsShareScope([c1], 'customer')).toBe(true)
    expect(selectedDebtsShareScope([c1, c1b], 'customer')).toBe(true)
    expect(selectedDebtsShareScope([c1, c2], 'customer')).toBe(false)
    expect(selectedDebtsShareScope([c1, c1Khr], 'customer')).toBe(false)
  })

  it('scopes supplier rows by supplierId', () => {
    const s1 = row({ supplierId: 's1', currency: 'USD' })
    const s2 = row({ supplierId: 's2', currency: 'USD' })
    expect(selectedDebtsShareScope([s1], 'supplier')).toBe(true)
    expect(selectedDebtsShareScope([s1, s2], 'supplier')).toBe(false)
  })

  it('sums the selected remaining balance without float drift', () => {
    expect(selectedDebtsTotal([
      row({ remainingAmount: 0.1 }),
      row({ remainingAmount: 0.2 }),
    ])).toBe(0.3)
    expect(selectedDebtsTotal([
      row({ remainingAmount: 12 }),
      row({ remainingAmount: 0.5 }),
    ])).toBe(12.5)
    expect(selectedDebtsTotal([])).toBe(0)
  })
})

describe('open debt filtering', () => {
  it('keeps unpaid and partially paid debts', () => {
    expect(isOpenDebt(row({ remainingAmount: 10, status: 'UNPAID' }))).toBe(true)
    expect(isOpenDebt(row({ remainingAmount: 3.5, status: 'PARTIAL' }))).toBe(true)
  })

  it('drops fully settled debts', () => {
    expect(isOpenDebt(row({ remainingAmount: 0, status: 'PAID' }))).toBe(false)
    expect(isOpenDebt(row({ remainingAmount: 0, status: 'UNPAID' }))).toBe(false)
    expect(isOpenDebt(row({ status: 'PAID' }))).toBe(false)
    expect(isOpenDebt(null)).toBe(false)
  })

  it('filters a debt list down to open rows', () => {
    const rows = [
      row({ remainingAmount: 0, status: 'PAID' }),
      row({ remainingAmount: 12, status: 'PARTIAL' }),
      row({ remainingAmount: 5, status: 'UNPAID' }),
    ]
    expect(openDebts(rows).map(item => item.remainingAmount)).toEqual([12, 5])
  })
})

describe('party summary rows (debt reports)', () => {
  const debt = (partial: Partial<AppRecord>) => row(partial)

  it('groups a customer\u2019s open invoices into ONE row with totalled amounts', () => {
    const rows = [
      debt({
        id: 'd1',
        customerId: 'c1',
        customer: 'aaaaaaa',
        currency: 'USD',
        invoiceTotal: 30,
        paidAmount: 10,
        remainingAmount: 20,
        createdAt: '2026-10-16T08:00:00Z',
      }),
      debt({
        id: 'd2',
        customerId: 'c1',
        customer: 'aaaaaaa',
        currency: 'USD',
        invoiceTotal: 15,
        paidAmount: 0,
        remainingAmount: 15,
        createdAt: '2026-10-16T09:00:00Z',
      }),
      // Fully settled rows never join a summary.
      debt({
        id: 'd3',
        customerId: 'c1',
        customer: 'aaaaaaa',
        currency: 'USD',
        invoiceTotal: 5,
        paidAmount: 5,
        remainingAmount: 0,
        status: 'PAID',
        createdAt: '2026-10-16T10:00:00Z',
      }),
    ]
    const summaries = summarizeDebtsByParty(rows, 'customer')
    expect(summaries).toHaveLength(1)
    const summary = summaries[0]!
    expect(summary.customer).toBe('aaaaaaa')
    expect(summary.invoiceTotal).toBe(45)
    expect(summary.paidAmount).toBe(10)
    expect(summary.remainingAmount).toBe(35)
    expect(summary.status).toBe('PARTIAL')
    // Source documents ride along oldest-first for lump payments/receipt.
    expect((summary.debts as AppRecord[]).map(item => item.id)).toEqual(['d1', 'd2'])
  })

  it('never sums different currencies into one row', () => {
    const rows = [
      debt({ id: 'd1', customerId: 'c1', customer: 'A', currency: 'USD', remainingAmount: 20, paidAmount: 0 }),
      debt({ id: 'd2', customerId: 'c1', customer: 'A', currency: 'KHR', remainingAmount: 410000, paidAmount: 0 }),
    ]
    const summaries = summarizeDebtsByParty(rows, 'customer')
    expect(summaries).toHaveLength(2)
    const usd = summaries.find(item => item.currency === 'USD')!
    const khr = summaries.find(item => item.currency === 'KHR')!
    expect(usd.remainingAmount).toBe(20)
    expect(khr.remainingAmount).toBe(410000)
  })

  it('keeps suppliers in their own rows and derives UNPAID when nothing was paid', () => {
    const rows = [
      debt({ id: 'd1', supplierId: 's1', supplier: 'aaa', currency: 'USD', totalAmount: 110, paidAmount: 0, remainingAmount: 110 }),
      debt({ id: 'd2', supplierId: 's2', supplier: 'bbb', currency: 'USD', totalAmount: 1, paidAmount: 0, remainingAmount: 1 }),
    ]
    const summaries = summarizeDebtsByParty(rows, 'supplier')
    expect(summaries.map(item => item.supplier)).toEqual(['aaa', 'bbb'])
    expect(summaries[0]!.status).toBe('UNPAID')
    expect(summaries[0]!.totalAmount).toBe(110)
  })

  it('allocates a lump payment over the summary oldest-first, clamping the last row', () => {
    const summary = row({
      id: 'c1::USD',
      customerId: 'c1',
      currency: 'USD',
      remainingAmount: 30,
      debts: [
        { id: 'd2', invoiceNo: 'INV-000002', date: '2026-10-16', remainingAmount: 10, createdAt: '2026-10-16T09:00:00Z' },
        { id: 'd1', invoiceNo: 'INV-000001', date: '2026-10-16', remainingAmount: 20, createdAt: '2026-10-16T08:00:00Z' },
      ],
    })
    const allocations = allocateDebtPayment(summary, 25)
    expect(allocations.map(item => [item.docNo, item.amount, item.remainingAfter])).toEqual([
      ['INV-000001', 20, 0],
      ['INV-000002', 5, 5],
    ])
    // Overpay is clamped to the outstanding balance.
    expect(allocateDebtPayment(summary, 99).reduce((sum, item) => sum + item.amount, 0)).toBe(30)
  })
})

describe('customer/supplier outstanding debt entries', () => {
  it('returns positive balances per currency and never mixes currencies', () => {
    expect(debtBalanceEntries(row({ debtBalances: { USD: 35, KHR: 410000 } }))).toEqual([
      { currency: 'KHR', amount: 410000 },
      { currency: 'USD', amount: 35 },
    ])
    expect(debtBalanceEntries(row({ debtBalances: { USD: 35, KHR: 0 } }))).toEqual([
      { currency: 'USD', amount: 35 },
    ])
  })

  it('falls back to the stored scalar (mock/local mode)', () => {
    expect(debtBalanceEntries(row({ debtBalance: 42 }))).toEqual([{ currency: 'USD', amount: 42 }])
    expect(debtBalanceEntries(row({ totalDebt: 7, currency: 'KHR' }))).toEqual([{ currency: 'KHR', amount: 7 }])
  })

  it('is empty when the party owes nothing', () => {
    expect(debtBalanceEntries(row({}))).toEqual([])
    expect(debtBalanceEntries(row({ debtBalances: { USD: 0 } }))).toEqual([])
    expect(debtBalanceEntries(row({ debtBalance: 0 }))).toEqual([])
    expect(debtBalanceEntries(null)).toEqual([])
  })
})
