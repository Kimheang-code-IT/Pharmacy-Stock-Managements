import { describe, expect, it } from 'vitest'
import { normalizePartyHistory, partyDay } from '../app/utils/party/ledger'

describe('party history normalizer', () => {
  it('maps a customer sale-history row', () => {
    const row = normalizePartyHistory('customer', {
      id: 's1',
      invoice_no: 'INV-1',
      sale_date: '2026-01-01T09:00:00Z',
      grand_total: '100.00',
      paid_amount: '60.00',
      debt_amount: '40.00',
      payment_status: 'PARTIAL',
      sale_status: 'COMPLETED',
      cashier_name: 'Cashier A',
      currency: 'KHR',
    })
    expect(row).toEqual({
      id: 's1',
      documentNo: 'INV-1',
      date: '2026-01-01T09:00:00Z',
      total: 100,
      paidAmount: 60,
      debtAmount: 40,
      status: 'PARTIAL',
      currency: 'KHR',
      user: 'Cashier A',
    })
  })

  it('maps a supplier purchase-history row', () => {
    const row = normalizePartyHistory('supplier', {
      id: 't1',
      document_no: 'PIN-1',
      transaction_date: '2026-02-02T00:00:00Z',
      total: '250.00',
      paid_amount: '100.00',
      remaining_amount: '150.00',
      status: 'PARTIAL',
      user_name: 'Stock Clerk',
    })
    expect(row.documentNo).toBe('PIN-1')
    expect(row.total).toBe(250)
    expect(row.paidAmount).toBe(100)
    expect(row.debtAmount).toBe(150)
    expect(row.status).toBe('PARTIAL')
    expect(row.user).toBe('Stock Clerk')
  })

  it('exposes an inclusive YYYY-MM-DD day bucket', () => {
    expect(partyDay('2026-02-02T23:59:59Z')).toBe('2026-02-02')
    expect(partyDay('')).toBe('')
  })
})
