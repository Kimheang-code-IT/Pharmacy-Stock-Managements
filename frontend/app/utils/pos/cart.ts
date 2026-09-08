import { defaultSaleRow, divideDecimalSafe, pricingRowsFor } from '~/utils/stock/uom-conversions'

export type PosCartLine = {
  productId: string
  name: string
  barcode: string
  /** UOM display (symbol/name snapshot of the **selected** line UOM). */
  uom: string
  /** Selected line UOM id — base UOM or a product Pricing row. */
  uomId: string
  /** How many base UOM units 1 of the selected UOM contains (base = 1).
   *  Completing the sale stocks out quantity × factorToBase in base UOM. */
  factorToBase: number
  /** UOM options for the line selector: every Pricing row's Original UOM. */
  uomOptions: Array<{ label: string, value: string }>
  imageUrl: string | null
  /** Remaining stock **in the selected UOM** (base stock ÷ factor). */
  availableStock: number
  unitPrice: number
  discountPercent: number
  quantity: number
}

export function lineGross(line: PosCartLine): number {
  return roundMoney(line.unitPrice * line.quantity)
}

export function lineDiscountAmount(line: PosCartLine): number {
  const percent = Math.min(100, Math.max(0, Number(line.discountPercent) || 0))
  return roundMoney(lineGross(line) * (percent / 100))
}

export function lineNet(line: PosCartLine): number {
  return roundMoney(lineGross(line) - lineDiscountAmount(line))
}

export function cartSubtotal(lines: PosCartLine[]): number {
  return roundMoney(lines.reduce((sum, line) => sum + lineGross(line), 0))
}

export function cartDiscountTotal(lines: PosCartLine[]): number {
  return roundMoney(lines.reduce((sum, line) => sum + lineDiscountAmount(line), 0))
}

export function cartTotal(lines: PosCartLine[]): number {
  return roundMoney(lines.reduce((sum, line) => sum + lineNet(line), 0))
}

export function roundMoney(value: number): number {
  return Math.round((Number(value) || 0) * 100) / 100
}

export function productImageUrl(row: Record<string, unknown>): string | null {
  const candidates = [row.imageUrl, row.image, row.photoUrl, row.thumbnailUrl]
  for (const value of candidates) {
    const text = String(value || '').trim()
    if (text) return text
  }
  return null
}

/** Per-product line UOM options (spec §2.1.3 / §5.11): every Pricing row's
 *  **Original UOM** for that product only. Legacy products without Pricing
 *  rows fall back to their base UOM. */
export function uomOptionsFor(product: Record<string, unknown>): Array<{ label: string, value: string }> {
  const rows = pricingRowsFor(product).filter(row => row.uomId)
  if (rows.length) {
    return rows.map(row => ({ label: String(row.uomSymbol || row.uomId || ''), value: row.uomId }))
  }
  return [{ label: String(product.uomSymbol || product.uom || ''), value: String(product.uomId || '') }]
}

/** The UOM a new cart line starts in: the product's **Default sale** Pricing
 *  row; else its base/Original=Convert row; else the first row (spec §2.1.3
 *  POS cart rule 2). Returns the line's uomId, symbol and factorToBase. */
export function defaultLineUomFor(product: Record<string, unknown>): { uomId: string, uomSymbol: string, factorToBase: number } {
  const row = defaultSaleRow(product)
  if (row) {
    return {
      uomId: row.uomId,
      uomSymbol: String(row.uomSymbol || product.uomSymbol || product.uom || ''),
      factorToBase: row.factorToBase,
    }
  }
  return {
    uomId: String(product.uomId || ''),
    uomSymbol: String(product.uomSymbol || product.uom || ''),
    factorToBase: 1,
  }
}

/** Remaining stock shown in the selected UOM: base stock ÷ factorToBase (base UOM factor = 1). */
export function availableStockInUom(baseStock: unknown, factorToBase: unknown): number {
  const factor = Number(factorToBase)
  if (!Number.isFinite(factor) || factor <= 0) return 0
  return divideDecimalSafe(Number(baseStock) || 0, factor)
}
