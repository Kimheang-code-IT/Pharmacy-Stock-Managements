import { beforeEach, describe, expect, it } from 'vitest'
import { configureFormats, DEFAULT_FORMAT_CONFIG } from '../app/utils/format/format-service'
import { buildPaymentReceiptHtml, type PaymentReceiptInput } from '../app/utils/print/payment-receipt'

/** Intl may insert NBSP between groups — normalize for assertions. */
const normalize = (html: string) => html.replace(/\u00A0/g, ' ')

const input: PaymentReceiptInput = {
  shopName: 'Yoeun Sokhon Pharmacy',
  partyKind: 'customer',
  partyName: 'aaaaaaa',
  receiptNo: 'PAY-00001',
  dateLabel: '16/10/26 21:30',
  cashier: 'admin',
  currency: 'USD',
  paymentMethod: 'Cash',
  reference: '',
  balanceBefore: 35,
  amountPaid: 25,
  balanceAfter: 10,
  documents: [
    { docNo: 'INV-000001', date: '2026-10-16', amount: 20 },
    { docNo: 'INV-000002', date: '2026-10-16', amount: 5 },
  ],
}

describe('debt payment receipt (sale-invoice paper, A4/A5)', () => {
  beforeEach(() => {
    configureFormats(DEFAULT_FORMAT_CONFIG)
  })

  it('renders the settled invoices, balances and signature blocks', () => {
    const html = normalize(buildPaymentReceiptHtml(input, 'A5'))
    expect(html).toContain('បង្កាន់ដៃទូទាត់ / PAYMENT RECEIPT')
    expect(html).toContain('PAY-00001')
    expect(html).toContain('aaaaaaa')
    // Every invoice the lump payment settled, oldest-first.
    expect(html).toContain('INV-000001')
    expect(html).toContain('INV-000002')
    // Balances: before 35, paid now 25, after 10.
    expect(html).toContain('$35.00')
    expect(html).toContain('$25.00')
    expect(html).toContain('$10.00')
    expect(html).toContain('អ្នកបង់ប្រាក់ / Payer')
    expect(html).toContain('អ្នកទទួល / Receiver')
  })

  it('uses the sale-invoice page style: one fixed sheet + filler grid for a short list', () => {
    const html = buildPaymentReceiptHtml(input, 'A5')
    expect(html).toContain('class="doc"')
    expect(html).toContain('class="invoice-page last"')
    expect(html).toContain('data-filler-rows=')
    expect(html).toContain('class="lines"')
    expect(html).toContain('class="summary"')
    expect(html).toContain('class="doc-footer"')
  })

  it('long lists flow naturally instead of clipping a fixed sheet', () => {
    const many: PaymentReceiptInput = {
      ...input,
      documents: Array.from({ length: 40 }, (_, index) => ({
        docNo: `INV-${index + 100}`,
        date: '2026-10-16',
        amount: 1,
      })),
    }
    const html = buildPaymentReceiptHtml(many, 'A5')
    expect(html).not.toContain('invoice-page')
    expect(html).not.toContain('data-filler-rows')
    expect(html).toContain('INV-139')
  })

  it('prints the reference line only when a reference is provided', () => {
    expect(buildPaymentReceiptHtml({ ...input, reference: '' }, 'A5')).not.toContain('Reference')
    expect(buildPaymentReceiptHtml({ ...input, reference: 'TRX-9' }, 'A5')).toContain('TRX-9')
  })

  it('escapes party/document values into the HTML', () => {
    const html = buildPaymentReceiptHtml({
      ...input,
      partyName: '<script>alert(1)</script>',
      documents: [{ docNo: '<b>INV</b>', date: '2026-10-16', amount: 1 }],
    }, 'A4')
    expect(html).not.toContain('<script>')
    expect(html).toContain('&lt;script&gt;')
    expect(html).toContain('&lt;b&gt;INV&lt;/b&gt;')
  })

  it('prints the collected currency when it differs from the debt\u2019s own', () => {
    // Riel cash collected for a USD debt: the receipt shows the received riel
    // amount + rate next to the USD settlement (never a mixed total).
    const html = normalize(buildPaymentReceiptHtml({
      ...input,
      collectedCurrency: 'KHR',
      collectedAmount: 82000,
      exchangeRate: 4100,
    }, 'A5'))
    expect(html).toContain('បានទទួល Received')
    expect(html).toContain('82,000៛')
    expect(html).toContain('1 USD = 4,100 KHR')
    // The settled totals stay in the debt's own currency.
    expect(html).toContain('$25.00')
    expect(html).toContain('$35.00')
    // Same-currency collections do not repeat the amount.
    const plain = buildPaymentReceiptHtml({ ...input, collectedCurrency: 'USD', collectedAmount: 25 }, 'A5')
    expect(plain).not.toContain('បានទទួល Received')
  })

  it('prints KHR amounts as whole riel', () => {
    const html = normalize(buildPaymentReceiptHtml({
      ...input,
      currency: 'KHR',
      balanceBefore: 410000,
      amountPaid: 410000,
      balanceAfter: 0,
      documents: [{ docNo: 'INV-000009', date: '2026-10-16', amount: 410000 }],
    }, 'A5'))
    expect(html).toContain('410,000៛')
  })
})
