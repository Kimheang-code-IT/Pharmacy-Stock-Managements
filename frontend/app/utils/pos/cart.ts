import { defaultSaleRow, divideDecimalSafe, pricingRowsFor } from '~/utils/stock/uom-conversions'

export type PosBatchAllocation = {
  batchNo: string
  /** Quantity in the line's selected UOM supplied by this lot. */
  qty: number
  /** Sale price per selected-UOM unit (sale currency). */
  unitPrice: number
}

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
  /** FEFO lot breakdown behind the line (base-UOM lots allocated first-expiry
   *  first). Recomputed whenever the quantity/UOM changes; the server
   *  recomputes authoritatively at checkout. */
  batchAllocations?: PosBatchAllocation[]
  /** POS return mode: the original sale-item id this line returns. */
  saleItemId?: string
}

/** FEFO allocation of `quantity` (selected UOM) across eligible lots. */
export function allocateBatches(
  lots: Array<Record<string, unknown>> | undefined,
  quantity: number,
  factorToBase: number,
): PosBatchAllocation[] {
  const factor = Number(factorToBase) > 0 ? Number(factorToBase) : 1
  const remaining = Math.max(0, Number(quantity) || 0)
  if (!Array.isArray(lots) || remaining <= 0) return []
  const allocations: PosBatchAllocation[] = []
  let left = remaining
  for (const lot of lots) {
    if (left <= 0) break
    const lotSold = (Number(lot.remainingQty ?? 0) || 0) / factor
    const price = Number(lot.unitPrice)
    if (!(lotSold > 0) || !Number.isFinite(price)) continue
    const take = Math.min(lotSold, left)
    allocations.push({
      batchNo: String(lot.batchNo ?? ''),
      qty: round4(take),
      unitPrice: price,
    })
    left -= take
  }
  return allocations
}

/** Blended sale price of an allocation list (gross / quantity). */
export function allocationUnitPrice(allocations: PosBatchAllocation[], quantity: number): number {
  const total = allocations.reduce((sum, row) => sum + row.qty * row.unitPrice, 0)
  return quantity > 0 ? roundMoney(total / quantity) : 0
}

function round4(value: number): number {
  return Math.round((Number(value) || 0) * 10000) / 10000
}

export function lineGross(line: PosCartLine): number {
  if (line.batchAllocations && line.batchAllocations.length) {
    return roundMoney(line.batchAllocations.reduce((sum, row) => sum + row.qty * row.unitPrice, 0))
  }
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
  const allRows = pricingRowsFor(product).filter(row => row.uomId)
  // Only POS-active rows are offered; a product whose pricing rows are all
  // deactivated has no selectable UOM (never falls back to the base UOM).
  const rows = allRows.filter(row => row.isActive !== false)
  if (rows.length) {
    return rows.map(row => ({ label: String(row.uomSymbol || row.uomId || ''), value: row.uomId }))
  }
  if (allRows.length) return []
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
