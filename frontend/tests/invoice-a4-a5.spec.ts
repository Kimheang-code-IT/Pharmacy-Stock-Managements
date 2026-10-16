import { describe, expect, it, beforeEach } from 'vitest'
import { configureFormats, DEFAULT_FORMAT_CONFIG } from '../app/utils/format/format-service'
import { PAPER_STYLES, printPageCss, PRINT_IFRAME_SIZES } from '../app/utils/print/html'
import {
  buildSaleInvoiceHtml,
  planInvoiceLayout,
  saleInvoicePrintInputFromRecord,
  saleReceiptPrintInput,
} from '../app/utils/print/invoice'
import type { SaleReceipt } from '../app/repositories/contracts/entities'

/** Intl may insert NBSP between groups — normalize for assertions. */
const normalize = (html: string) => html.replace(/\u00A0/g, ' ')

describe('invoice A4/A5 sizes (one component, two paper variants)', () => {
  beforeEach(() => {
    configureFormats(DEFAULT_FORMAT_CONFIG)
  })

  it('A4 renders a 210mm × 297mm page', () => {
    expect(PRINT_IFRAME_SIZES.A4).toEqual({ width: '210mm', height: '297mm' })
    expect(printPageCss('A4')).toContain('@page { size: A4;')
  })

  it('A5 renders a 148mm × 210mm page with a compact budget (no transform scale)', () => {
    expect(PRINT_IFRAME_SIZES.A5).toEqual({ width: '148mm', height: '210mm' })
    const css = printPageCss('A5')
    expect(css).toContain('@page { size: A5;')
    // A5 is its own metric set — never a transform:scale() of the A4 page.
    expect(css).not.toContain('transform')
  })

  it('shares one visual structure between A4 and A5 (same rule set)', () => {
    const ruleNames = (css: string) => css.split('}').map(rule => rule.split('{')[0]?.trim()).filter(Boolean).sort()
    expect(ruleNames(printPageCss('A4'))).toEqual(ruleNames(printPageCss('A5')))
  })

  it('keeps the existing visual structure on both sizes', () => {
    const input = {
      shopName: 'Demo Shop',
      invoiceNo: 'INV-000010',
      dateLabel: '10/09/26 10:00',
      customerName: 'Walk-in',
      cashier: 'admin',
      currency: 'USD',
      lines: [{ name: 'Glove', uom: 'PCS', quantity: 1, unitPrice: 3.15, discountPercent: 0 }],
      deliveryPrice: 0,
      previousDebtAmount: 0,
      depositAmount: 0,
      outstandingAmount: 3.15,
    }
    for (const size of ['A4', 'A5'] as const) {
      const html = buildSaleInvoiceHtml(input, size)
      expect(html).toContain('វិក្កយបត្រ / INVOICE')
      expect(html).toContain('លេខ Invoice')
      expect(html).toContain('កាលបរិច្ឆេទ Date')
      expect(html).toContain('អតិថិជន Customer')
      expect(html).toContain('បេឡា Cashier')
      expect(html).toContain('<span>N°</span>')
      expect(html).toContain('<span>Product</span>')
      expect(html).toContain('<span>Unit</span>')
      expect(html).toContain('<span>Qty</span>')
      expect(html).toContain('<span>Price</span>')
      expect(html).toContain('<span>Discount</span>')
      expect(html).toContain('<span>Amount</span>')
      expect(html).toContain('ទឹកប្រាក់សរុប / Total Amount')
      expect(html).toContain('ខ្វះសរុប')
      expect(html).toContain('អ្នកទិញ / Buyer')
      expect(html).toContain('អ្នកលក់ / Seller')
      // A5 shrinks spacing/metrics — not the layout structure.
      expect((html.match(/<tr class="empty stretch"/g) || []).length).toBeGreaterThan(0)
    }
  })

  it('keeps A5 fillers below A4 so signatures stay on page 1', () => {
    const input = {
      shopName: 'Demo Shop',
      invoiceNo: 'INV-000011',
      dateLabel: '10/09/26 10:00',
      customerName: 'Walk-in',
      cashier: 'admin',
      currency: 'USD',
      lines: [{ name: 'Glove', uom: 'PCS', quantity: 1, unitPrice: 3.15, discountPercent: 0 }],
      deliveryPrice: 0,
      previousDebtAmount: 0,
      depositAmount: 0,
      outstandingAmount: 3.15,
    }
    const countFillers = (html: string) => [...html.matchAll(/data-filler-rows="(\d+)"/g)]
      .reduce((sum, match) => sum + Number(match[1]), 0)
    const a4 = countFillers(buildSaleInvoiceHtml(input, 'A4'))
    const a5 = countFillers(buildSaleInvoiceHtml(input, 'A5'))
    expect(a5).toBeLessThan(a4)
  })

  it('repeats the table header on page breaks and never splits item rows', () => {
    const css = printPageCss('A4')
    expect(css).toContain('table.lines thead { display: table-header-group; }')
    expect(css).toContain('page-break-inside: avoid')
    expect(css).toContain('break-inside: avoid')
  })
})

describe('USD/KHR invoice printing (stored currency + rate)', () => {
  beforeEach(() => {
    configureFormats(DEFAULT_FORMAT_CONFIG)
  })

  it('prints USD amounts as $254.75', () => {
    const html = normalize(buildSaleInvoiceHtml({
      shopName: 'Demo Shop',
      invoiceNo: 'INV-000012',
      dateLabel: '10/09/26 10:00',
      customerName: 'Walk-in',
      cashier: 'admin',
      currency: 'USD',
      lines: [{ name: 'Glove', uom: 'PCS', quantity: 1, unitPrice: 254.75, discountPercent: 0 }],
      deliveryPrice: 0,
      previousDebtAmount: 0,
      depositAmount: 0,
      outstandingAmount: 254.75,
    }))
    expect(html).toContain('$254.75')
  })

  it('prints KHR amounts as 1,019,000៛ (whole riel, symbol after)', () => {
    const html = normalize(buildSaleInvoiceHtml({
      shopName: 'Demo Shop',
      invoiceNo: 'INV-000013',
      dateLabel: '10/09/26 10:00',
      customerName: 'Walk-in',
      cashier: 'admin',
      currency: 'KHR',
      lines: [{ name: 'Glove', uom: 'PCS', quantity: 1, unitPrice: 1019000, discountPercent: 0 }],
      deliveryPrice: 0,
      previousDebtAmount: 0,
      depositAmount: 0,
      outstandingAmount: 1019000,
    }))
    expect(html).toContain('1,019,000៛')
  })

  it('renders a KHR sale with the exchange rate printed in the meta block', () => {
    const html = normalize(buildSaleInvoiceHtml({
      shopName: 'Demo Shop',
      invoiceNo: 'INV-000014',
      dateLabel: '10/09/26 10:00',
      customerName: 'Walk-in',
      cashier: 'admin',
      currency: 'USD',
      lines: [{ name: 'Glove', uom: 'PCS', quantity: 1, unitPrice: 6.3, discountPercent: 0 }],
      deliveryPrice: 0,
      previousDebtAmount: 0,
      depositAmount: 0,
      outstandingAmount: 6.3,
      displayCurrency: 'KHR',
      exchangeRate: 4100,
    }))
    expect(html).toContain('25,830៛')
    expect(html).toContain('1 USD = 4,100 KHR')
  })

  it('never re-uses the current exchange rate on historical reprints', () => {
    const printInput = saleInvoicePrintInputFromRecord({
      invoiceNo: 'INV-000015',
      date: '2026-01-02T09:30:00Z',
      customer: 'Dara',
      cashier: 'Sokha',
      currency: 'KHR',
      exchangeRate: 4000,
      items: [{ name: 'Glove', uom: 'PCS', quantity: 2, price: 8200, discountPercent: 0 }],
      paidAmount: 8200,
      remaining: 8200,
    }, 'Demo Shop')
    // Stored snapshot currency/rate, not the shop's live rate.
    expect(printInput.currency).toBe('KHR')
    expect(printInput.displayCurrency).toBe('KHR')
    expect(printInput.exchangeRate).toBe(4000)
    const html = normalize(buildSaleInvoiceHtml(printInput, 'A4'))
    // 2 × 8,200 = 16,400 riel — converted nowhere else.
    expect(html).toContain('16,400៛')
  })

  it('derives a reprint input from the receipt payload (movement/history dialog)', () => {
    const receipt: SaleReceipt = {
      saleId: 's1',
      saleNo: 'SALE-000001',
      invoiceNo: 'INV-000016',
      date: '2026-02-01',
      customer: 'Walk-in customer',
      cashier: 'Sokha',
      paymentMethod: 'CASH',
      note: '',
      currency: 'KHR',
      exchangeRate: 4100,
      items: [{ name: 'Glove', quantity: 1, uom: 'PCS', unitPrice: 4100, discount: 0, total: 4100 }],
      subtotal: 4100,
      discount: 0,
      deliveryPrice: 0,
      deposit: 4100,
      total: 4100,
      paidAmount: 4100,
      remaining: 0,
    }
    const input = saleReceiptPrintInput(receipt, 'Demo Shop')
    expect(input.currency).toBe('KHR')
    const html = normalize(buildSaleInvoiceHtml(input, 'A5'))
    expect(html).toContain('INV-000016')
    expect(html).toContain('4,100៛')
  })

  it('reprint paid amount comes from the sale, never from a missing deposit', () => {
    // The receipt contract has no `deposit` value (always 0); the paid line
    // must use the sale's recorded paid amount — an invoice with $10 paid and
    // $20 remaining used to reprint as "paid 0".
    const receipt: SaleReceipt = {
      saleId: 's1',
      saleNo: 'SALE-000002',
      invoiceNo: 'INV-000017',
      date: '2026-02-01',
      customer: 'Walk-in customer',
      cashier: 'Sokha',
      paymentMethod: 'CUSTOMER_DEBT',
      note: '',
      currency: 'USD',
      exchangeRate: 1,
      items: [{ name: 'Glove', quantity: 2, uom: 'PCS', unitPrice: 15, discount: 0, total: 30 }],
      subtotal: 30,
      discount: 0,
      deliveryPrice: 0,
      deposit: 0,
      total: 30,
      paidAmount: 10,
      remaining: 20,
    }
    const input = saleReceiptPrintInput(receipt, 'Demo Shop')
    expect(input.depositAmount).toBe(10)
    expect(input.previousDebtAmount).toBe(0)
    expect(input.outstandingAmount).toBe(20)
    const html = normalize(buildSaleInvoiceHtml(input, 'A4'))
    // Paid $10 and outstanding $20 both render on the paper.
    expect(html).toContain('$10.00')
    expect(html).toContain('$20.00')
  })
})

describe('smart one-page invoice layout (A4/A5)', () => {
  beforeEach(() => {
    configureFormats(DEFAULT_FORMAT_CONFIG)
  })

  const invoiceInput = (count: number) => ({
    shopName: 'Demo Shop',
    invoiceNo: 'INV-000050',
    dateLabel: '10/09/26 10:00',
    customerName: 'Walk-in',
    cashier: 'admin',
    currency: 'USD',
    lines: Array.from({ length: count }, (_, index) => ({
      name: `Product ${index + 1}`,
      uom: 'PCS',
      quantity: 1,
      unitPrice: 3.15,
      discountPercent: 0,
    })),
    deliveryPrice: 0,
    previousDebtAmount: 0,
    depositAmount: 0,
    outstandingAmount: 3.15 * count,
  })

  const countFillers = (html: string) => [...html.matchAll(/data-filler-rows="(\d+)"/g)]
    .reduce((sum, match) => sum + Number(match[1]), 0)

  it('1 product → exactly one page, filled but never overflowing', () => {
    const plan = planInvoiceLayout(1, 'A4')
    expect(plan.pages).toBe(1)
    expect(plan.multipage).toBe(false)
    expect(plan.fillerRows).toBeGreaterThan(0)
    expect(countFillers(buildSaleInvoiceHtml(invoiceInput(1), 'A4'))).toBe(plan.fillerRows)
  })

  it('3 products → one page on A4', () => {
    const plan = planInvoiceLayout(3, 'A4')
    expect(plan.pages).toBe(1)
    expect(plan.fillerRows).toBe(plan.firstPageCapacity - 3)
    expect(countFillers(buildSaleInvoiceHtml(invoiceInput(3), 'A4'))).toBe(plan.fillerRows)
  })

  it('moderate counts are decided per paper size (A4 fits, A5 overflows)', () => {
    expect(planInvoiceLayout(18, 'A4').pages).toBe(1)
    expect(planInvoiceLayout(18, 'A5').multipage).toBe(true)
    expect(planInvoiceLayout(1, 'A5').pages).toBe(1)
    // Capacity is paper-specific — never one shared filler count.
    expect(planInvoiceLayout(0, 'A4').firstPageCapacity)
      .toBeGreaterThan(planInvoiceLayout(0, 'A5').firstPageCapacity)
  })

  it('many products → explicit two/three-page sheets with every item preserved', () => {
    const a4 = planInvoiceLayout(60, 'A4')
    expect(a4.multipage).toBe(true)
    expect(a4.pages).toBe(3)
    expect(a4.fillerRows).toBe(0)
    expect(a4.pageRows.reduce((sum, count) => sum + count, 0)).toBe(60)
    expect(a4.pageRows.every((count, index) => count <= (
      index === a4.pages - 1 ? a4.firstPageCapacity : a4.continuationPageCapacity
    ))).toBe(true)
    const a4Html = buildSaleInvoiceHtml(invoiceInput(60), 'A4')
    expect((a4Html.match(/class="invoice-page/g) || []).length).toBe(3)
    expect((a4Html.match(/វិក្កយបត្រ \/ INVOICE/g) || []).length).toBe(3)
    expect(a4Html).toContain('Page 3 / 3')
    expect(a4Html).toContain('Product 60')
    expect((a4Html.match(/class="doc-footer"/g) || []).length).toBe(1)

    const a5 = planInvoiceLayout(40, 'A5')
    expect(a5.multipage).toBe(true)
    expect(a5.pages).toBeGreaterThanOrEqual(2)
    expect(a5.fillerRows).toBe(0)
    expect(a5.pageRows.reduce((sum, count) => sum + count, 0)).toBe(40)
  })

  it('uses one continuous blank grid area instead of many horizontal filler lines', () => {
    const plan = planInvoiceLayout(3, 'A4')
    const html = buildSaleInvoiceHtml(invoiceInput(3), 'A4')
    expect((html.match(/<tr class="empty stretch"/g) || []).length).toBe(1)
    expect(html).toContain(`data-filler-rows="${plan.fillerRows}"`)
  })

  it('a one-page budget never exceeds the printable height on either size', () => {
    for (const size of ['A4', 'A5'] as const) {
      const style = PAPER_STYLES[size]
      const plan = planInvoiceLayout(1, size)
      const usedMm = style.headerMm + style.tableHeadMm
        + plan.firstPageCapacity * style.rowMm
        + style.footerMm
      expect(usedMm).toBeLessThanOrEqual(style.printableMm)
    }
  })

  it('keeps totals and signatures together, after the last product row', () => {
    const html = buildSaleInvoiceHtml(invoiceInput(3), 'A4')
    const footerStart = html.indexOf('<div class="doc-footer">')
    expect(footerStart).toBeGreaterThan(html.lastIndexOf('Product 3'))
    const footer = html.slice(footerStart)
    expect(footer).toContain('ទឹកប្រាក់សរុប / Total Amount')
    expect(footer).toContain('ខ្វះសរុប')
    expect(footer).toContain('អ្នកទិញ / Buyer')
    expect(footer).toContain('អ្នកលក់ / Seller')
  })

  it('footer block cannot split across pages and rows stay vertically centered', () => {
    for (const size of ['A4', 'A5'] as const) {
      const css = printPageCss(size)
      expect(css).toContain('.doc-footer')
      expect(css).toContain('break-inside: avoid')
      expect(css).toContain('page-break-inside: avoid')
      expect(css).toContain('vertical-align: middle')
    }
  })

  it('gives product rows extra padding with a uniform row height per size', () => {
    const cssA4 = printPageCss('A4')
    expect(cssA4).toContain('padding: 6px 3px')
    expect(cssA4).toContain(`height: ${PAPER_STYLES.A4.rowMm}mm`)
    const cssA5 = printPageCss('A5')
    expect(cssA5).toContain(`height: ${PAPER_STYLES.A5.rowMm}mm`)
    // The table itself has no fixed height; explicit physical page wrappers
    // own the page budget and prevent accidental blank sheets.
    expect(cssA4).not.toMatch(/table\.lines\s*\{[^}]*height\s*:/)
    expect(cssA4).not.toMatch(/min-height\s*:/)
    expect(cssA4).toContain(`height: ${PAPER_STYLES.A4.printableMm}mm`)
    expect(cssA4).toContain('page-break-after: always')
  })
})
