import { describe, expect, it } from 'vitest'
import { barcodeSvg, code128ModuleCount, encodeCode128, encodeCode128B } from '../app/utils/barcode/code128'
import {
  BARCODE_LABEL_PRESETS,
  barcodeLabelCss,
  barcodeLabelHtml,
  barcodePrintState,
  barcodeSheetCss,
  barcodeTooDense,
  buildBarcodeSheetHtml,
  layoutBarcode,
  MIN_SCANNABLE_MODULE_MM,
  minBarcodeWidthMm,
  normalizeLabelSettings,
  printBarcodeLabels,
  printBarcodeTestLabel,
  recommendBarcodeLabelPreset,
  type BarcodePrintValidationError,
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

  it('uses Code Set C for numeric values so the sticker stays scannable', () => {
    // 10 digits → Start C + 5 pairs + checksum + stop = 7 × 11 + 13.
    expect(encodeCode128('8801001234')).toHaveLength((7 * 11) + 13)
    // Strictly narrower than the same value in Set B.
    expect(encodeCode128('8801001234').length).toBeLessThan(encodeCode128B('8801001234').length)
    // Six-digit internal barcodes are three compact Set C pairs.
    expect(encodeCode128('100001')).toHaveLength((5 * 11) + 13)
  })

  it('switches C → B for an odd trailing digit', () => {
    // 13 digits → Start C + 6 pairs + Code B + 1 digit + checksum + stop.
    expect(encodeCode128('1234567890123')).toHaveLength((10 * 11) + 13)
  })

  it('keeps Code Set B for non-numeric values', () => {
    expect(encodeCode128('AB-12')).toBe(encodeCode128B('AB-12'))
  })

  it('renders an SVG with bars for a value and an empty string for blank', () => {
    expect(barcodeSvg('')).toBe('')
    const svg = barcodeSvg('8801001234')
    expect(svg).toContain('<svg')
    expect(svg).toContain('<rect')
  })

  it('renders exact physical mm width, crisp edges and a 10-module quiet zone', () => {
    const moduleWidthMm = 0.25
    const svg = barcodeSvg('8801001234', { moduleWidthMm })
    // Anti-aliasing blurs scaled bars — force crisp edges for the printer.
    expect(svg).toContain('shape-rendering="crispEdges"')
    // Geometry is in module units; the physical width is exact millimetres.
    const totalModules = encodeCode128('8801001234').length + 2 * 10
    expect(svg).toContain(`viewBox="0 0 ${totalModules} 1"`)
    expect(svg).toContain(`width="${(totalModules * moduleWidthMm).toFixed(4)}mm"`)
  })
})

describe('barcode layout (printer-dot aligned)', () => {
  const dotMm = (dpi: number) => 25.4 / dpi
  const CODES = {
    internal: '100001',
    numeric12: '123456789012',
    short: '1234',
    medium: '5276338490176',
    long: '1234567890123456789012',
  } as const

  it('uses a whole number of printer dots per module at 203/300/600 DPI', () => {
    for (const dpi of [203, 300, 600]) {
      for (const value of Object.values(CODES)) {
        const layout = layoutBarcode(value, { widthMm: 50, printerDpi: dpi })
        expect(layout.moduleDots).toBeGreaterThanOrEqual(1)
        expect(layout.moduleWidthMm).toBeCloseTo(layout.moduleDots * dotMm(dpi), 9)
      }
    }
  })

  it('uses the largest whole dots-per-module that fits every preset', () => {
    for (const printerDpi of [203, 300, 600]) {
      const dotMm = 25.4 / printerDpi
      for (const preset of BARCODE_LABEL_PRESETS) {
        for (const barcode of Object.values(CODES)) {
          const layout = layoutBarcode(barcode, { ...preset, printerDpi })
          const printableWidthMm = preset.widthMm - 2
          expect(layout.barcodeWidthMm).toBeLessThanOrEqual(printableWidthMm + 1e-9)
          expect(layout.totalModules * (layout.moduleDots + 1) * dotMm).toBeGreaterThan(printableWidthMm)
        }
      }
    }
  })

  it.each([203, 300, 600])('fits each barcode only on physically compatible presets at %i DPI', (printerDpi) => {
    const states = Object.fromEntries(BARCODE_LABEL_PRESETS.map(preset => [
      preset.id,
      {
        internal: layoutBarcode(CODES.internal, { ...preset, printerDpi }).tooDense,
        numeric12: layoutBarcode(CODES.numeric12, { ...preset, printerDpi }).tooDense,
        numeric13: layoutBarcode(CODES.medium, { ...preset, printerDpi }).tooDense,
        long: layoutBarcode(CODES.long, { ...preset, printerDpi }).tooDense,
      },
    ]))

    expect(states['30x20']).toEqual({ internal: false, numeric12: true, numeric13: true, long: true })
    expect(states['40x30']).toEqual({ internal: false, numeric12: false, numeric13: false, long: true })
    expect(states['50x25']).toEqual({ internal: false, numeric12: false, numeric13: false, long: false })
    expect(states['50x30']).toEqual({ internal: false, numeric12: false, numeric13: false, long: false })
  })

  it.each([203, 300, 600])('changes from too dense to valid at the exact custom-width boundary at %i DPI', (printerDpi) => {
    const reference = layoutBarcode(CODES.medium, { widthMm: 50, printerDpi })
    const minimumWidthMm = reference.minimumLabelWidthMm
    expect(layoutBarcode(CODES.medium, { widthMm: minimumWidthMm - 0.01, printerDpi }).tooDense).toBe(true)
    expect(layoutBarcode(CODES.medium, { widthMm: minimumWidthMm, printerDpi }).tooDense).toBe(false)
  })

  it('keeps the module width and the 10-module quiet zone scannable', () => {
    for (const dpi of [203, 300, 600]) {
      const layout = layoutBarcode(CODES.medium, { widthMm: 40, printerDpi: dpi })
      expect(layout.tooDense).toBe(false)
      // Bars + 10 modules of quiet zone on each side.
      expect(layout.totalModules).toBe(code128ModuleCount(CODES.medium) + 20)
      expect(layout.barcodeWidthMm).toBeCloseTo(layout.totalModules * layout.moduleWidthMm, 9)
      // Fits inside the sticker's padded width (1 mm padding each side).
      expect(layout.barcodeWidthMm).toBeLessThanOrEqual(40 - 2 + 1e-6)
      // Never below the physical minimum a scanner needs.
      expect(layout.moduleWidthMm).toBeGreaterThanOrEqual(MIN_SCANNABLE_MODULE_MM - 1e-9)
    }
  })

  it('scales the dots with DPI without ever changing the printer DPI', () => {
    const at203 = layoutBarcode(CODES.medium, { widthMm: 40, printerDpi: 203 })
    const at300 = layoutBarcode(CODES.medium, { widthMm: 40, printerDpi: 300 })
    const at600 = layoutBarcode(CODES.medium, { widthMm: 40, printerDpi: 600 })
    expect(at203.moduleDots).toBe(2)
    expect(at300.moduleDots).toBe(3)
    expect(at600.moduleDots).toBe(6)
    // Same physical symbol width regardless of DPI (all ≈ 36 mm).
    expect(Math.abs(at203.barcodeWidthMm - at600.barcodeWidthMm)).toBeLessThan(1.5)
  })

  it('fits short codes on small labels and flags medium/long ones', () => {
    expect(barcodeTooDense(CODES.short, { widthMm: 30, printerDpi: 203 })).toBe(false)
    expect(barcodeTooDense(CODES.medium, { widthMm: 30, printerDpi: 203 })).toBe(true)
    expect(barcodeTooDense(CODES.long, { widthMm: 40, printerDpi: 203 })).toBe(true)
    expect(barcodeTooDense(CODES.long, { widthMm: 60, printerDpi: 203 })).toBe(false)
  })

  it('treats 2 dots at 300 DPI (0.169 mm) as too small', () => {
    // The minimum is a physical size (0.25 mm), so 300 DPI requires 3 dots.
    expect(layoutBarcode(CODES.medium, { widthMm: 40, printerDpi: 300 }).minModuleDots).toBe(3)
    expect(barcodeTooDense(CODES.medium, { widthMm: 30, printerDpi: 300 })).toBe(true)
  })

  it('renders the SVG at the exact layout width', () => {
    const layout = layoutBarcode(CODES.medium, { widthMm: 40, printerDpi: 203 })
    const svg = barcodeSvg(CODES.medium, {
      moduleWidthMm: layout.moduleWidthMm,
      quietZoneModules: 10,
    })
    expect(svg).toContain(`viewBox="0 0 ${layout.totalModules} 1"`)
    expect(svg).toContain(`width="${layout.barcodeWidthMm.toFixed(4)}mm"`)
  })

  it('reports the narrowest label width that still scans (DPI independent)', () => {
    // 13-digit Set C = 123 modules + 20 quiet = 143 × 0.25 mm ≈ 36 + 2 padding.
    expect(minBarcodeWidthMm(CODES.medium)).toBe(38)
    expect(minBarcodeWidthMm(CODES.short)).toBeLessThan(38)
    expect(minBarcodeWidthMm('')).toBe(0)
  })

  it.each([203, 300, 600])('disables printing for dense layouts at %i DPI', (printerDpi) => {
    const state = barcodePrintState(CODES.medium, { widthMm: 30, printerDpi })
    expect(state.layout.tooDense).toBe(true)
    expect(state.disabled).toBe(true)
  })

  it.each([203, 300, 600])('enables printing for valid layouts at %i DPI', (printerDpi) => {
    const state = barcodePrintState(CODES.medium, { widthMm: 50, printerDpi })
    expect(state.layout.tooDense).toBe(false)
    expect(state.disabled).toBe(false)
  })

  it.each([203, 300, 600])('enables printing when width reaches the DPI-safe minimum at %i DPI', (printerDpi) => {
    const narrow = barcodePrintState(CODES.medium, { widthMm: 30, printerDpi })
    const valid = barcodePrintState(CODES.medium, {
      widthMm: narrow.layout.minimumLabelWidthMm,
      printerDpi,
    })
    expect(narrow.disabled).toBe(true)
    expect(valid.layout.tooDense).toBe(false)
    expect(valid.disabled).toBe(false)
  })

  it('disables printing when the barcode is empty or printing is externally disabled', () => {
    expect(barcodePrintState('', { widthMm: 50 }).disabled).toBe(true)
    expect(barcodePrintState('   ', { widthMm: 50 }).disabled).toBe(true)
    expect(barcodePrintState(CODES.short, { widthMm: 50 }, true).disabled).toBe(true)
  })

  it.each([203, 300, 600])('recommends the smallest compatible preset at %i DPI', (printerDpi) => {
    expect(recommendBarcodeLabelPreset(CODES.medium, { widthMm: 30, heightMm: 20, printerDpi })?.id).toBe('40x30')
    expect(recommendBarcodeLabelPreset(CODES.long, { widthMm: 40, heightMm: 30, printerDpi })?.id).toBe('50x25')
    expect(recommendBarcodeLabelPreset(CODES.internal, { widthMm: 30, heightMm: 20, printerDpi })).toBeNull()
  })

  it('returns no preset recommendation when even the widest preset is too narrow', () => {
    expect(recommendBarcodeLabelPreset('ABCDEFGHIJKLMNOPQRSTUVWXYZ', {
      widthMm: 30,
      heightMm: 20,
      printerDpi: 203,
    })).toBeNull()
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

  it('flags a dense code on a narrow label but passes on a wide label', () => {
    // 13-digit Set C ≈ 123 modules × 0.25 mm ≈ 31 mm: too dense at 30 mm…
    expect(barcodeTooDense('1234567890123', { widthMm: 30 })).toBe(true)
    // …but safe once the sticker is wide enough.
    expect(barcodeTooDense('1234567890123', { widthMm: 50 })).toBe(false)
    expect(barcodeTooDense('', { widthMm: 30 })).toBe(false)
  })

  it('keeps content toggles (defaults on)', () => {
    const defaults = normalizeLabelSettings({})
    expect(defaults.widthMm).toBe(30)
    expect(defaults.heightMm).toBe(20)
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
  const internalLabel = { ...label, barcode: '100001' }

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

  it('writes exact physical page sizes for every preset and a custom size', () => {
    const sizes = [
      ...BARCODE_LABEL_PRESETS,
      { id: 'custom', label: 'Custom', widthMm: 47.5, heightMm: 22.5 },
    ]
    for (const size of sizes) {
      const settings = normalizeLabelSettings({ ...size, pageMode: 'label' })
      expect(barcodeSheetCss(settings)).toContain(`@page { size: ${size.widthMm}mm ${size.heightMm}mm; margin: 0; }`)
      expect(buildBarcodeSheetHtml([internalLabel], settings)).toContain(
        `width:${size.widthMm}mm;height:${size.heightMm}mm`,
      )
    }
  })

  it.each([203, 300, 600])('keeps preview SVG geometry identical to the production layout at %i DPI', (printerDpi) => {
    const settings = normalizeLabelSettings({ widthMm: 40, heightMm: 30, printerDpi })
    const layout = layoutBarcode(label.barcode, settings)
    const preview = barcodeLabelHtml(label, settings, layout)
    const printed = buildBarcodeSheetHtml([label], settings)
    const physicalWidth = `width="${layout.barcodeWidthMm.toFixed(4)}mm"`
    expect(preview).toContain(physicalWidth)
    expect(printed).toContain(physicalWidth)
    expect(preview).toContain(`viewBox="0 0 ${layout.totalModules} 1"`)
    expect(printed).toContain(`viewBox="0 0 ${layout.totalModules} 1"`)
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

  it('hides the product price when disabled', () => {
    const html = buildBarcodeSheetHtml([label], { showUsd: false, showKhr: false })
    expect(html).not.toContain('0.80')
    expect(html).not.toContain('bc-prices')
  })

  it('lays out one label per requested copy', () => {
    const html = buildBarcodeSheetHtml([label, label, { ...label, barcode: '8801009999999' }], { labelsPerRow: 2 })
    expect((html.match(/class="bc-label"/g) || []).length).toBe(3)
    expect(html).toContain('8801009999999')
  })

  it('prints without a DOM (node test environment)', async () => {
    await expect(printBarcodeLabels([label], { widthMm: 40, heightMm: 30 })).resolves.toBeUndefined()
    await expect(printBarcodeTestLabel(label, { widthMm: 40, heightMm: 30 })).resolves.toBeUndefined()
  })

  it.each([203, 300, 600])('prints an internal barcode at exactly 30 x 20 mm at %i DPI', async (printerDpi) => {
    const settings = { widthMm: 30, heightMm: 20, pageMode: 'label' as const, printerDpi }
    const layout = layoutBarcode(internalLabel.barcode, settings)
    const html = buildBarcodeSheetHtml([internalLabel], settings)
    expect(layout.tooDense).toBe(false)
    expect(layout.moduleDots).toBeGreaterThanOrEqual(layout.minModuleDots)
    expect(html).toContain('width:30mm;height:20mm')
    await expect(printBarcodeLabels([internalLabel], settings)).resolves.toBeUndefined()
  })

  it.each([203, 300, 600])('blocks direct printing of a too-dense barcode at %i DPI', async (printerDpi) => {
    const layout = layoutBarcode(label.barcode, { widthMm: 30, printerDpi })
    await expect(printBarcodeLabels([label], { widthMm: 30, printerDpi })).rejects.toMatchObject({
      name: 'BarcodePrintValidationError',
      reason: 'too-dense',
      labelIndex: 0,
      minimumLabelWidthMm: layout.minimumLabelWidthMm,
    })
  })

  it.each(['', '   '])('blocks direct printing of an empty barcode (%j)', async (barcode) => {
    await expect(printBarcodeLabels([{ ...label, barcode }], {})).rejects.toEqual(
      expect.objectContaining<Partial<BarcodePrintValidationError>>({
        name: 'BarcodePrintValidationError',
        reason: 'empty-barcode',
        labelIndex: 0,
        minimumLabelWidthMm: 0,
      }),
    )
  })
})
