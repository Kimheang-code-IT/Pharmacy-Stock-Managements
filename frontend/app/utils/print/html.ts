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
 * Print paper metrics. There is **one** invoice style; A5 is the same style
 * scaled down (px metrics × scalePx) on a smaller printable area.
 */
export const PAPER_STYLES: Record<PrintPaperSize, {
  page: 'A4' | 'A5'
  marginMm: number
  /** px metric scale (A5 keeps the A4 look, slightly smaller to stay legible). */
  scalePx: number
  /** Printable height after @page margins (mm). */
  printableMm: number
  /** Typical line-row height on paper (mm) — used for layout estimates. */
  rowMm: number
}> = {
  A4: { page: 'A4', marginMm: 8, scalePx: 1, printableMm: 281, rowMm: 6.5 },
  A5: { page: 'A5', marginMm: 6, scalePx: 0.8, printableMm: 198, rowMm: 5.2 },
}

/** Base (A4-scale) invoice px metrics used by printPageCss. */
const BASE_PX = {
  font: 13,
  title: 20,
  meta: 16,
  padX: 3,
  padY: 2,
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
table { width: 100%; border-collapse: collapse; }
table.lines {
  table-layout: fixed;
  border: 0.5px solid #000;
}
th, td {
  border: 0.5px solid #000;
  padding: ${pad};
  vertical-align: middle;
  font-weight: 400;
}
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
td.product { text-align: left; word-wrap: break-word; overflow-wrap: anywhere; }
tr.empty td { height: ${style.rowMm}mm; }
.num { white-space: nowrap; }
.col-no { width: 5%; }
.col-product { width: 28%; }
.col-unit { width: 9%; }
.col-qty { width: 7%; }
.col-price { width: 15%; }
.col-discount { width: 18%; }
.col-amount { width: 18%; }
.totals { margin: 0; width: 100%; }
table.summary {
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
  border: none;
  margin-top: 0;
}
table.summary td {
  padding: ${pad};
  vertical-align: middle;
  border: none;
}
table.summary td.spacer {
  border: none;
  padding: 0;
}
table.summary td.label {
  text-align: left;
  font-weight: 400;
  border-top: none;
  border-left: 0.5px solid #000;
  border-right: 0.5px solid #000;
  border-bottom: 0.5px solid #000;
}
table.summary td.num {
  text-align: right;
  white-space: nowrap;
  border-top: none;
  border-left: 0.5px solid #000;
  border-right: 0.5px solid #000;
  border-bottom: 0.5px solid #000;
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
  border-top: 0.5px solid #000;
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
  options?: { paperSize?: PrintPaperSize },
): Promise<void> {
  return new Promise((resolve) => {
    if (typeof document === 'undefined') {
      resolve()
      return
    }

    const paperSize = options?.paperSize ?? 'A4'
    const iframeSize = PRINT_IFRAME_SIZES[paperSize]
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
  <style>${printPageCss(paperSize)}</style>
</head>
<body>${html}</body>
</html>`)
    frameDoc.close()

    const trigger = () => {
      try {
        frameWindow.focus()
        frameWindow.print()
      }
      catch {
        finish()
      }
      window.setTimeout(finish, 120000)
    }

    const startPrint = () => {
      const fonts = frameDoc.fonts
      if (fonts?.ready) {
        void fonts.ready.then(() => window.setTimeout(trigger, 50)).catch(() => window.setTimeout(trigger, 80))
        return
      }
      window.setTimeout(trigger, 80)
    }

    if (frameDoc.readyState === 'complete') startPrint()
    else iframe.addEventListener('load', startPrint, { once: true })
  })
}
