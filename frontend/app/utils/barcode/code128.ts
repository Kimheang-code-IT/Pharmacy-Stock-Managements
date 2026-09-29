/**
 * Minimal, dependency-free CODE128-B barcode encoder.
 *
 * Auto-issued barcodes are digits-only, but a product may carry a custom
 * alphanumeric code, so CODE128-B is the right symbology: it covers the full
 * printable ASCII range and scans reliably. The module renders an inline SVG —
 * no canvas, no external library.
 */

/** CODE128 bar/space module patterns, index 0…106 (103=StartA, 104=StartB, 105=StartC, 106=Stop). */
const CODE128_PATTERNS: readonly string[] = [
  '11011001100', '11001101100', '11001100110', '10010011000', '10010001100',
  '10001001100', '10011001000', '10011000100', '10001100100', '11001001000',
  '11001000100', '11000100100', '10110011100', '10011011100', '10011001110',
  '10111001100', '10011101100', '10011100110', '11001110010', '11001011100',
  '11001001110', '11011100100', '11001110100', '11101101110', '11101001100',
  '11100101100', '11100100110', '11101100100', '11100110100', '11100110010',
  '11011011000', '11011000110', '11000110110', '10100011000', '10001011000',
  '10001000110', '10110001000', '10001101000', '10001100010', '11010001000',
  '11000101000', '11000100010', '10110111000', '10110001110', '10001101110',
  '10111011000', '10111000110', '10001110110', '11101110110', '11010001110',
  '11000101110', '11011101000', '11011100010', '11011101110', '11101011000',
  '11101000110', '11100010110', '11101101000', '11101100010', '11100011010',
  '11101111010', '11001000010', '11110001010', '10100110000', '10100001100',
  '10010110000', '10010000110', '10000101100', '10000100110', '10110010000',
  '10110000100', '10011010000', '10011000010', '10000110100', '10000110010',
  '11000010010', '11001010000', '11110111010', '11000010100', '10001111010',
  '10100111100', '10010111100', '10010011110', '10111100100', '10011110100',
  '10011110010', '11110100100', '11110010100', '11110010010', '11011011110',
  '11011110110', '11110110110', '10101111000', '10100011110', '10001011110',
  '10111101000', '10111100010', '11110101000', '11110100010', '10111011110',
  '10111101110', '11101011110', '11110101110', '11010000100', '11010010000',
  '11010011100', '1100011101011',
]

const START_B = 104
const START_C = 105
const CODE_B = 100
const STOP = 106
const MODULO = 103

/**
 * Encode a value as a CODE128 module bit string (1 = bar, 0 = space).
 * Characters outside printable ASCII (32…126) are dropped — empty input
 * yields an empty string so callers can show a placeholder.
 */
export function encodeCode128B(value: string): string {
  const codes: number[] = [START_B]
  let checksum = START_B
  let position = 1
  for (const char of value) {
    const code = char.charCodeAt(0) - 32
    if (code < 0 || code > 94) continue
    codes.push(code)
    checksum += code * position
    position += 1
  }
  if (codes.length === 1) return ''
  codes.push(checksum % MODULO)
  codes.push(STOP)
  return codes.map(code => CODE128_PATTERNS[code]).join('')
}

/**
 * Auto-select the narrowest CODE128 code set.
 *
 * Numeric values use **Code Set C** (two digits per symbol), which is roughly
 * half the width of Set B — critical for small stickers: a 13-digit code at
 * 203 DPI cannot resolve ~7 modules/mm, but Set C brings it into range. An odd
 * trailing digit switches to Set B for that one character. Non-numeric values
 * fall back to Code Set B (full printable ASCII).
 */
export function encodeCode128(value: string): string {
  const text = [...String(value ?? '')]
    .filter((char) => {
      const code = char.charCodeAt(0) - 32
      return code >= 0 && code <= 94
    })
    .join('')
  if (!text) return ''

  const codes: number[] = []
  let checksum = 0
  let position = 1
  const addSymbol = (code: number) => {
    codes.push(code)
    checksum += code * position
    position += 1
  }

  if (/^\d+$/.test(text) && text.length >= 2) {
    codes.push(START_C)
    checksum = START_C
    const pairsEnd = text.length - (text.length % 2)
    for (let index = 0; index < pairsEnd; index += 2) {
      addSymbol(Number(text.slice(index, index + 2)))
    }
    // Odd trailing digit: switch to Set B for the final character.
    if (pairsEnd < text.length) {
      addSymbol(CODE_B)
      addSymbol(text.charCodeAt(pairsEnd) - 32)
    }
  }
  else {
    codes.push(START_B)
    checksum = START_B
    for (const char of text) addSymbol(char.charCodeAt(0) - 32)
  }

  codes.push(checksum % MODULO)
  codes.push(STOP)
  return codes.map(code => CODE128_PATTERNS[code]).join('')
}

export interface BarcodeSvgOptions {
  /**
   * Physical width of one narrow module in millimetres. The label builder snaps
   * this to the printer's dot grid (`25.4 / dpi`) so every bar is a whole
   * number of printer dots — fractional dots are what make a printed barcode
   * unreadable even when the on-screen preview scans.
   */
  moduleWidthMm?: number
  /** Bar height in millimetres; the label CSS stretches it to fill (default 12). */
  heightMm?: number
  /** Quiet zone in modules on each side (default 10 — the CODE128 minimum). */
  quietZoneModules?: number
}

/** Number of narrow modules in the encoded symbol (bars only, no quiet zone). */
export function code128ModuleCount(value: string): number {
  return encodeCode128(String(value ?? '').trim()).length
}

/**
 * Render a value as an inline SVG string.
 *
 * The viewBox is expressed in **module units** (one bar = one unit) and the
 * physical `width` is written in millimetres, so the printed geometry is exact
 * regardless of browser/print scaling. The label CSS only stretches the height
 * (`height:100%`), which is harmless for a 1-D symbol.
 */
export function barcodeSvg(value: string, options: BarcodeSvgOptions = {}): string {
  const bits = encodeCode128(String(value ?? '').trim())
  if (!bits) return ''

  const moduleWidthMm = options.moduleWidthMm ?? 0.25
  const heightMm = options.heightMm ?? 12
  // CODE128 requires a quiet zone of at least 10 narrow modules on each side.
  const quiet = options.quietZoneModules ?? 10
  const totalModules = bits.length + quiet * 2
  const widthMm = totalModules * moduleWidthMm

  const bars: string[] = []
  let x = quiet
  let index = 0
  while (index < bits.length) {
    if (bits[index] === '1') {
      let run = 1
      while (bits[index + run] === '1') run += 1
      bars.push(`<rect x="${x}" y="0" width="${run}" height="1"/>`)
      x += run
      index += run
    }
    else {
      x += 1
      index += 1
    }
  }

  const label = escapeXml(value)
  const width = `${widthMm.toFixed(4)}mm`
  // Exact physical width + crisp edges; height is left to the label CSS.
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${heightMm}mm" viewBox="0 0 ${totalModules} 1" role="img" aria-label="${label}" preserveAspectRatio="none" shape-rendering="crispEdges" style="shape-rendering:crispEdges;width:${width};height:100%"><rect width="${totalModules}" height="1" fill="#ffffff"/><g fill="#000000">${bars.join('')}</g></svg>`
}

function escapeXml(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}
