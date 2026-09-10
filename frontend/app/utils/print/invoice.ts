import { formatMoney, formatNumber } from '~/utils/format/format-service'
import { cartTotal, lineNet, type PosCartLine } from '~/utils/pos/cart'
import { escapeHtml, PAPER_STYLES, printHtmlDocument, type PrintPaperSize } from '~/utils/print/html'

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
  /** Customer's open (unpaid) debt before this sale — printed as ខ្វះមុន. */
  previousDebtAmount: number
  /** Cash received at checkout (covers this sale + any settled previous debt). */
  depositAmount: number
  /** Amount still owed after this sale, including previous debt not settled now. */
  outstandingAmount: number
  /** Currency to render the printed document in (defaults to `currency`). */
  displayCurrency?: string
  /** Exchange rate as **1 USD = X KHR**; required when `displayCurrency` differs. */
  exchangeRate?: number
}

/**
 * Print-currency choice made in the document print chooser: the paper
 * currency (USD/KHR, defaulting to the record currency) plus the exchange
 * rate applied when the print currency differs from the record currency.
 */
export type PrintCurrencyChoice = {
  currency: string
  exchangeRate?: number
}

/**
 * Format an amount for the printed document, converting between the record
 * currency and the print currency when they differ. Rate is always stated as
 * **1 USD = X KHR**; KHR amounts are rounded to whole riel (no decimals).
 */
function formatPrintMoney(
  value: unknown,
  recordCurrency: string,
  displayCurrency: string,
  exchangeRate: number,
): string {
  const amount = Number(value || 0)
  const converting = displayCurrency !== recordCurrency && exchangeRate > 0
  const converted = converting
    ? (displayCurrency === 'KHR' ? amount * exchangeRate : amount / exchangeRate)
    : amount
  const code = converting ? displayCurrency : recordCurrency
  if (code === 'KHR') {
    return formatNumber(Math.round(converted), { style: 'currency', currency: 'KHR', maximumFractionDigits: 0 })
  }
  return formatMoney(converted, code)
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

/**
 * Height reserved on page 1 for the fixed blocks (title, meta, summary rows,
 * buyer/seller signature lines) outside the lines grid. Filler rows are sized
 * from what is left so the signatures stay on page 1 — a fixed 70% target
 * used to push the A5 signature block onto page 2 even for short sales.
 * A4 keeps the previous 70%-target behaviour (281 − 84 ≈ 197mm).
 */
const FIXED_PAGE1_MM: Record<PrintPaperSize, number> = {
  A4: 84,
  A5: 76,
}

/** Filler rows trimmed below the budget so short sales stay safely on one page. */
const FILLER_TRIM: Record<PrintPaperSize, number> = {
  A4: 3,
  A5: 5,
}

/**
 * Empty filler rows so the lines grid fills the page-1 budget left after the
 * fixed blocks (shop-form look) without forcing a short sale — and its
 * signatures — onto page 2 when product rows already cover that space.
 */
function emptyInvoiceRows(filled: number, paperSize: PrintPaperSize): string {
  const style = PAPER_STYLES[paperSize]
  const targetMm = style.printableMm - FIXED_PAGE1_MM[paperSize]
  const headerMm = style.rowMm * 1.6
  const bodyMm = Math.max(0, targetMm - headerMm)
  const totalRows = Math.max(filled, Math.floor(bodyMm / style.rowMm))
  const missing = Math.max(0, totalRows - filled - FILLER_TRIM[paperSize])
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

function summaryRow(label: string, amountHtml: string, strong = false): string {
  const cls = strong ? ' class="strong"' : ''
  return `
      <tr${cls}>
        <td class="spacer" colspan="4"></td>
        <td class="label" colspan="2">${label}</td>
        <td class="num">${amountHtml}</td>
      </tr>`
}

/**
 * Build invoice HTML. Product rows + empty fillers (~70% page height).
 * Totals label aligns with Price+Discount; amount aligns with Amount.
 */
export function buildSaleInvoiceHtml(
  input: SaleInvoicePrintInput,
  paperSize: PrintPaperSize = 'A4',
): string {
  const displayCurrency = input.displayCurrency || input.currency
  const exchangeRate = Number(input.exchangeRate || 0)
  const converting = displayCurrency !== input.currency && exchangeRate > 0
  const money = (value: unknown) => escapeHtml(formatPrintMoney(value, input.currency, displayCurrency, exchangeRate))
  const lines = input.lines.map(asCartLine)
  const total = cartTotal(lines)
  const rows = lines.map((line, index) => `
    <tr>
      <td class="num">${index + 1}</td>
      <td class="product">${escapeHtml(line.name)}</td>
      <td>${escapeHtml(line.uom || '—')}</td>
      <td class="num">${escapeHtml(line.quantity)}</td>
      <td class="num">${money(line.unitPrice)}</td>
      <td class="num">${escapeHtml(line.discountPercent || 0)}%</td>
      <td class="num">${money(lineNet(line))}</td>
    </tr>`).join('')

  const colgroup = `
    <colgroup>
      <col class="col-no">
      <col class="col-product">
      <col class="col-unit">
      <col class="col-qty">
      <col class="col-price">
      <col class="col-discount">
      <col class="col-amount">
    </colgroup>`

  return `
<article class="doc">
  <p class="title">វិក្កយបត្រ / INVOICE</p>
  <div class="meta">
    <div>
      <p>លេខ Invoice : <strong>${escapeHtml(input.invoiceNo)}</strong></p>
      <p>កាលបរិច្ឆេទ Date : <strong>${escapeHtml(input.dateLabel)}</strong></p>${converting ? `\n      <p>អត្រាប្តូរប្រាក់ Exchange rate : <strong>1 USD = ${escapeHtml(formatNumber(Math.round(exchangeRate)))} KHR</strong></p>` : ''}
    </div>
    <div class="right">
      <p>អតិថិជន Customer : <strong>${escapeHtml(input.customerName)}</strong></p>
      <p>បេឡា Cashier : <strong>${escapeHtml(input.cashier)}</strong></p>
    </div>
  </div>
  <table class="lines">
    ${colgroup}
    <thead>
      <tr>
        <th>ល.រ<span>N°</span></th>
        <th>មុខទំនិញ<span>Product</span></th>
        <th>ឯកតា<span>Unit</span></th>
        <th class="num">ចំនួន<span>Qty</span></th>
        <th class="num">តម្លៃ<span>Price</span></th>
        <th class="num">បញ្ចុះតម្លៃ<span>Discount</span></th>
        <th class="num">តម្លៃសរុប<span>Amount</span></th>
      </tr>
    </thead>
    <tbody>${rows}${emptyInvoiceRows(lines.length, paperSize)}</tbody>
  </table>
  <div class="totals">
    <table class="summary">
      ${colgroup}
      ${summaryRow('ទឹកប្រាក់សរុប / Total Amount', money(total))}
      ${summaryRow('ខ្វះមុន', money(input.previousDebtAmount))}
      ${summaryRow('តម្លៃដឹកជញ្ជូន_____/_____/_____', money(input.deliveryPrice))}
      ${summaryRow('បានទូទាត់_____/_____/_____', money(input.depositAmount))}
      ${summaryRow('ខ្វះសរុប', money(input.outstandingAmount), true)}
    </table>
  </div>
  <div class="signs"> 
    <div class="sign">
      <div class="line"></div>
      <p>អ្នកទិញ / Buyer</p>
    </div>
    <div class="sign">
      <div class="line"></div>
      <p>អ្នកលក់ / Seller</p>
    </div>
  </div>
</article>`
}

/** Print the invoice in the chosen paper size and print currency (POS chooser). */
export function printSaleInvoice(
  input: SaleInvoicePrintInput,
  paperSize: PrintPaperSize = 'A4',
  currencyChoice?: PrintCurrencyChoice,
): Promise<void> {
  const printInput: SaleInvoicePrintInput = currencyChoice
    ? { ...input, displayCurrency: currencyChoice.currency, exchangeRate: currencyChoice.exchangeRate }
    : input
  return printHtmlDocument(buildSaleInvoiceHtml(printInput, paperSize), printInput.invoiceNo || 'Invoice', { paperSize })
}
