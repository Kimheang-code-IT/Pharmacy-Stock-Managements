import { barcodeSvg, code128ModuleCount } from '~/utils/barcode/code128'
import { formatNumber } from '~/utils/format/format-service'
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
  /**
   * Thermal printer resolution. The bar (module) width is snapped to this dot
   * grid so printed bars are a whole number of dots — required for scanning.
   */
  printerDpi: number
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
  barcodeAutoFit: true,
  fontSizePt: 8,
  labelsPerRow: 4,
  // Thermal barcode-label printers are the default target: one sticker per
  // label at the exact page size. A4 sheet is still available per-product.
  pageMode: 'label',
  printerDpi: 203,
  showName: true,
  showUsd: true,
  showKhr: true,
}

/** Common sticker sizes — the panel also offers a fully custom width/height. */
export interface BarcodeLabelPreset {
  id: string
  label: string
  widthMm: number
  heightMm: number
}

export const BARCODE_LABEL_PRESETS: BarcodeLabelPreset[] = [
  { id: '30x20', label: '30 × 20 mm', widthMm: 30, heightMm: 20 },
  { id: '40x30', label: '40 × 30 mm', widthMm: 40, heightMm: 30 },
  { id: '50x25', label: '50 × 25 mm', widthMm: 50, heightMm: 25 },
  { id: '50x30', label: '50 × 30 mm', widthMm: 50, heightMm: 30 },
]

const A4_WIDTH_MM = 210
const A4_HEIGHT_MM = 297

/** Sticker inner padding on each side (matches `.bc-label { padding: 1mm }`). */
const LABEL_PADDING_MM = 1
/** CODE128 quiet zone in modules, each side. 10 is the spec minimum. */
const QUIET_ZONE_MODULES = 10
/**
 * Narrowest bar (module) width a barcode should print at to stay reliably
 * scannable — 0.25 mm / 10 mil. This is a physical minimum, independent of the
 * printer DPI, so a 300 or 600 DPI printer is not allowed to shrink every bar
 * below the size a laser/CCD scanner needs.
 */
export const MIN_SCANNABLE_MODULE_MM = 0.25
/** Guards float division so an exact fit is not rejected by rounding noise. */
const EPSILON = 1e-9

export interface BarcodeLayout {
  /** Physical width of one narrow module (mm) — a whole number of printer dots. */
  moduleWidthMm: number
  /** Total symbol width including quiet zones (mm). */
  barcodeWidthMm: number
  /** Module positions including both quiet zones. */
  totalModules: number
  /** Whole printer dots spanned by one module. */
  moduleDots: number
  /** Minimum whole dots that keep the module >= `MIN_SCANNABLE_MODULE_MM`. */
  minModuleDots: number
  /** True when the label is too narrow to print the bars at a scannable width. */
  tooDense: boolean
  /** Narrowest label width, rounded safely up to 0.01 mm, for this DPI's dot grid. */
  minimumLabelWidthMm: number
}

/**
 * Fit the barcode to the sticker at an exact, printer-friendly module width.
 *
 * The module width is the largest **whole number of printer dots** that fits
 * the sticker (`25.4 / dpi` per dot), never below 1 dot. When even the minimum
 * scannable width cannot fit, the layout is flagged `tooDense` instead of
 * squeezing (which would leave fractional dots and blur the bars). The printer
 * DPI is only used to quantise the width — it is never changed to fit.
 */
export function layoutBarcode(
  barcode: string,
  rawSettings: Partial<BarcodeLabelSettings> = {},
): BarcodeLayout {
  const s = normalizeLabelSettings(rawSettings)
  const bars = code128ModuleCount(barcode)
  if (!bars) {
    return {
      moduleWidthMm: 0,
      barcodeWidthMm: 0,
      totalModules: 0,
      moduleDots: 0,
      minModuleDots: 0,
      tooDense: false,
      minimumLabelWidthMm: 0,
    }
  }

  const totalModules = bars + QUIET_ZONE_MODULES * 2
  const dotMm = 25.4 / s.printerDpi
  const innerWidthMm = Math.max(1, s.widthMm - LABEL_PADDING_MM * 2)

  const minModuleDots = Math.ceil((MIN_SCANNABLE_MODULE_MM / dotMm) - EPSILON)
  const dotsThatFit = Math.floor((innerWidthMm / totalModules / dotMm) + EPSILON)
  const moduleDots = Math.max(1, dotsThatFit)
  const moduleWidthMm = moduleDots * dotMm
  return {
    moduleWidthMm,
    barcodeWidthMm: totalModules * moduleWidthMm,
    totalModules,
    moduleDots,
    minModuleDots,
    tooDense: moduleDots < minModuleDots,
    minimumLabelWidthMm: Math.ceil(
      ((totalModules * minModuleDots * dotMm) + LABEL_PADDING_MM * 2 - EPSILON) * 100,
    ) / 100,
  }
}

export interface BarcodePrintState {
  layout: BarcodeLayout
  disabled: boolean
}

export type BarcodePrintValidationReason = 'empty-barcode' | 'too-dense'

/** Typed failure raised before a print document is created. */
export class BarcodePrintValidationError extends Error {
  override readonly name = 'BarcodePrintValidationError'

  constructor(
    readonly reason: BarcodePrintValidationReason,
    readonly labelIndex: number,
    readonly minimumLabelWidthMm: number,
  ) {
    const labelNumber = labelIndex + 1
    const message = reason === 'empty-barcode'
      ? `Barcode label ${labelNumber} cannot be printed because its barcode is empty.`
      : `Barcode label ${labelNumber} is too dense to print. Increase the label width to at least ${minimumLabelWidthMm} mm.`
    super(message)
  }
}

/** Reactive UI safety state backed by the same layout calculation as printing. */
export function barcodePrintState(
  barcode: string,
  rawSettings: Partial<BarcodeLabelSettings> = {},
  externallyDisabled = false,
): BarcodePrintState {
  const value = String(barcode ?? '').trim()
  const layout = layoutBarcode(value, rawSettings)
  return {
    layout,
    disabled: externallyDisabled || !value || layout.tooDense,
  }
}

/** Smallest built-in label preset that safely fits at the selected printer DPI. */
export function recommendBarcodeLabelPreset(
  barcode: string,
  rawSettings: Partial<BarcodeLabelSettings> = {},
): BarcodeLabelPreset | null {
  const settings = normalizeLabelSettings(rawSettings)
  if (!layoutBarcode(barcode, settings).tooDense) return null

  return BARCODE_LABEL_PRESETS.find(preset =>
    preset.widthMm > settings.widthMm
    && !layoutBarcode(barcode, {
      ...settings,
      widthMm: preset.widthMm,
      heightMm: preset.heightMm,
    }).tooDense,
  ) ?? null
}

/** True when the barcode cannot fit the sticker at a scannable bar density. */
export function barcodeTooDense(
  barcode: string,
  rawSettings: Partial<BarcodeLabelSettings> = {},
): boolean {
  return layoutBarcode(barcode, rawSettings).tooDense
}

/**
 * Narrowest label width (mm) that fits the barcode at the minimum scannable
 * module width. DPI-independent — the physical bar size is what matters.
 */
export function minBarcodeWidthMm(barcode: string): number {
  const bars = code128ModuleCount(barcode)
  if (!bars) return 0
  const totalModules = bars + QUIET_ZONE_MODULES * 2
  return Math.ceil(totalModules * MIN_SCANNABLE_MODULE_MM) + LABEL_PADDING_MM * 2
}

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
    barcodeAutoFit: merged.barcodeAutoFit !== false,
    fontSizePt: clamp(merged.fontSizePt, 4, 24, DEFAULT_BARCODE_LABEL_SETTINGS.fontSizePt),
    labelsPerRow: Math.round(clamp(merged.labelsPerRow, 1, 20, DEFAULT_BARCODE_LABEL_SETTINGS.labelsPerRow)),
    pageMode: merged.pageMode === 'label' ? 'label' : 'A4',
    printerDpi: Math.round(clamp(merged.printerDpi, 150, 600, DEFAULT_BARCODE_LABEL_SETTINGS.printerDpi)),
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
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
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
/* The SVG carries its exact width in mm (module-aligned); the CSS only fills
   the row height. Never force width:100% — that reintroduces fractional bars. */
.bc-label .bc-bc svg { display: block; height: 100%; max-width: none; shape-rendering: crispEdges; }
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
  computedLayout?: BarcodeLayout,
): string {
  const s = normalizeLabelSettings(rawSettings)
  // Module width is fitted to the sticker at an exact number of printer dots, so
  // the printed bars are sharp (see layoutBarcode). Quiet zone is the spec 10.
  const layout = computedLayout ?? layoutBarcode(label.barcode, s)
  const svg = layout.moduleWidthMm > 0
    ? barcodeSvg(label.barcode, {
        moduleWidthMm: layout.moduleWidthMm,
        heightMm: s.barcodeHeightMm,
        quietZoneModules: QUIET_ZONE_MODULES,
      })
    : ''

  const prices: string[] = []
  if (s.showUsd) {
    // Label prices keep a stable 2-decimal look (up to 4 when needed).
    const usd = formatNumber(Number(label.priceUsd || 0), {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 4,
    })
    prices.push(`<span class="bc-usd">${escapeHtml(usd)}</span>`)
  }
  if (s.showKhr && label.priceKhr != null) {
    const khr = formatNumber(Math.round(label.priceKhr), { maximumFractionDigits: 0 })
    prices.push(`<span class="bc-khr">${escapeHtml(khr)}៛</span>`)
  }

  // Auto-fit lets the barcode stretch to fill the remaining label height; a
  // fixed height is only applied when auto-fit is turned off.
  const barcodeStyle = s.barcodeAutoFit
    ? ''
    : ` style="flex:0 0 auto;height:${s.barcodeHeightMm}mm"`

  const rows: string[] = []
  if (s.showName) rows.push(`<div class="bc-name">${escapeHtml(label.name)}</div>`)
  if (prices.length) rows.push(`<div class="bc-prices">${prices.join('')}</div>`)
  rows.push(`<div class="bc-bc"${barcodeStyle}>${svg || '&nbsp;'}</div>`)
  rows.push(`<div class="bc-code">${escapeHtml(label.barcode)}</div>`)

  return `<div class="bc-label" style="width:${s.widthMm}mm;height:${s.heightMm}mm;font-size:${s.fontSizePt}pt">${rows.join('')}</div>`
}

export function barcodeSheetCss(s: BarcodeLabelSettings): string {
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

/** Print the sticker sheet after every barcode passes the production layout check. */
export async function printBarcodeLabels(
  labels: BarcodeLabelData[],
  settings: Partial<BarcodeLabelSettings> = {},
): Promise<void> {
  const s = normalizeLabelSettings(settings)
  const labelsToValidate = labels.length ? labels : [{ barcode: '' }]
  for (const [labelIndex, label] of labelsToValidate.entries()) {
    const barcode = String(label.barcode ?? '').trim()
    const layout = layoutBarcode(barcode, s)
    if (!barcode) {
      throw new BarcodePrintValidationError('empty-barcode', labelIndex, 0)
    }
    if (layout.tooDense) {
      throw new BarcodePrintValidationError('too-dense', labelIndex, layout.minimumLabelWidthMm)
    }
  }

  // Thermal labels print on a page exactly the sticker's size, so the browser
  // has no reason to rescale the content (which blurs the bars).
  const thermal = s.pageMode === 'label'
  await printHtmlDocument(buildBarcodeSheetHtml(labels, s), 'Barcode labels', {
    paperSize: 'A4',
    css: barcodeSheetCss(s),
    iframeSize: thermal
      ? { width: `${s.widthMm}mm`, height: `${s.heightMm}mm` }
      : undefined,
  })
}

/** Print a single sample sticker (Test Print) with the current settings. */
export function printBarcodeTestLabel(
  label: BarcodeLabelData,
  settings: Partial<BarcodeLabelSettings> = {},
): Promise<void> {
  return printBarcodeLabels([label], settings)
}
