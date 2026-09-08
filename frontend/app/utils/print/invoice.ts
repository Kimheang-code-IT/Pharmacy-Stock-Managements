import { formatMoney } from '~/utils/format/format-service'
import { cartTotal, lineNet, type PosCartLine } from '~/utils/pos/cart'
import { escapeHtml, PAPER_STYLES, printHtmlDocument, type PrintPaperSize } from '~/utils/print/html'

/** Fixed invoice chrome above/below the grid (title, meta, totals, signatures) at scale 1, mm. */
const CHROME_MM = 84
/** Fewest grid rows so even a one-line invoice reads like a shop form. */
const MIN_GRID_ROWS = 18

/**
 * Grid rows that fit between the invoice chrome and the page bottom on the
 * given paper — the bordered grid fills the printable area on both A4 and A5
 * with the same logic (printable height ÷ row height, per paper metrics).
 */
function totalGridRows(paperSize: PrintPaperSize): number {
  const style = PAPER_STYLES[paperSize]
  const gridMm = Math.max(0, style.printableMm - CHROME_MM * style.scalePx)
  return Math.max(MIN_GRID_ROWS, Math.floor(gridMm / style.rowMm))
}

export type SaleInvoicePrintLine = Pick<
  PosCartLine,
  'name' | 'uom' | 'quantity' | 'unitPrice' | 'discountPercent'
>

export type SaleInvoicePrintInput = {
  shopName: string
  invoiceNo: string
  dateLabel: string
  customerName: string
  cashier: string
  currency: string
  lines: SaleInvoicePrintLine[]
  deliveryPrice: number
  depositAmount: number
  outstandingAmount: number
}

function asCartLine(line: SaleInvoicePrintLine): PosCartLine {
  return {
    productId: '',
    barcode: '',
    imageUrl: null,
    availableStock: 0,
    uomId: '',
    factorToBase: 1,
    uomOptions: [],
    ...line,
  }
}

function emptyInvoiceRows(filled: number, paperSize: PrintPaperSize): string {
  const missing = Math.max(0, totalGridRows(paperSize) - filled)
  return Array.from({ length: missing }, () => `
    <tr class="empty">
      <td class="num">&nbsp;</td>
      <td></td>
      <td></td>
      <td></td>
      <td></td>
      <td></td>
      <td></td>
    </tr>`).join('')
}

export function buildSaleInvoiceHtml(
  input: SaleInvoicePrintInput,
  paperSize: PrintPaperSize = 'A4',
): string {
  const money = (value: unknown) => escapeHtml(formatMoney(value, input.currency))
  const lines = input.lines.map(asCartLine)
  const total = cartTotal(lines)
  const rows = lines.map((line, index) => `
    <tr>
      <td class="num">${index + 1}</td>
      <td>${escapeHtml(line.name)}</td>
      <td>${escapeHtml(line.uom || '—')}</td>
      <td class="num">${escapeHtml(line.quantity)}</td>
      <td class="num">${money(line.unitPrice)}</td>
      <td class="num">${escapeHtml(line.discountPercent || 0)}%</td>
      <td class="num">${money(lineNet(line))}</td>
    </tr>`).join('')

  return `
<article class="doc">
  <p class="title">វិក្កយបត្រ / INVOICE</p>
  <div class="meta">
    <div>
      <p>លេខ Invoice : <strong>${escapeHtml(input.invoiceNo)}</strong></p>
      <p>កាលបរិច្ឆេទ Date : <strong>${escapeHtml(input.dateLabel)}</strong></p>
    </div>
    <div class="right">
      <p>អតិថិជន Customer : <strong>${escapeHtml(input.customerName)}</strong></p>
      <p>បេឡា Cashier : <strong>${escapeHtml(input.cashier)}</strong></p>
    </div>
  </div>
  <table class="lines">
    <colgroup>
      <col class="col-no">
      <col class="col-product">
      <col class="col-unit">
      <col class="col-qty">
      <col class="col-price">
      <col class="col-discount">
      <col class="col-amount">
    </colgroup>
    <thead>
      <tr>
        <th>ល.រ N°</th>
        <th>មុខទំនិញ Product</th>
        <th>ឯកតា Unit</th>
        <th class="num">ចំនួន Qty</th>
        <th class="num">តម្លៃ Price</th>
        <th class="num">បញ្ចុះតម្លៃ Discount</th>
        <th class="num">តម្លៃសរុប Amount</th>
      </tr>
    </thead>
    <tbody>${rows}${emptyInvoiceRows(lines.length, paperSize)}</tbody>
  </table>
  <div class="totals">
    <table class="summary">
      <tr>
        <td class="label">ទឹកប្រាក់សរុប Total Amount</td>
        <td class="num">${money(total)}</td>
      </tr>
      <tr>
        <td class="label">តម្លៃដឹកជញ្ជូន Delivery</td>
        <td class="num">${money(input.deliveryPrice)}</td>
      </tr>
      <tr>
        <td class="label">បានទូទាត់ Deposit</td>
        <td class="num">${money(input.depositAmount)}</td>
      </tr>
      <tr class="strong">
        <td class="label">ខ្វះសរុប</td>
        <td class="num">${money(input.outstandingAmount)}</td>
      </tr>
    </table>
  </div>
  <div class="signs">
    <p>អ្នកទិញ / Buyer</p>
    <p>អ្នកលក់ / Seller</p>
  </div>
</article>`
}

/** Print the invoice in the chosen paper size (POS chooser: A4 default). */
export function printSaleInvoice(input: SaleInvoicePrintInput, paperSize: PrintPaperSize = 'A4'): Promise<void> {
  return printHtmlDocument(buildSaleInvoiceHtml(input, paperSize), input.invoiceNo || 'Invoice', { paperSize })
}
