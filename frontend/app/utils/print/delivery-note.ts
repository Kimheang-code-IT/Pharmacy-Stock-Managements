import { escapeHtml, printHtmlDocument } from '~/utils/print/html'

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

  const note = input.note
    ? `<p class="note">កំណត់សម្គាល់ / Note: ${escapeHtml(input.note)}</p>`
    : ''

  return `
<article class="doc">
  <p class="title">ប័ណ្ណដឹកជញ្ជូន / DELIVERY NOTE</p>
  <p class="shop">${escapeHtml(input.shopName)}</p>
  <div class="meta">
    <div>
      <p>លេខប័ណ្ណ / No: <strong>${escapeHtml(input.deliveryNo)}</strong></p>
      <p>លេខវិក្កយបត្រ / Invoice No: <strong>${escapeHtml(input.invoiceNo)}</strong></p>
      <p>អតិថិជន / Customer: <strong>${escapeHtml(input.customer)}</strong></p>
      <p>ទូរស័ព្ទ / Phone: <strong>${escapeHtml(input.deliveryPhone)}</strong></p>
    </div>
    <div class="right">
      <p>កាលបរិច្ឆេទ / Date: <strong>${escapeHtml(input.dateLabel)}</strong></p>
      <p>ស្ថានភាព / Status: <strong>${escapeHtml(input.status)}</strong></p>
      <p>ទីតាំងបញ្ជូន / Location: <strong>${escapeHtml(input.deliveryLocation)}</strong></p>
    </div>
  </div>
  <table>
    <thead>
      <tr>
        <th>ល.រ<span>N°</span></th>
        <th>មុខទំនិញ<span>Product</span></th>
        <th>ឯកតា<span>Unit</span></th>
        <th class="num">បញ្ជាក់<span>Ordered</span></th>
        <th class="num">បញ្ជូន<span>To Deliver</span></th>
      </tr>
    </thead>
    <tbody>${rows}</tbody>
  </table>
  ${note}
  <div class="signs">
    <p>អ្នកទទួល / Receiver</p>
    <p>អ្នកដឹកជញ្ជូន / Delivery staff</p>
  </div>
</article>`
}

export function printDeliveryNoteDocument(
  note: Record<string, unknown>,
  shopName: string,
): Promise<void> {
  const input = deliveryNotePrintInputFromRecord(note, shopName)
  return printHtmlDocument(buildDeliveryNoteHtml(input), input.deliveryNo || 'Delivery Note')
}
