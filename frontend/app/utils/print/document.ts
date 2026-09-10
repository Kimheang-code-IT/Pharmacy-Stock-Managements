import { escapeHtml } from '~/utils/print/html'

/**
 * Reusable bilingual print-document chrome shared by every printable
 * document (POS invoice, delivery note, future purchase/return prints).
 * Each document supplies only its own title, meta pairs, table headers /
 * rows and signature labels; headers, filler rows, notes and signature
 * blocks render identically everywhere (Khmer-first stacked headers,
 * ~70% page-1 filler budget, 0.5px borders from printPageCss).
 */

export type PrintMetaPair = { label: string, value: string }

/** Bilingual stacked column header: Khmer label over English sub-label. */
export type PrintDocumentHeader = {
  label: string
  sub?: string
  /** `num` right-aligns and matches the `th.num` / `td.num` CSS. */
  align?: 'num'
}

function headerClass(header: PrintDocumentHeader): string {
  return header.align === 'num' ? ' class="num"' : ''
}

/**
 * Centered underlined document title (never the shop name) — e.g.
 * `ប័ណ្ណដឹកជញ្ជូន / DELIVERY NOTE`.
 */
export function printDocTitle(title: string): string {
  return `<p class="title">${escapeHtml(title)}</p>`
}

/** Bold two-column meta block (left/right stacks of label: value lines). */
export function printDocMeta(left: PrintMetaPair[], right: PrintMetaPair[]): string {
  const line = (pair: PrintMetaPair) => `<p>${escapeHtml(pair.label)} : <strong>${escapeHtml(pair.value)}</strong></p>`
  return `
  <div class="meta">
    <div>
      ${left.map(line).join('')}
    </div>
    <div class="right">
      ${right.map(pair => `<p>${escapeHtml(pair.label)} : <strong>${escapeHtml(pair.value)}</strong></p>`).join('')}
    </div>
  </div>`
}

/** `<colgroup>` for a lines table (column widths in percent). */
export function printDocColgroup(widths: string[]): string {
  return `
    <colgroup>
      ${widths.map(width => `<col style="width: ${escapeHtml(width)}">`).join('')}
    </colgroup>`
}

/** Header row of stacked bilingual column headers. */
export function printDocHeadRow(headers: PrintDocumentHeader[]): string {
  const cell = (header: PrintDocumentHeader) => {
    const sub = header.sub ? `<span>${escapeHtml(header.sub)}</span>` : ''
    return `<th${headerClass(header)}>${escapeHtml(header.label)}${sub}</th>`
  }
  return `
      <tr>
        ${headers.map(cell).join('')}
      </tr>`
}

/** One empty filler row across `columns` grid columns (page-1 height fill). */
export function printDocFillerRow(columns: number): string {
  return `
    <tr class="empty">
      ${Array.from({ length: columns }, () => '<td></td>').join('')}
    </tr>`
}

/** Optional note paragraph under the lines grid (e.g. កំណត់សម្គាល់ / Note). */
export function printDocNote(label: string, text: string): string {
  const value = String(text || '').trim()
  if (!value) return ''
  return `<p class="note">${escapeHtml(label)}: ${escapeHtml(value)}</p>`
}

/** Signature blocks: a rule line over each label (Receiver, Buyer, …). */
export function printDocSignatures(labels: string[]): string {
  return `
  <div class="signs">
    ${labels.map(label => `
    <div class="sign">
      <div class="line"></div>
      <p>${escapeHtml(label)}</p>
    </div>`).join('')}
  </div>`
}