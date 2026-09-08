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
 * scaled down (px metrics × scalePx) on a smaller printable area. The grid
 * row height per paper drives how many filler rows fit below the invoice
 * chrome, so both sizes fill their page with the same bordered layout.
 */
export const PAPER_STYLES: Record<PrintPaperSize, {
  page: 'A4' | 'A5'
  marginMm: number
  /** px metric scale (A5 keeps the A4 look, slightly smaller to stay legible). */
  scalePx: number
  /** Printable height after @page margins (mm). */
  printableMm: number
  /** One invoice grid row on paper (mm) — text line + cell padding. */
  rowMm: number
}> = {
  A4: { page: 'A4', marginMm: 8, scalePx: 1, printableMm: 281, rowMm: 6 },
  A5: { page: 'A5', marginMm: 6, scalePx: 0.8, printableMm: 198, rowMm: 4.8 },
}

/** Base (A4-scale) invoice px metrics used by printPageCss. */
const BASE_PX = {
  font: 10,
  title: 13,
  padX: 3,
  padY: 2,
  summaryWidth: 210,
  signsTop: 24,
  signsGap: 24,
} as const

/**
 * Page CSS for a paper size. One shared template for A4 and A5 — the lines
 * grid and summary table are bordered on both; only the scale differs.
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
  line-height: 1.25;
  font-weight: 700;
}
.doc { width: 100%; }
.title { text-align: center; font-size: ${px(BASE_PX.title)}; font-weight: 700; margin: 0 0 5px; }
.meta { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 5px; }
.meta p { margin: 0 0 1px; font-weight: 700; }
.meta .right { text-align: right; }
table { width: 100%; border-collapse: collapse; }
table.lines { table-layout: fixed; }
th, td { border: 1px solid #000; padding: ${pad}; vertical-align: top; }
th { background: #e8e8e8; font-weight: 700; text-align: left; }
th span { font-weight: 700; }
tr.empty td { height: ${style.rowMm}mm; }
.num { text-align: right; white-space: nowrap; }
.col-no { width: 6%; }
.col-product { width: 38%; }
.col-unit { width: 12%; }
.col-qty { width: 8%; }
.col-price { width: 12%; }
.col-discount { width: 12%; }
.col-amount { width: 12%; }
.totals { margin: 2px 0 0; display: flex; justify-content: flex-end; }
table.summary {
  width: ${px(BASE_PX.summaryWidth)};
  border-collapse: collapse;
}
table.summary td.label { text-align: left; font-weight: 700; }
table.summary tr.strong td { font-weight: 700; }
.signs { display: flex; justify-content: space-between; gap: ${px(BASE_PX.signsGap)}; margin-top: ${px(BASE_PX.signsTop)}; text-align: center; }
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
