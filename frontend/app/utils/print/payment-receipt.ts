import { escapeHtml, PAPER_STYLES, printHtmlDocument, type PrintPaperSize } from '~/utils/print/html'
import { planInvoiceLayout } from '~/utils/print/invoice'
import { formatNumber } from '~/utils/format/format-service'

/**
 * Debt payment receipt (customer & supplier): the paper a party gets after a
 * lump payment settles open invoices oldest-first. Lists every document the
 * amount covered so the party can trace exactly which invoices were paid.
 *
 * The paper reuses the sale-invoice page style (`printPageCss`) and the same
 * one-page form rules (title, meta, bordered grid, filler rows, totals,
 * signatures) so a receipt looks exactly like a product-sale invoice — only
 * its lines list the settled invoices instead of products. Labels are the
 * shop's usual bilingual Khmer/English form, like the invoice.
 */
export type PaymentReceiptDocument = {
  docNo: string
  date: string
  amount: number
}

export type PaymentReceiptInput = {
  shopName: string
  /** Which side paid (the paper labels it Customer/Supplier). */
  partyKind: 'customer' | 'supplier'
  partyName: string
  /** Payment document number(s) recorded by the backend. */
  receiptNo: string
  dateLabel: string
  cashier: string
  currency: string
  paymentMethod: string
  /** Optional transfer/receipt reference (printed only when provided). */
  reference: string
  /** Balance before this payment (the party's open documents on the settled side). */
  balanceBefore: number
  /** Amount received now. */
  amountPaid: number
  /** Balance after this payment (balanceBefore − amountPaid, never below 0). */
  balanceAfter: number
  /** Documents settled by this payment, oldest-first. */
  documents: PaymentReceiptDocument[]
  /** What the customer actually handed over (set when collected in another
   *  currency than the debt's own, e.g. riel cash for a USD debt). */
  collectedCurrency?: string
  collectedAmount?: number
  /** KHR per 1 USD used for the collection (shown with the received amount). */
  exchangeRate?: number
}

/** Format an amount on the receipt: same paper style as the invoice (whole
 *  riel for KHR; stable 2-decimals for USD) in the document's own currency. */
function money(value: unknown, currency: string): string {
  const amount = Number(value || 0)
  const code = String(currency || 'USD').toUpperCase()
  if (code === 'KHR') {
    return `${formatNumber(Math.round(amount), { maximumFractionDigits: 0 })}៛`
  }
  return formatNumber(amount, {
    style: 'currency',
    currency: code,
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  })
}

/** One settled document line, copied from the invoice's product-row style. */
function documentRows(documents: PaymentReceiptDocument[], currency: string): string {
  if (!documents.length) {
    return '<tr><td class="num center">—</td><td class="product"></td><td class="center"></td><td class="num"></td></tr>'
  }
  return documents.map((document, index) => `
    <tr>
      <td class="num center">${index + 1}</td>
      <td class="product">${escapeHtml(document.docNo || '—')}</td>
      <td class="center">${escapeHtml(document.date || '—')}</td>
      <td class="num">${escapeHtml(money(document.amount, currency))}</td>
    </tr>`).join('')
}

/** Blank grid rows so a short receipt fills the page like the invoice form. */
function fillerRows(count: number, rowMm: number): string {
  if (count <= 0) return ''
  return `
    <tr class="empty stretch" data-filler-rows="${count}" style="height:${count * rowMm}mm">
      <td colspan="4">&nbsp;</td>
    </tr>`
}

function summaryRow(label: string, amountHtml: string, strong = false): string {
  const cls = strong ? ' class="strong"' : ''
  return `
      <tr${cls}>
        <td class="spacer" colspan="2"></td>
        <td class="label">${label}</td>
        <td class="num">${amountHtml}</td>
      </tr>`
}

/**
 * Build the receipt HTML with the sale-invoice page style: bilingual
 * Khmer/English labels, the shared column grid, filler rows (when everything
 * fits one sheet) and the totals + signature footer.
 */
export function buildPaymentReceiptHtml(
  input: PaymentReceiptInput,
  paperSize: PrintPaperSize = 'A5',
): string {
  const partyLabel = input.partyKind === 'customer' ? 'អតិថិជន / Customer' : 'អ្នកផ្គត់ផ្គង់ / Supplier'
  const layout = planInvoiceLayout(Math.max(1, input.documents.length), paperSize)
  // Collected in another currency (e.g. riel cash for a USD debt): print what
  // the customer actually handed over next to the settlement currency.
  const collectedCurrency = String(input.collectedCurrency || '')
  const collectedRate = Number(input.exchangeRate || 0)
  const receivedLine = collectedCurrency && collectedCurrency !== input.currency
    ? `<p>បានទទួល Received : <strong>${escapeHtml(money(input.collectedAmount, collectedCurrency))}</strong>${collectedRate > 0 ? ` · 1 USD = ${escapeHtml(formatNumber(Math.round(collectedRate)))} KHR` : ''}</p>`
    : ''
  const colgroup = `
    <colgroup>
      <col style="width:8%">
      <col style="width:44%">
      <col style="width:20%">
      <col style="width:28%">
    </colgroup>`

  const page = `
  <p class="title">បង្កាន់ដៃទូទាត់ / PAYMENT RECEIPT</p>
  <div class="meta">
    <div>
      <p>លេខបង្កាន់ដៃ Receipt No : <strong>${escapeHtml(input.receiptNo || '—')}</strong></p>
      <p>កាលបរិច្ឆេទ Date : <strong>${escapeHtml(input.dateLabel)}</strong></p>${input.reference ? `\n      <p>ឯកសារយោង Reference : <strong>${escapeHtml(input.reference)}</strong></p>` : ''}
    </div>
    <div class="right">
      <p>${partyLabel} : <strong>${escapeHtml(input.partyName || '—')}</strong></p>
      <p>វិធីទូទាត់ Method : <strong>${escapeHtml(input.paymentMethod || '—')}</strong></p>${receivedLine ? `\n      ${receivedLine}` : ''}
      <p>បេឡា Cashier : <strong>${escapeHtml(input.cashier || '—')}</strong></p>
    </div>
  </div>
  <table class="lines">
    ${colgroup}
    <thead>
      <tr>
        <th class="num center">ល.រ<span>N°</span></th>
        <th>វិក្កយបត្រ / ឯកសារ<span>Invoice / Document</span></th>
        <th class="num center">កាលបរិច្ឆេទ<span>Date</span></th>
        <th class="num">ទឹកប្រាក់<span>Amount (${escapeHtml(input.currency)})</span></th>
      </tr>
    </thead>
    <tbody>${documentRows(input.documents, input.currency)}${layout.multipage ? '' : fillerRows(layout.fillerRows, PAPER_STYLES[paperSize].rowMm)}</tbody>
  </table>
  <div class="doc-footer">
    <div class="totals">
      <table class="summary">
        ${colgroup}
        ${summaryRow('សមតុល្យមុន / Balance before', money(input.balanceBefore, input.currency))}
        ${summaryRow('បានទូទាត់ / Paid now', money(input.amountPaid, input.currency), true)}
        ${summaryRow('សមតុល្យក្រោយ / Balance after', money(input.balanceAfter, input.currency))}
      </table>
    </div>
    <div class="signs">
      <div class="sign">
        <div class="line"></div>
        <p>អ្នកបង់ប្រាក់ / Payer</p>
      </div>
      <div class="sign">
        <div class="line"></div>
        <p>អ្នកទទួល / Receiver</p>
      </div>
    </div>
  </div>`

  // Short receipts use the invoice's fixed one-page sheet (filler rows keep the
  // form reaching the footer); long lists flow across natural pages instead of
  // clipping inside a fixed-height sheet.
  return layout.multipage
    ? `<article class="doc">${page}</article>`
    : `<article class="doc"><section class="invoice-page last">${page}</section></article>`
}

/** Print the receipt in the chosen paper size (A4/A5 chooser) — the exact
 *  sale-invoice page style (`printPageCss`), never a separate one-off design. */
export function printPaymentReceipt(
  input: PaymentReceiptInput,
  paperSize: PrintPaperSize = 'A5',
): Promise<void> {
  return printHtmlDocument(
    buildPaymentReceiptHtml(input, paperSize),
    input.receiptNo || 'Payment receipt',
    { paperSize },
  )
}
