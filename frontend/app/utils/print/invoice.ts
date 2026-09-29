import { formatMoney, formatNumber, formatDate, formatDateTime } from '~/utils/format/format-service'
import { cartTotal, lineGross, lineNet, type PosCartLine } from '~/utils/pos/cart'
import { escapeHtml, invoiceColgroup, PAPER_STYLES, printHtmlDocument, type PrintPaperSize } from '~/utils/print/html'
import type { SaleReceipt } from '~/repositories/contracts/entities'

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
    // Whole riel, symbol after the amount (1,019,000៛).
    return `${formatNumber(Math.round(converted), { maximumFractionDigits: 0 })}៛`
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

/** Physical-sheet layout decision for an invoice, derived from the paper budget. */
export type InvoiceLayout = {
  paperSize: PrintPaperSize
  /** Actual product rows in the invoice. */
  productRows: number
  /** Rows (products + blank grid) that fit on the final page above the footer. */
  firstPageCapacity: number
  /** Blank grid-row budget on a one-page invoice (0 for multi-page invoices). */
  fillerRows: number
  /** Product-row capacity on pages that do not carry totals/signatures. */
  continuationPageCapacity: number
  /** Actual product rows assigned to each physical sheet. */
  pageRows: number[]
  /** Blank grid-row budget on each sheet. */
  pageFillerRows: number[]
  /** Estimated printed pages (>= 1). */
  pages: number
  /** True when product rows overflow past page 1. */
  multipage: boolean
}

/**
 * Decide the invoice layout for a paper size.
 *
 * The final-page budget is the printable height minus the header (title + meta),
 * the table header and the totals/signatures block, plus a small safety
 * margin. When the products fit that budget, the leftover space is filled with
 * blank grid area so the table reaches the footer — but never so much that the
 * footer is pushed to another sheet. Larger invoices are explicitly divided
 * into physical sheets; continuation sheets use the space otherwise reserved
 * for totals and signatures.
 */
export function planInvoiceLayout(
  productRows: number,
  paperSize: PrintPaperSize = 'A4',
): InvoiceLayout {
  const style = PAPER_STYLES[paperSize]
  const rows = Math.max(0, Math.floor(productRows))
  const reservedMm = style.headerMm + style.tableHeadMm + style.footerMm + style.safetyMm
  const bodyMm = Math.max(0, style.printableMm - reservedMm)
  const firstPageCapacity = Math.max(1, Math.floor(bodyMm / style.rowMm))
  const continuationPageCapacity = Math.max(
    1,
    Math.floor(
      (style.printableMm - style.headerMm - style.tableHeadMm - style.safetyMm)
      / style.rowMm,
    ),
  )

  if (rows <= firstPageCapacity) {
    return {
      paperSize,
      productRows: rows,
      firstPageCapacity,
      fillerRows: firstPageCapacity - rows,
      continuationPageCapacity,
      pageRows: [rows],
      pageFillerRows: [firstPageCapacity - rows],
      pages: 1,
      multipage: false,
    }
  }

  // Every physical sheet repeats the title/meta/table header. Only the final
  // one reserves space for totals and signatures. Find the smallest sheet
  // count that can hold every item without truncation (three sheets is a
  // normal supported outcome, not a hard limit).
  const pages = 1 + Math.ceil((rows - firstPageCapacity) / continuationPageCapacity)
  const pageRows: number[] = []
  let remaining = rows
  for (let index = 0; index < pages; index += 1) {
    const remainingPages = pages - index
    const capacity = index === pages - 1 ? firstPageCapacity : continuationPageCapacity
    const capacityAfter = remainingPages <= 1
      ? 0
      : ((remainingPages - 2) * continuationPageCapacity) + firstPageCapacity
    const balanced = Math.ceil(remaining / remainingPages)
    const requiredNow = Math.max(1, remaining - capacityAfter)
    const take = Math.min(capacity, Math.max(balanced, requiredNow))
    pageRows.push(take)
    remaining -= take
  }
  const pageFillerRows = pageRows.map((count, index) => {
    const capacity = index === pages - 1 ? firstPageCapacity : continuationPageCapacity
    return Math.max(0, capacity - count)
  })
  return {
    paperSize,
    productRows: rows,
    firstPageCapacity,
    fillerRows: 0,
    continuationPageCapacity,
    pageRows,
    pageFillerRows,
    pages,
    multipage: true,
  }
}

/**
 * One continuous blank grid row so unused paper keeps the photographed form
 * appearance without adding many horizontal lines. Its height represents the
 * unused row budget calculated by `planInvoiceLayout`.
 */
function emptyInvoiceRows(fillerRows: number, rowMm: number): string {
  if (fillerRows <= 0) return ''
  return `
    <tr class="empty stretch" data-filler-rows="${fillerRows}" style="height:${fillerRows * rowMm}mm">
      <td class="num">&nbsp;</td>
      <td></td>
      <td></td>
      <td></td>
      <td></td>
      <td></td>
      <td></td>
    </tr>`
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
 * Build invoice HTML. Product rows are assigned to explicit physical sheets;
 * every sheet retains the vertical grid and only the last carries totals and
 * signatures. This prevents a short invoice from creating a blank page 2 and
 * makes two/three-page invoices deterministic.
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
  const layout = planInvoiceLayout(lines.length, paperSize)
  const lineRows = (pageLines: PosCartLine[], offset: number) => pageLines.map((line, index) => `
    <tr>
      <td class="num center">${offset + index + 1}</td>
      <td class="product">${escapeHtml(line.name)}</td>
      <td class="center">${escapeHtml(line.uom || '—')}</td>
      <td class="num center">${escapeHtml(line.quantity)}</td>
      <td class="num center">${money(line.unitPrice)}</td>
      <td class="num center">${money(lineGross(line) * (Number(line.discountPercent || 0) / 100))}</td>
      <td class="num">${money(lineNet(line))}</td>
    </tr>`).join('')

  const colgroup = invoiceColgroup()

  let offset = 0
  const pages = layout.pageRows.map((rowCount, pageIndex) => {
    const pageLines = lines.slice(offset, offset + rowCount)
    const pageOffset = offset
    offset += rowCount
    const isLast = pageIndex === layout.pages - 1
    const pageLabel = layout.pages > 1
      ? `<p class="page-number">Page ${pageIndex + 1} / ${layout.pages}</p>`
      : ''
    const footer = !isLast ? '' : `
  <div class="doc-footer">
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
  </div>`
    return `
<section class="invoice-page${isLast ? ' last' : ''}">
  ${pageLabel}
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
        <th class="center">ល.រ<span>N°</span></th>
        <th>មុខទំនិញ<span>Product</span></th>
        <th class="center">ឯកតា<span>Unit</span></th>
        <th class="num center">ចំនួន<span>Qty</span></th>
        <th class="num center">តម្លៃ<span>Price</span></th>
        <th class="num center">បញ្ចុះតម្លៃ<span>Discount</span></th>
        <th class="num">តម្លៃសរុប<span>Amount</span></th>
      </tr>
    </thead>
    <tbody>${lineRows(pageLines, pageOffset)}${emptyInvoiceRows(layout.pageFillerRows[pageIndex] || 0, PAPER_STYLES[paperSize].rowMm)}</tbody>
  </table>
  ${footer}
</section>`
  }).join('')

  return `<article class="doc">${pages}</article>`
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

/**
 * Reprint input from a stored sale record (movement/history dialogs).
 * Uses the record's currency/exchange-rate snapshot — never the shop's live
 * rate — so historical reprints show the amounts as sold.
 */
export function saleInvoicePrintInputFromRecord(
  record: Record<string, unknown>,
  shopName: string,
): SaleInvoicePrintInput {
  const items = Array.isArray(record.items) ? record.items as Array<Record<string, unknown>> : []
  const currency = String(record.currency || 'USD')
  return {
    shopName,
    invoiceNo: String(record.invoiceNo ?? record.saleNo ?? ''),
    dateLabel: formatDateTime(record.date),
    customerName: String(record.customer ?? ''),
    cashier: String(record.cashier ?? ''),
    currency,
    // Stored snapshot: print in the sale's own currency/rate.
    displayCurrency: String(record.displayCurrency || currency),
    exchangeRate: Number(record.exchangeRate || 0) || undefined,
    lines: items.map(item => ({
      name: String(item.name ?? ''),
      uom: String(item.uom ?? ''),
      quantity: Number(item.quantity || 0),
      unitPrice: Number(item.price ?? item.unitPrice ?? 0),
      discountPercent: Number(item.discountPercent ?? item.discount ?? 0),
    })),
    deliveryPrice: Number(record.deliveryPrice ?? 0),
    previousDebtAmount: Number(record.previousDebtAmount ?? 0),
    depositAmount: Number(record.depositAmount ?? record.deposit ?? 0),
    outstandingAmount: Number(record.remaining ?? record.outstandingAmount ?? 0),
  }
}

/**
 * Reprint input from a sale receipt payload (GET receipt of a sale /
 * movement invoice). Same snapshot rule as `saleInvoicePrintInputFromRecord`.
 */
export function saleReceiptPrintInput(
  receipt: SaleReceipt,
  shopName: string,
): SaleInvoicePrintInput {
  return {
    shopName,
    invoiceNo: receipt.invoiceNo || receipt.saleNo,
    dateLabel: formatDate(receipt.date),
    customerName: receipt.customer,
    cashier: receipt.cashier,
    currency: receipt.currency || 'USD',
    displayCurrency: receipt.currency || 'USD',
    exchangeRate: Number(receipt.exchangeRate || 0) || undefined,
    lines: receipt.items.map(item => ({
      name: item.name,
      uom: item.uom,
      quantity: Number(item.quantity || 0),
      unitPrice: Number(item.unitPrice || 0),
      discountPercent: Number(item.discount || 0),
    })),
    deliveryPrice: Number(receipt.deliveryPrice || 0),
    previousDebtAmount: 0,
    depositAmount: Number(receipt.deposit || 0),
    outstandingAmount: Number(receipt.remaining || 0),
  }
}
