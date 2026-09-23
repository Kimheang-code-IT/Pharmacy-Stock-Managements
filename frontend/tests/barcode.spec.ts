import { describe, expect, it } from 'vitest'
import { barcodeSvg, encodeCode128B } from '../app/utils/barcode/code128'
import {
  barcodeLabelCss,
  buildBarcodeSheetHtml,
  normalizeLabelSettings,
  printBarcodeLabels,
  printBarcodeTestLabel,
} from '../app/utils/print/barcode-label'

describe('CODE128-B encoder', () => {
  it('encodes Start B + data + checksum + stop for a known value', () => {
    // "A": StartB(104) + 'A'(33) + checksum((104 + 33) % 103 = 34) + stop(106).
    const expected = '11010010000' + '10100011000' + '10001011000' + '1100011101011'
    expect(encodeCode128B('A')).toBe(expected)
  })

  it('emits 11-module symbols plus a 13-module stop', () => {
    // "AB": Start B + 2 data + checksum + stop = 4 × 11 + 13 modules.
    expect(encodeCode128B('AB')).toHaveLength((4 * 11) + 13)
  })

  it('drops non-printable characters and returns empty for blank input', () => {
    expect(encodeCode128B('')).toBe('')
    expect(encodeCode128B('\u0001\u0002')).toBe('')
    expect(encodeCode128B('A\u0001')).toBe(encodeCode128B('A'))
  })

  it('renders an SVG with bars for a value and an empty string for blank', () => {
    expect(barcodeSvg('')).toBe('')
    const svg = barcodeSvg('8801001234')
    expect(svg).toContain('<svg')
    expect(svg).toContain('<rect')
  })
})

describe('barcode label settings', () => {
  it('accepts any custom millimetre size and clamps only unsafe values', () => {
    expect(normalizeLabelSettings({ widthMm: 30, heightMm: 20 }).widthMm).toBe(30)
    expect(normalizeLabelSettings({ widthMm: 33.5, heightMm: 21.5 }).widthMm).toBe(33.5)
    expect(normalizeLabelSettings({ widthMm: 0 }).widthMm).toBe(10)
    expect(normalizeLabelSettings({ heightMm: 9999 }).heightMm).toBe(297)
    expect(normalizeLabelSettings({ labelsPerRow: 0 }).labelsPerRow).toBe(1)
  })

  it('keeps content toggles (defaults on)', () => {
    const defaults = normalizeLabelSettings({})
    expect(defaults.showName).toBe(true)
    expect(defaults.showUsd).toBe(true)
    expect(defaults.showKhr).toBe(true)
    expect(defaults.barcodeAutoFit).toBe(true)
    expect(normalizeLabelSettings({ showName: false }).showName).toBe(false)
  })
})

describe('barcode sticker sheet', () => {
  const label = {
    name: 'Coca-Cola 350ml',
    barcode: '8801001234501',
    priceUsd: 0.8,
    priceKhr: 3200,
  }

  it('renders bars and the number code (name/price can be hidden)', () => {
    const html = buildBarcodeSheetHtml([label], { showName: false, showUsd: false, showKhr: false })
    expect(html).toContain('8801001234501')
    expect(html).toContain('<svg')
    expect(html).not.toContain('bc-prices')
    expect(html).not.toContain('bc-name')
  })

  it('shows product name, USD and KHR price when enabled', () => {
    const html = buildBarcodeSheetHtml([label], {})
    expect(html).toContain('Coca-Cola 350ml')
    expect(html).toContain('0.80')
    expect(html).toContain('៛')
  })

  it('puts the product name at the top, above the barcode', () => {
    const html = buildBarcodeSheetHtml([label], {})
    expect(html.indexOf('Coca-Cola 350ml')).toBeLessThan(html.indexOf('<svg'))
  })

  it('writes the exact custom millimetre values into the layout', () => {
    const html = buildBarcodeSheetHtml([label], {
      widthMm: 45,
      heightMm: 25,
      barcodeHeightMm: 9,
      barcodeAutoFit: false,
      fontSizePt: 8,
    })
    expect(html).toContain('width:45mm')
    expect(html).toContain('height:25mm')
    expect(html).toContain('height:9mm')
    expect(html).toContain('font-size:8pt')
  })

  it('auto-fits the barcode height by default (no fixed barcode height)', () => {
    const html = buildBarcodeSheetHtml([label], {})
    // The label keeps its own size, but the barcode box has no fixed height.
    expect(html).toContain('class="bc-bc"')
    expect(html).not.toMatch(/class="bc-bc" style="[^"]*height:/)
    // The shared stylesheet makes the barcode box fill the remaining height.
    expect(barcodeLabelCss()).toContain('flex: 1 1 auto')
  })

  it('prints the product price when enabled', () => {
    const html = buildBarcodeSheetHtml([label], { showUsd: true, showKhr: false })
    expect(html).toContain('0.80')
    expect(html).toContain('bc-prices')
  })

  it('lays out one label per requested copy', () => {
    const html = buildBarcodeSheetHtml([label, label, { ...label, barcode: '8801009999999' }], { labelsPerRow: 2 })
    expect((html.match(/class="bc-label"/g) || []).length).toBe(3)
    expect(html).toContain('8801009999999')
  })

  it('prints without a DOM (node test environment)', async () => {
    await expect(printBarcodeLabels([label], {})).resolves.toBeUndefined()
    await expect(printBarcodeTestLabel(label, { widthMm: 40, heightMm: 30 })).resolves.toBeUndefined()
  })
})
