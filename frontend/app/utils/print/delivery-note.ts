import { escapeHtml, printHtmlDocument } from '~/utils/print/html'
import {
  printDocColgroup,
  printDocHeadRow,
  printDocMeta,
  printDocNote,
  printDocSignatures,
  printDocTitle,
  type PrintMetaPair,
} from '~/utils/print/document'

export type DeliveryNotePrintLine = {
  product: string
  uomSymbol: string
  qtyOrdered: number
  qtyToDeliver: number
}

export type DeliveryNotePrintInput = {
  shopName: string
  deliveryNo: string
  dateLabel: string
  invoiceNo: string
  status: string
  customer: string
  deliveryPhone: string
  deliveryLocation: string
  note: string
  lines: DeliveryNotePrintLine[]
}

function text(value: unknown, fallback = '—'): string {
  const next = String(value ?? '').trim()
  return next || fallback
}

/** Linked invoice nos of a note — many sales on one note (spec §2.1.9). */
function invoiceNosOf(note: Record<string, unknown>): string[] {
  const list = note.invoiceNos ?? note.invoiceNo
  if (Array.isArray(list)) return list.map(no => String(no).trim()).filter(Boolean)
  const joined = String(note.invoiceNo ?? note.saleNo ?? '').trim()
  return joined ? joined.split(',').map(no => no.trim()).filter(Boolean) : []
}

export function deliveryNotePrintInputFromRecord(
  note: Record<string, unknown>,
  shopName: string,
): DeliveryNotePrintInput {
  const items = Array.isArray(note.items) ? note.items as Record<string, unknown>[] : []
  return {
    shopName,
    deliveryNo: text(note.deliveryNo, ''),
    dateLabel: String(note.createdAt || '').slice(0, 10),
    invoiceNo: text(invoiceNosOf(note).join(', ')),
    status: text(note.status),
    customer: text(note.customer),
    deliveryPhone: text(note.deliveryPhone),
    deliveryLocation: text(note.deliveryLocation ?? note.deliveryAddress),
    note: String(note.note || '').trim(),
    lines: items.map(line => ({
      product: text(line.product),
      uomSymbol: text(line.uomSymbol),
      qtyOrdered: Number(line.qtyOrdered || 0),
      qtyToDeliver: Number(line.qtyToDeliver || 0),
    })),
  }
}

export function buildDeliveryNoteHtml(input: DeliveryNotePrintInput): string {
  const rows = input.lines.map((line, index) => `
    <tr>
      <td class="num">${index + 1}</td>
      <td>${escapeHtml(line.product)}</td>
      <td>${escapeHtml(line.uomSymbol)}</td>
      <td class="num">${escapeHtml(line.qtyOrdered)}</td>
      <td class="num">${escapeHtml(line.qtyToDeliver)}</td>
    </tr>`).join('')

  const left: PrintMetaPair[] = [
    { label: 'លេខប័ណ្ណ / No', value: input.deliveryNo },
    { label: 'លេខវិក្កយបត្រ / Invoice No', value: input.invoiceNo },
    { label: 'អតិថិជន / Customer', value: input.customer },
    { label: 'ទូរស័ព្ទ / Phone', value: input.deliveryPhone },
  ]
  const right: PrintMetaPair[] = [
    { label: 'កាលបរិច្ឆេទ / Date', value: input.dateLabel },
    { label: 'ស្ថានភាព / Status', value: input.status },
    { label: 'ទីតាំងបញ្ជូន / Location', value: input.deliveryLocation },
  ]

  return `
<article class="doc">
  ${printDocTitle('ប័ណ្ណដឹកជញ្ជូន / DELIVERY NOTE')}
  <p class="shop">${escapeHtml(input.shopName)}</p>
  ${printDocMeta(left, right)}
  <table>
    ${printDocColgroup(['5%', '33%', '14%', '24%', '24%'])}
    <thead>${printDocHeadRow([
      { label: 'ល.រ', sub: 'N°' },
      { label: 'មុខទំនិញ', sub: 'Product' },
      { label: 'ឯកតា', sub: 'Unit' },
      { label: 'បញ្ជាក់', sub: 'Ordered', align: 'num' },
      { label: 'បញ្ជូន', sub: 'To Deliver', align: 'num' },
    ])}</thead>
    <tbody>${rows}</tbody>
  </table>
  ${printDocNote('កំណត់សម្គាល់ / Note', input.note)}
  ${printDocSignatures(['អ្នកទទួល / Receiver', 'អ្នកដឹកជញ្ជូន / Delivery staff'])}
</article>`
}

export function printDeliveryNoteDocument(
  note: Record<string, unknown>,
  shopName: string,
): Promise<void> {
  const input = deliveryNotePrintInputFromRecord(note, shopName)
  return printHtmlDocument(buildDeliveryNoteHtml(input), input.deliveryNo || 'Delivery Note')
}