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

/** Intl may insert NBSP between currency code and amount — normalize for assertions. */
const normalize = (html: string) => html.replace(/\u00A0/g, ' ')

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
    expect(css).toContain('font-size: 13px')
    expect(css).toContain('.meta')
    expect(css).toContain('font-size: 16px')
    expect(css).toContain('font-size: 20px')
    expect(css).toContain('.meta p')
    expect(css).toContain('font-weight: 700')
    expect(css).toContain('table.lines')
    expect(css).toContain('border: 0.5px solid #000')
    expect(css).toContain('text-decoration: underline')
    expect(css).toContain('table.summary')
    expect(css).toContain('.col-product { width: 28%; }')
    expect(css).toContain('th.num { text-align: center; }')
    expect(css).toContain('tr.empty td')
    expect(css).toContain('border-top: none')
    expect(css).toContain('table.summary td.spacer')
    expect(PRINT_IFRAME_SIZES.A4).toEqual({ width: '210mm', height: '297mm' })
  })

  it('uses A5 page CSS and iframe size when A5 is chosen', () => {
    const css = printPageCss('A5')
    expect(css).toContain('@page { size: A5; margin: 6mm; }')
    expect(css).toContain('font-size: 10.4px')
    expect(css).toContain('border: 0.5px solid #000')
    expect(css).toContain('tr.empty td')
    expect(PRINT_IFRAME_SIZES.A5).toEqual({ width: '148mm', height: '210mm' })
  })

  it('renders the same bordered invoice style on A4 and A5 (scale only)', () => {
    const a4 = printPageCss('A4')
    const a5 = printPageCss('A5')
    expect(a4).toContain('border: 0.5px solid #000')
    expect(a5).toContain('border: 0.5px solid #000')
    expect(a4).toContain('text-decoration: underline')
    expect(a5).toContain('text-decoration: underline')
    expect(a4).toContain('.signs .line')
    expect(a5).toContain('.signs .line')
    expect(a4).toContain('th.num { text-align: center; }')
    expect(a5).toContain('th.num { text-align: center; }')
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
      previousDebtAmount: 0,
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
    expect(html).toContain('ល.រ')
    expect(html).toContain('<span>N°</span>')
    expect(html).toContain('មុខទំនិញ')
    expect(html).toContain('<span>Product</span>')
    expect(html).toContain('Little Bio &lt;Peach&gt;')
    expect(html).toContain('កំប៉ុង')
    expect(html).toContain('ទឹកប្រាក់សរុប / Total Amount')
    expect(html).toContain('ខ្វះមុន')
    expect(html).toContain('បានទូទាត់')
    expect(html).toContain('ខ្វះសរុប')
    expect(html).toContain('table class="lines"')
    expect(html).toContain('table class="summary"')
    expect(html).toContain('tr class="empty"')
    expect(html).toContain('class="spacer"')
    expect(html).toContain('colspan="2"')
    expect(html).toContain('class="line"')
    expect(html).toContain('អ្នកទិញ / Buyer')
    expect(html).toContain('អ្នកលក់ / Seller')
  })

  it('prints in the record currency when no print-currency choice is made', () => {
    const html = buildSaleInvoiceHtml({
      shopName: 'Demo Shop',
      invoiceNo: 'INV-000001',
      dateLabel: '07/09/26 22:10',
      customerName: 'Walk-in',
      cashier: 'admin',
      currency: 'USD',
      lines: [{ name: 'Glove', uom: 'PCS', quantity: 2, unitPrice: 3.15, discountPercent: 0 }],
      deliveryPrice: 0,
      previousDebtAmount: 0,
      depositAmount: 0,
      outstandingAmount: 6.3,
    })
    expect(html).toContain('$6.30')
    expect(html).not.toContain('Exchange rate')
  })

  it('converts invoice amounts to KHR using the chosen exchange rate', () => {
    const input = {
      shopName: 'Demo Shop',
      invoiceNo: 'INV-000001',
      dateLabel: '07/09/26 22:10',
      customerName: 'Walk-in',
      cashier: 'admin',
      currency: 'USD',
      lines: [{ name: 'Glove', uom: 'PCS', quantity: 2, unitPrice: 3.15, discountPercent: 0 }],
      deliveryPrice: 0,
      previousDebtAmount: 0,
      depositAmount: 0,
      outstandingAmount: 6.3,
      displayCurrency: 'KHR',
      exchangeRate: 4100,
    }
    const html = buildSaleInvoiceHtml(input)
    // Line amount: 2 × $3.15 = $6.30 → ៛25,830 (whole riel, no decimals)
    expect(normalize(html)).toContain('KHR 25,830')
    // Outstanding: $6.30 → ៛25,830
    expect(normalize(html)).toContain('KHR 25,830')
    // Rate stated in the meta block
    expect(html).toContain('អត្រាប្តូរប្រាក់ Exchange rate')
    expect(normalize(html)).toContain('1 USD = 4,100 KHR')
  })

  it('keeps USD printing when the sale is recorded in KHR and printed as USD', () => {
    const html = buildSaleInvoiceHtml({
      shopName: 'Demo Shop',
      invoiceNo: 'INV-000002',
      dateLabel: '07/09/26 22:10',
      customerName: 'Walk-in',
      cashier: 'admin',
      currency: 'KHR',
      lines: [{ name: 'Glove', uom: 'PCS', quantity: 1, unitPrice: 12345, discountPercent: 0 }],
      deliveryPrice: 0,
      previousDebtAmount: 0,
      depositAmount: 0,
      outstandingAmount: 12345,
      displayCurrency: 'USD',
      exchangeRate: 4100,
    })
    // 12,345 riel ÷ 4,100 = $3.01 (rounded to cents)
    expect(normalize(html)).toContain('$3.01')
    expect(normalize(html)).toContain('1 USD = 4,100 KHR')
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

  it('keeps the A5 signature block on page 1 for short sales (fewer fillers than A4)', () => {
    const input = {
      shopName: 'Demo Shop',
      invoiceNo: 'INV-000003',
      dateLabel: '07/09/26 22:10',
      customerName: 'Walk-in',
      cashier: 'admin',
      currency: 'USD',
      lines: [{ name: 'Glove', uom: 'PCS', quantity: 1, unitPrice: 3.15, discountPercent: 0 }],
      deliveryPrice: 0,
      previousDebtAmount: 0,
      depositAmount: 0,
      outstandingAmount: 3.15,
    }
    const countFillers = (html: string) => (html.match(/<tr class="empty">/g) || []).length
    const a4Fillers = countFillers(buildSaleInvoiceHtml(input, 'A4'))
    const a5Fillers = countFillers(buildSaleInvoiceHtml(input, 'A5'))
    // A5 printable height is ~30% smaller; its filler budget must shrink so
    // title + meta + summary + signatures still fit on page 1.
    expect(a5Fillers).toBeLessThan(a4Fillers)
    expect(a5Fillers).toBeGreaterThan(0)
  })
})
