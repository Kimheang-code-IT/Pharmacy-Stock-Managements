import { formatNumber, formatDate, formatDateTime } from '~/utils/format/format-service'
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
  // Printed invoices keep a stable 2-decimal money look (up to 4 when needed),
  // independent of the adaptive on-screen number format.
  return formatNumber(converted, {
    style: 'currency',
    currency: code,
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  })
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
  /** Rows that fit on a ONE-page invoice above the footer (full header). */
  firstPageCapacity: number
  /** Blank grid-row budget on a one-page invoice (0 for multi-page invoices). */
  fillerRows: number
  /** Product-row capacity on middle sheets (compact header, no footer). */
  continuationPageCapacity: number
  /** Product-row capacity on the final sheet (compact header + totals/signatures). */
  lastPageCapacity: number
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
 * One-page invoices keep the photographed-form budget: full header
 * (title + meta) + table header + totals/signatures, with the leftover space
 * filled by blank grid area so the table reaches the footer.
 *
 * Multi-page invoices never waste paper: page 1 keeps the full header but no
 * footer, middle pages carry only the compact continued header, and only the
 * final page reserves the totals/signatures block. Pages fill to capacity
 * greedily (no blank gaps mid-invoice); the remainder lands on the last page.
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
      // Continuation sheets repeat only the compact "continued" header line
      // plus the table header — the full title/meta block lives on page 1.
      (style.printableMm - style.continuedHeaderMm - style.tableHeadMm - style.safetyMm)
      / style.rowMm,
    ),
  )
  const lastPageCapacity = Math.max(
    1,
    Math.floor(
      // The final sheet repeats the compact header and carries totals/signatures.
      (style.printableMm - style.continuedHeaderMm - style.tableHeadMm - style.footerMm - style.safetyMm)
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
      lastPageCapacity: firstPageCapacity,
      pageRows: [rows],
      pageFillerRows: [firstPageCapacity - rows],
      pages: 1,
      multipage: false,
    }
  }

  // Multi-page budgets: page 1 keeps the full header but no footer (the
  // totals block lives on the last page); middle pages are the largest.
  const multiFirstCapacity = Math.max(
    1,
    Math.floor(
      (style.printableMm - style.headerMm - style.tableHeadMm - style.safetyMm)
      / style.rowMm,
    ),
  )

  // Fill every page greedily to capacity; the remainder lands on the final
  // page (never over it: each step keeps at least one row for the last page).
  const pageRows: number[] = []
  let remaining = rows
  while (remaining > lastPageCapacity) {
    const capacity = pageRows.length === 0 ? multiFirstCapacity : continuationPageCapacity
    const take = Math.min(capacity, remaining - 1)
    pageRows.push(take)
    remaining -= take
  }
  pageRows.push(remaining)
  const pages = pageRows.length
  const pageFillerRows = pageRows.map((count, index) => {
    const capacity = index === 0
      ? multiFirstCapacity
      : index === pages - 1
        ? lastPageCapacity
        : continuationPageCapacity
    return Math.max(0, capacity - count)
  })
  return {
    paperSize,
    productRows: rows,
    firstPageCapacity,
    fillerRows: 0,
    continuationPageCapacity,
    lastPageCapacity,
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
 * Build invoice HTML. The full header (title + invoice no/date/customer/
 * cashier meta) prints on page 1 only; continuation sheets repeat a compact
 * header line (invoice no) plus the table header. Product rows are assigned
 * to explicit physical sheets; every sheet retains the vertical grid and only
 * the last carries totals and signatures.
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
    // Full header (title + meta) on page 1; compact continued line after it.
    const pageHeader = pageIndex === 0
      ? `<p class="title">វិក្កយបត្រ / INVOICE</p>
  <div class="meta">
    <div>
      <p>លេខ Invoice : <strong>${escapeHtml(input.invoiceNo)}</strong></p>
      <p>កាលបរិច្ឆេទ Date : <strong>${escapeHtml(input.dateLabel)}</strong>${converting ? `\n      <p>អត្រាប្តូរប្រាក់ Exchange rate : <strong>1 USD = ${escapeHtml(formatNumber(Math.round(exchangeRate)))} KHR</strong></p>` : ''}
    </div>
    <div class="right">
      <p>អតិថិជន Customer : <strong>${escapeHtml(input.customerName)}</strong></p>
      <p>បេឡា Cashier : <strong>${escapeHtml(input.cashier)}</strong></p>
    </div>
  </div>`
      : `<p class="continued">វិក្កយបត្រ / INVOICE ${escapeHtml(input.invoiceNo)} — បន្ត / continued</p>`
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
  ${pageHeader}
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
 * movement invoice). Same snapshot rule as `saleInvoicePrintInputFromRecord`:
 * a KHR sale reprints in KHR with its stored rate, never re-based to USD.
 */
export function saleReceiptPrintInput(
  receipt: SaleReceipt,
  shopName: string,
): SaleInvoicePrintInput {
  const customerTotalDebt = Number(receipt.customerTotalDebt || 0)
  const invoiceRemaining = Number(receipt.remaining || 0)
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
    // The reprint always shows the customer's remaining debt when there is
    // any: ខ្វះសរុប = the customer's TOTAL open debt over all invoices (this
    // sale + other unpaid ones), ខ្វះមុន = the part owed on OTHER invoices.
    // Falls back to this sale's own remaining when the total is unavailable.
    previousDebtAmount: customerTotalDebt > 0
      ? Math.max(0, customerTotalDebt - invoiceRemaining)
      : 0,
    // Paid on THIS invoice = the sale's recorded paid amount (the receipt has
    // no separate deposit; using it printed "paid 0" on every reprint).
    depositAmount: Number(receipt.paidAmount || 0),
    outstandingAmount: customerTotalDebt > 0 ? customerTotalDebt : invoiceRemaining,
  }
}
