import { barcodeSvg } from '~/utils/barcode/code128'
import { formatMoney, formatNumber } from '~/utils/format/format-service'
import { escapeHtml, printHtmlDocument } from '~/utils/print/html'

/** How the sheet is laid out on paper. */
export type BarcodePageMode = 'A4' | 'label'

/**
 * Fully user-configurable sticker geometry (millimetres / points), so the same
 * engine drives both A4 sticker sheets and thermal label printers. Every value
 * is written straight into the print CSS — nothing is hardcoded.
 */
export interface BarcodeLabelSettings {
  widthMm: number
  heightMm: number
  gapXMm: number
  gapYMm: number
  marginTopMm: number
  marginLeftMm: number
  barcodeHeightMm: number
  /** Barcode width as a percentage (30…100) of the label's inner width. */
  barcodeScale: number
  /**
   * When true (default) the barcode fills whatever vertical space the label
   * leaves, so tall labels grow the bars automatically — no manual height.
   * `barcodeHeightMm` is only used when this is false.
   */
  barcodeAutoFit: boolean
  /** Text size in points. */
  fontSizePt: number
  labelsPerRow: number
  pageMode: BarcodePageMode
  showName: boolean
  showUsd: boolean
  showKhr: boolean
}

export const DEFAULT_BARCODE_LABEL_SETTINGS: BarcodeLabelSettings = {
  widthMm: 30,
  heightMm: 20,
  gapXMm: 2,
  gapYMm: 2,
  marginTopMm: 8,
  marginLeftMm: 8,
  barcodeHeightMm: 8,
  barcodeScale: 100,
  barcodeAutoFit: true,
  fontSizePt: 7,
  labelsPerRow: 4,
  pageMode: 'A4',
  showName: true,
  showUsd: true,
  showKhr: true,
}

/** Common sticker sizes — the panel also offers a fully custom width/height. */
export const BARCODE_LABEL_PRESETS: Array<{ id: string, label: string, widthMm: number, heightMm: number }> = [
  { id: '30x20', label: '30 × 20 mm', widthMm: 30, heightMm: 20 },
  { id: '40x30', label: '40 × 30 mm', widthMm: 40, heightMm: 30 },
  { id: '50x25', label: '50 × 25 mm', widthMm: 50, heightMm: 25 },
  { id: '50x30', label: '50 × 30 mm', widthMm: 50, heightMm: 30 },
]

const A4_WIDTH_MM = 210
const A4_HEIGHT_MM = 297

export interface BarcodeLabelData {
  name: string
  /** Human-readable barcode value printed under the bars. */
  barcode: string
  /** Sale price in USD (base currency). */
  priceUsd: number
  /** Sale price in KHR; null when no exchange rate is set. */
  priceKhr: number | null
}

function clamp(value: unknown, min: number, max: number, fallback: number): number {
  const number = Number(value)
  if (!Number.isFinite(number)) return fallback
  return Math.min(max, Math.max(min, number))
}

/** Clamp/pad every field so a half-typed value can never break the layout. */
export function normalizeLabelSettings(input: Partial<BarcodeLabelSettings> = {}): BarcodeLabelSettings {
  const merged = { ...DEFAULT_BARCODE_LABEL_SETTINGS, ...input }
  return {
    widthMm: clamp(merged.widthMm, 10, A4_WIDTH_MM, DEFAULT_BARCODE_LABEL_SETTINGS.widthMm),
    heightMm: clamp(merged.heightMm, 8, A4_HEIGHT_MM, DEFAULT_BARCODE_LABEL_SETTINGS.heightMm),
    gapXMm: clamp(merged.gapXMm, 0, 50, DEFAULT_BARCODE_LABEL_SETTINGS.gapXMm),
    gapYMm: clamp(merged.gapYMm, 0, 50, DEFAULT_BARCODE_LABEL_SETTINGS.gapYMm),
    marginTopMm: clamp(merged.marginTopMm, 0, 80, DEFAULT_BARCODE_LABEL_SETTINGS.marginTopMm),
    marginLeftMm: clamp(merged.marginLeftMm, 0, 80, DEFAULT_BARCODE_LABEL_SETTINGS.marginLeftMm),
    barcodeHeightMm: clamp(merged.barcodeHeightMm, 3, 120, DEFAULT_BARCODE_LABEL_SETTINGS.barcodeHeightMm),
    barcodeScale: clamp(merged.barcodeScale, 30, 100, DEFAULT_BARCODE_LABEL_SETTINGS.barcodeScale),
    barcodeAutoFit: merged.barcodeAutoFit !== false,
    fontSizePt: clamp(merged.fontSizePt, 4, 24, DEFAULT_BARCODE_LABEL_SETTINGS.fontSizePt),
    labelsPerRow: Math.round(clamp(merged.labelsPerRow, 1, 20, DEFAULT_BARCODE_LABEL_SETTINGS.labelsPerRow)),
    pageMode: merged.pageMode === 'label' ? 'label' : 'A4',
    showName: merged.showName !== false,
    showUsd: merged.showUsd !== false,
    showKhr: merged.showKhr !== false,
  }
}

/** Element-level CSS shared by screen preview and print (class names are `bc-` scoped). */
export function barcodeLabelCss(): string {
  return `
.bc-label {
  box-sizing: border-box;
  padding: 1mm;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  gap: 0.6mm;
  overflow: hidden;
  text-align: center;
  color: #000;
  background: #fff;
}
.bc-label .bc-prices {
  flex: 0 0 auto;
  display: flex;
  align-items: baseline;
  gap: 1.5mm;
  font-weight: 800;
  line-height: 1;
}
.bc-label .bc-prices .bc-khr { font-size: 0.62em; font-weight: 700; }
.bc-label .bc-bc {
  /* Auto-fit: fill whatever vertical space the name/price/code rows leave. */
  flex: 1 1 auto;
  display: flex;
  align-items: stretch;
  justify-content: center;
  align-self: center;
  max-width: 100%;
  min-height: 3mm;
}
.bc-label .bc-bc svg { width: 100%; height: 100%; display: block; }
.bc-label .bc-code {
  flex: 0 0 auto;
  font-family: "Courier New", monospace;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
  letter-spacing: 0.2mm;
}
.bc-label .bc-name {
  flex: 0 0 auto;
  font-weight: 600;
  line-height: 1.05;
  max-width: 100%;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
`
}

/** One sticker as inline-styled HTML (drives both the preview and the print). */
export function barcodeLabelHtml(
  label: BarcodeLabelData,
  rawSettings: Partial<BarcodeLabelSettings> = {},
): string {
  const s = normalizeLabelSettings(rawSettings)
  const svg = barcodeSvg(label.barcode, { moduleWidth: 2, height: 60, quietZone: 8 })

  const prices: string[] = []
  if (s.showUsd) {
    prices.push(`<span class="bc-usd">${escapeHtml(formatMoney(Number(label.priceUsd || 0), 'USD'))}</span>`)
  }
  if (s.showKhr && label.priceKhr != null) {
    const khr = formatNumber(Math.round(label.priceKhr), { maximumFractionDigits: 0 })
    prices.push(`<span class="bc-khr">${escapeHtml(khr)}៛</span>`)
  }

  // Auto-fit lets the barcode stretch to fill the remaining label height; a
  // fixed height is only applied when auto-fit is turned off.
  const barcodeStyle = s.barcodeAutoFit
    ? `width:${s.barcodeScale}%`
    : `width:${s.barcodeScale}%;height:${s.barcodeHeightMm}mm;flex:0 0 auto`

  const rows: string[] = []
  if (s.showName) rows.push(`<div class="bc-name">${escapeHtml(label.name)}</div>`)
  if (prices.length) rows.push(`<div class="bc-prices">${prices.join('')}</div>`)
  rows.push(`<div class="bc-bc" style="${barcodeStyle}">${svg || '&nbsp;'}</div>`)
  rows.push(`<div class="bc-code">${escapeHtml(label.barcode)}</div>`)

  return `<div class="bc-label" style="width:${s.widthMm}mm;height:${s.heightMm}mm;font-size:${s.fontSizePt}pt">${rows.join('')}</div>`
}

function sheetCss(s: BarcodeLabelSettings): string {
  const thermal = s.pageMode === 'label'
  const pageSize = thermal ? `${s.widthMm}mm ${s.heightMm}mm` : 'A4'
  const pageMargin = thermal ? '0' : `${s.marginTopMm}mm 0 0 ${s.marginLeftMm}mm`
  const sheetWidth = thermal
    ? `${s.widthMm}mm`
    : `${(s.labelsPerRow * s.widthMm) + (Math.max(0, s.labelsPerRow - 1) * s.gapXMm)}mm`
  const pageBreak = thermal
    ? `.sheet .bc-label { break-after: page; page-break-after: always; }
.sheet .bc-label:last-child { break-after: auto; page-break-after: auto; }`
    : `.sheet { break-after: page; page-break-after: always; }
.sheet.last { break-after: auto; page-break-after: auto; }`
  return `
@page { size: ${pageSize}; margin: ${pageMargin}; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: #fff; color: #000; font-family: "Khmer OS Content", "Noto Sans Khmer", Arial, sans-serif; }
@media print { html, body { margin: 0; padding: 0; } }
.sheet {
  width: ${sheetWidth};
  display: flex;
  flex-wrap: wrap;
  align-content: flex-start;
  column-gap: ${s.gapXMm}mm;
  row-gap: ${s.gapYMm}mm;
}
${pageBreak}
${barcodeLabelCss()}
`
}

/** Lay the labels out with the user's exact millimetre values. */
export function buildBarcodeSheetHtml(
  labels: BarcodeLabelData[],
  rawSettings: Partial<BarcodeLabelSettings> = {},
): string {
  const s = normalizeLabelSettings(rawSettings)
  const items = labels.length ? labels : []

  if (s.pageMode === 'label') {
    return `<div class="sheet last">${items.map(label => barcodeLabelHtml(label, s)).join('')}</div>`
  }

  const rowsPerPage = Math.max(
    1,
    Math.floor((A4_HEIGHT_MM - s.marginTopMm + s.gapYMm) / (s.heightMm + s.gapYMm)),
  )
  const perPage = Math.max(1, s.labelsPerRow * rowsPerPage)
  const pageCount = Math.max(1, Math.ceil(items.length / perPage))

  const pages: string[] = []
  for (let page = 0; page < pageCount; page += 1) {
    const slice = items.slice(page * perPage, (page + 1) * perPage)
    const isLast = page === pageCount - 1
    pages.push(`<section class="sheet${isLast ? ' last' : ''}">${slice.map(label => barcodeLabelHtml(label, s)).join('')}</section>`)
  }
  return pages.join('')
}

/** Print the sticker sheet for the given labels and settings. */
export function printBarcodeLabels(
  labels: BarcodeLabelData[],
  settings: Partial<BarcodeLabelSettings> = {},
): Promise<void> {
  const s = normalizeLabelSettings(settings)
  return printHtmlDocument(buildBarcodeSheetHtml(labels, s), 'Barcode labels', {
    paperSize: 'A4',
    css: sheetCss(s),
  })
}

/** Print a single sample sticker (Test Print) with the current settings. */
export function printBarcodeTestLabel(
  label: BarcodeLabelData,
  settings: Partial<BarcodeLabelSettings> = {},
): Promise<void> {
  return printBarcodeLabels([label], settings)
}
