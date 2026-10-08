/** Escape user-facing values before inserting them into a print document. */
export function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/** Print paper sizes offered by the POS invoice chooser (spec: A4 or A5). */
export type PrintPaperSize = 'A4' | 'A5'

/** Hidden-iframe dimensions per paper size (portrait). */
export const PRINT_IFRAME_SIZES: Record<PrintPaperSize, { width: string, height: string }> = {
  A4: { width: '210mm', height: '297mm' },
  A5: { width: '148mm', height: '210mm' },
}

/** Khmer-first stack so invoice Khmer (and Latin) use a Khmer font, not Arial. */
const PRINT_FONT_STACK = '"Khmer OS Content", "Khmer OS", "Noto Sans Khmer", "Hanuman", sans-serif'

/** Load Khmer fonts inside the print iframe (main app fonts are not inherited). */
export const PRINT_FONT_LINKS = `<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Khmer:wght@400;600;700&display=swap" rel="stylesheet">`

/**
 * The shared border used by visible invoice boundaries (grid lines, totals
 * box, signature rules). Internal boundaries use a clear 1px solid black
 * line; the Amount column's outer edge is intentionally emphasized at 2px.
 * Every document type and paper size (A4 / A5) uses these same border widths.
 */
const PRINT_BORDER_WIDTH = 1
export const PRINT_BORDER = `${PRINT_BORDER_WIDTH}px solid #000`
/** The Amount column closes the invoice table with a more visible edge. */
const PRINT_AMOUNT_BORDER = '2px solid #000'

/**
 * Invoice column layout — the single source of truth for both the width CSS
 * and the `<colgroup>` shared by the line-items table and the totals table.
 *
 * The shares MUST total exactly 100% (`INVOICE_COLUMN_SHARE_TOTAL`). Both
 * tables use `table-layout: fixed` and resolve their columns from this same
 * `<colgroup>`. When the shares sum to less than 100%, the browser distributes
 * the leftover space itself, and it does not distribute it identically across
 * the line-items table and the structurally different totals table (which uses
 * colspans) — so the Amount column's right edge lands at different X
 * coordinates and the shared outer border appears inconsistent. With an exact
 * 100% total there is nothing left to distribute, so both tables resolve
 * identical boundaries: the 1px outer border runs at the same X from the
 * header through the items and the totals.
 */
export const INVOICE_COLUMNS = [
  { name: 'no', share: 5 },
  { name: 'product', share: 28 },
  { name: 'unit', share: 9 },
  { name: 'qty', share: 7 },
  { name: 'price', share: 15 },
  { name: 'discount', share: 18 },
  { name: 'amount', share: 18 },
] as const

/** Sum of the column shares; must be exactly 100 (asserted by tests). */
export const INVOICE_COLUMN_SHARE_TOTAL = INVOICE_COLUMNS.reduce(
  (total, column) => total + column.share,
  0,
)

/** `<colgroup>` built from the shared `INVOICE_COLUMNS` layout. */
export function invoiceColgroup(): string {
  return `
    <colgroup>
      ${INVOICE_COLUMNS.map(column => `<col class="col-${column.name}">`).join('\n      ')}
    </colgroup>`
}

/**
 * Print paper metrics. There is **one** invoice style; A5 is the same style
 * scaled down (px metrics × scalePx) on a smaller printable area. Each size
 * also carries its own mm layout budget so filler rows are computed for that
 * exact paper — never one hardcoded row count for both.
 */
export const PAPER_STYLES: Record<PrintPaperSize, {
  page: 'A4' | 'A5'
  marginMm: number
  /** px metric scale (A5 keeps the A4 look, slightly smaller to stay legible). */
  scalePx: number
  /** Printable height after @page margins (mm). */
  printableMm: number
  /** Product/filler line-row height on paper (mm). */
  rowMm: number
  /** Estimated table-header row height (mm). */
  tableHeadMm: number
  /** Estimated title + customer/cashier meta block (mm). */
  headerMm: number
  /** Estimated totals + signatures block, kept together as one unit (mm). */
  footerMm: number
  /** Page-1 slack so rounding never spills the footer onto page 2 (mm). */
  safetyMm: number
}> = {
  // A4: 297mm page − 2 × 8mm margins. rowMm includes a little extra padding.
  A4: {
    page: 'A4',
    marginMm: 8,
    scalePx: 1,
    printableMm: 281,
    rowMm: 8.5,
    tableHeadMm: 12,
    headerMm: 35,
    footerMm: 56,
    safetyMm: 6,
  },
  // A5: 210mm page − 2 × 6mm margins. Independent budget from A4.
  A5: {
    page: 'A5',
    marginMm: 6,
    scalePx: 0.8,
    printableMm: 198,
    rowMm: 6.8,
    tableHeadMm: 10,
    headerMm: 28,
    footerMm: 44,
    safetyMm: 5,
  },
}

/** Base (A4-scale) invoice px metrics used by printPageCss. */
const BASE_PX = {
  font: 13,
  title: 20,
  meta: 16,
  padX: 3,
  padY: 3,
  signsTop: 24,
  signsGap: 24,
} as const

/**
 * Page CSS for a paper size. Shop-form invoice: underlined title, larger
 * meta, gray header, empty filler rows sized to the page-1 budget left after
 * the fixed blocks, totals aligned to Price+Discount | Amount (no top border
 * on summary cells).
 */
export function printPageCss(size: PrintPaperSize): string {
  const style = PAPER_STYLES[size]
  const px = (value: number) => `${Math.round(value * style.scalePx * 100) / 100}px`
  const pad = `${px(BASE_PX.padY)} ${px(BASE_PX.padX)}`
  return `
@page { size: ${style.page}; margin: ${style.marginMm}mm; }
html, body, table, th, td, p, span, strong {
  margin: 0;
  font-family: ${PRINT_FONT_STACK};
}
html, body {
  padding: 0;
  background: #fff;
  color: #000;
  font-size: ${px(BASE_PX.font)};
  line-height: 1.3;
  font-weight: 400;
}
.doc { width: 100%; }
.invoice-page {
  position: relative;
  box-sizing: border-box;
  width: 100%;
  height: ${style.printableMm}mm;
  overflow: hidden;
  break-after: page;
  page-break-after: always;
}
.invoice-page.last {
  break-after: auto;
  page-break-after: auto;
}
.page-number {
  position: absolute;
  top: 0;
  right: 0;
  font-size: ${px(BASE_PX.font - 2)};
  font-weight: 400;
}
.title {
  text-align: center;
  font-size: ${px(BASE_PX.title)};
  font-weight: 700;
  margin: 0 0 10px;
  text-decoration: underline;
  text-underline-offset: 4px;
}
.meta {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 10px;
  font-size: ${px(BASE_PX.meta)};
  font-weight: 700;
}
.meta p {
  margin: 0 0 5px;
  font-weight: 700;
  font-size: ${px(BASE_PX.meta)};
  line-height: 1.45;
}
.meta strong { font-weight: 700; }
.meta .right { text-align: right; }
/* Separate borders with zero spacing: every cell paints its own edge inside
   its own box, so no border is centred on the table edge (nothing is clipped
   at the page margin) and no shared grid line is painted twice. Column
   geometry then comes only from the shared <colgroup>, so the line-items and
   totals tables line up exactly. */
table { width: 100%; border-collapse: separate; border-spacing: 0; }
table.lines { table-layout: fixed; border: 0; }
/* Multi-page sales: repeat the header row and never split an item row. */
table.lines thead { display: table-header-group; }
table.lines tbody tr {
  height: ${style.rowMm}mm;
  page-break-inside: avoid;
  break-inside: avoid;
}
th, td {
  border: 0;
  padding: ${pad};
  vertical-align: middle;
  font-weight: 400;
}
/* Grid: every cell draws its left + bottom edge, the header closes the top,
   and the last column closes the right — exactly one border per shared line. */
table.lines th, table.lines td {
  border-left: ${PRINT_BORDER};
  border-bottom: ${PRINT_BORDER};
}
table.lines thead th { border-top: ${PRINT_BORDER}; }
/* The Amount column is the outer edge of the invoice grid. Its right border
   is intentionally heavier than the internal grid boundaries. */
table.lines th:last-child,
table.lines td:last-child { border-right: ${PRINT_AMOUNT_BORDER}; }
th {
  background: #e8e8e8;
  font-weight: 700;
  text-align: center;
  line-height: 1.2;
}
th span {
  display: block;
  font-weight: 700;
  font-size: 0.92em;
}
th.num { text-align: center; }
td.num { text-align: right; }
/* Unit / Qty / Price / Discount read centred on the product lines. */
td.center, th.center { text-align: center; }
td.product { text-align: left; word-wrap: break-word; overflow-wrap: anywhere; }
/* Product lines: slightly taller + bigger for easier reading, still compact
   enough that the page-1 budget holds many rows. */
table.lines th, table.lines td {
  padding: ${px(BASE_PX.padY + 3)} ${px(BASE_PX.padX)};
  font-size: ${px(BASE_PX.font + 1)};
}
tr.empty.stretch td {
  padding: 0;
  vertical-align: top;
}
.num { white-space: nowrap; }
${INVOICE_COLUMNS.map(column => `.col-${column.name} { width: ${column.share}%; }`).join('\n')}
/* Totals + signatures are one atomic block: never split, never orphaned
   onto an extra page. Short sales keep them on page 1 (filler rows reserve
   the space); long sales push the whole block to the last page. */
.doc-footer {
  break-inside: avoid;
  page-break-inside: avoid;
}
.totals { margin: 0; width: 100%; }
table.summary {
  width: 100%;
  table-layout: fixed;
  border-collapse: separate;
  border-spacing: 0;
  border: 0;
  margin-top: 0;
}
table.summary td {
  padding: ${pad};
  vertical-align: middle;
  border: 0;
}
table.summary td.spacer {
  border: 0;
  padding: 0;
}
/* Totals sit on the same grid as the items: the label starts on the Price
   boundary and the amount cell on the Amount boundary, sharing the one border.
   Only border-left is drawn on each inner edge (never a matching border-right
   on the neighbour) so no line is doubled. */
table.summary td.label {
  text-align: left;
  font-weight: 400;
  border-left: ${PRINT_BORDER};
  border-bottom: ${PRINT_BORDER};
}
table.summary td.num {
  text-align: right;
  white-space: nowrap;
  border-left: ${PRINT_BORDER};
  border-right: ${PRINT_AMOUNT_BORDER};
  border-bottom: ${PRINT_BORDER};
}
table.summary tr.strong td.label,
table.summary tr.strong td.num { font-weight: 700; }
.signs {
  display: flex;
  justify-content: space-between;
  gap: ${px(BASE_PX.signsGap)};
  margin-top: ${px(BASE_PX.signsTop)};
  text-align: center;
}
.signs .sign { flex: 1; max-width: 42%; }
.signs .line {
  border-top: ${PRINT_BORDER};
  margin: 28px auto 6px;
  width: 85%;
}
.signs p { margin: 0; font-weight: 700; }
.note { margin-top: 8px; }
`
}

/**
 * Print a standalone HTML document from a hidden iframe.
 * Modal/page print CSS cannot see Teleport/dialog content, which produced a blank preview.
 * The OS print dialog still appears — browsers do not allow silent printing from a website.
 */
export function printHtmlDocument(
  html: string,
  title = 'Print',
  options?: {
    paperSize?: PrintPaperSize
    css?: string
    iframeSize?: { width: string, height: string }
    /**
     * Runs in the print document just before printing, once fonts are loaded.
     * Use it to measure/adjust the laid-out DOM (e.g. auto-fit long product
     * names). Errors are swallowed so preparation never blocks the print.
     */
    prepare?: (doc: Document) => void
  },
): Promise<void> {
  return new Promise((resolve) => {
    if (typeof document === 'undefined') {
      resolve()
      return
    }

    const paperSize = options?.paperSize ?? 'A4'
    const iframeSize = options?.iframeSize ?? PRINT_IFRAME_SIZES[paperSize]
    const iframe = document.createElement('iframe')
    iframe.setAttribute('title', title)
    iframe.setAttribute('aria-hidden', 'true')
    Object.assign(iframe.style, {
      position: 'fixed',
      left: '-10000px',
      top: '0',
      width: iframeSize.width,
      height: iframeSize.height,
      border: '0',
      pointerEvents: 'none',
    })
    document.body.appendChild(iframe)

    const frameWindow = iframe.contentWindow
    const frameDoc = iframe.contentDocument || frameWindow?.document
    if (!frameWindow || !frameDoc) {
      iframe.remove()
      resolve()
      return
    }

    let settled = false
    const finish = () => {
      if (settled) return
      settled = true
      window.setTimeout(() => iframe.remove(), 500)
      resolve()
    }

    frameWindow.addEventListener('afterprint', finish, { once: true })
    frameDoc.open()
    frameDoc.write(`<!DOCTYPE html>
<html lang="km">
<head>
  <meta charset="utf-8">
  <title>${escapeHtml(title)}</title>
  ${PRINT_FONT_LINKS}
  <style>${options?.css ?? printPageCss(paperSize)}</style>
</head>
<body>${html}</body>
</html>`)
    frameDoc.close()

    const trigger = () => {
      try {
        frameWindow.focus()
        // Most browsers block until the OS print dialog closes; iframe
        // `afterprint` is unreliable, so resolve as soon as print() returns.
        frameWindow.print()
      }
      catch {
        // ignore — still finish below
      }
      finish()
      // Non-blocking print() engines: short fallback if neither return nor afterprint ran.
      window.setTimeout(finish, 2000)
    }

    const startPrint = () => {
      const run = () => {
        try {
          options?.prepare?.(frameDoc)
        }
        catch {
          // best-effort layout prep — never block printing
        }
        trigger()
      }
      const fonts = frameDoc.fonts
      if (fonts?.ready) {
        void fonts.ready.then(() => window.setTimeout(run, 50)).catch(() => window.setTimeout(run, 80))
        return
      }
      window.setTimeout(run, 80)
    }

    if (frameDoc.readyState === 'complete') startPrint()
    else iframe.addEventListener('load', startPrint, { once: true })
  })
}
