import { describe, expect, it, beforeEach } from 'vitest'
import {
  configureFormats,
  DEFAULT_FORMAT_CONFIG,
} from '../app/utils/format/format-service'
import { escapeHtml, PRINT_IFRAME_SIZES, printPageCss } from '../app/utils/print/html'
import { buildSaleInvoiceHtml } from '../app/utils/print/invoice'
import {
  buildDeliveryNoteHtml,
  deliveryNotePrintInputFromRecord,
} from '../app/utils/print/delivery-note'

describe('print documents', () => {
  beforeEach(() => {
    configureFormats(DEFAULT_FORMAT_CONFIG)
  })

  it('escapes HTML in print values', () => {
    expect(escapeHtml('<script>alert(1)</script>')).toBe('&lt;script&gt;alert(1)&lt;/script&gt;')
  })

  it('uses A4 page CSS and iframe size by default and when A4 is chosen', () => {
    const css = printPageCss('A4')
    expect(css).toContain('@page { size: A4; margin: 8mm; }')
    expect(css).toContain('font-family: "Khmer OS Content", "Khmer OS", "Noto Sans Khmer", "Hanuman", sans-serif')
    expect(css).toContain('font-size: 10px')
    expect(css).toContain('table.lines { table-layout: fixed; }')
    expect(css).toContain('th, td { border: 1px solid #000; padding: 2px 3px;')
    expect(css).toContain('table.summary')
    expect(css).toContain('tr.empty td { height: 6mm; }')
    expect(PRINT_IFRAME_SIZES.A4).toEqual({ width: '210mm', height: '297mm' })
  })

  it('uses A5 page CSS and iframe size when A5 is chosen', () => {
    const css = printPageCss('A5')
    expect(css).toContain('@page { size: A5; margin: 6mm; }')
    expect(css).toContain('font-size: 8px')
    expect(css).toContain('th, td { border: 1px solid #000; padding: 1.6px 2.4px;')
    expect(css).toContain('tr.empty td { height: 4.8mm; }')
    expect(PRINT_IFRAME_SIZES.A5).toEqual({ width: '148mm', height: '210mm' })
  })

  it('renders the same bordered invoice style on A4 and A5 (scale only)', () => {
    const a4 = printPageCss('A4')
    const a5 = printPageCss('A5')
    // Same rule set — both papers get the bordered lines grid and summary.
    expect(a4).toContain('th, td { border: 1px solid #000')
    expect(a5).toContain('th, td { border: 1px solid #000')
    expect(a4).not.toContain('border: none')
    expect(a5).not.toContain('border: none')
    // Identical rule names, only values scaled.
    const ruleNames = (css: string) => css.split('}').map(rule => rule.split('{')[0]?.trim()).filter(Boolean).sort()
    expect(ruleNames(a4)).toEqual(ruleNames(a5))
  })

  it('builds a bilingual sale invoice with lines and totals', () => {
    const html = buildSaleInvoiceHtml({
      shopName: 'Demo Shop',
      invoiceNo: 'INV-000001',
      dateLabel: '07/09/26 22:10',
      customerName: 'Ph Yoeun Sokhon',
      cashier: 'admin',
      currency: 'USD',
      lines: [{
        name: 'Little Bio <Peach>',
        uom: 'កំប៉ុង',
        quantity: 2,
        unitPrice: 3.15,
        discountPercent: 0,
      }],
      deliveryPrice: 0,
      depositAmount: 0,
      outstandingAmount: 6.3,
    })
    expect(html).toContain('វិក្កយបត្រ / INVOICE')
    expect(html).not.toContain('Demo Shop')
    expect(html).not.toContain('Yoeun Sokhon Pharmacy')
    expect(html).toContain('INV-000001')
    expect(html).toContain('Ph Yoeun Sokhon')
    expect(html).toContain('បេឡា Cashier')
    expect(html).toContain('admin')
    expect(html).toContain('ល.រ N°')
    expect(html).toContain('មុខទំនិញ Product')
    expect(html).toContain('Little Bio &lt;Peach&gt;')
    expect(html).toContain('កំប៉ុង')
    expect(html).toContain('ខ្វះសរុប')
    expect(html).toContain('table class="lines"')
    expect(html).toContain('table class="summary"')
    expect(html).toContain('tr class="empty"')
    expect(html).toContain('អ្នកទិញ / Buyer')
  })

  it('builds a bilingual delivery note from a record', () => {
    const input = deliveryNotePrintInputFromRecord({
      deliveryNo: 'DN-000001',
      createdAt: '2026-09-07T15:00:00Z',
      invoiceNo: 'INV-000001',
      status: 'Confirmed',
      customer: 'Walk-in customer',
      deliveryName: 'Receiver',
      deliveryPhone: '012',
      deliveryAddress: 'Phnom Penh',
      scheduledDate: '2026-09-08',
      items: [{ product: 'Glove TG S', uomSymbol: 'ប្រអប់', qtyOrdered: 3, qtyToDeliver: 2 }],
    }, 'Demo Shop')
    const html = buildDeliveryNoteHtml(input)
    expect(html).toContain('ប័ណ្ណដឹកជញ្ជូន / DELIVERY NOTE')
    expect(html).toContain('DN-000001')
    expect(html).toContain('INV-000001')
    expect(html).toContain('Glove TG S')
    expect(html).toContain('អ្នកទទួល / Receiver')
  })
})
