import type { AppRecord } from '~/config/admin-seed'
import { roundMoney } from '~/utils/pos/cart'

export type ReturnDocumentKind = 'sale' | 'purchase'

export type ReturnLineDraft = {
  lineId: string
  productId: string
  name: string
  uom: string
  soldQty: number
  returnedQty: number
  returnableQty: number
  unitAmount: number
  qty: number
  restock: boolean
}

/** Net unit amount for a sale/purchase line (decimal-safe display math). */
export function lineUnitAmount(line: AppRecord): number {
  const qty = Number(line.quantity || 0)
  if (qty <= 0) return 0
  if (line.total != null && Number.isFinite(Number(line.total))) {
    return roundMoney(Number(line.total) / qty)
  }
  const price = Number(line.price || line.unitCost || 0)
  const discountPercent = Math.min(100, Math.max(0, Number(line.discountPercent || 0)))
  return roundMoney(price * (1 - discountPercent / 100))
}

export function documentLines(doc: AppRecord | null | undefined): AppRecord[] {
  if (!doc || !Array.isArray(doc.items)) return []
  return doc.items as AppRecord[]
}

export function buildReturnLines(doc: AppRecord | null | undefined, kind: ReturnDocumentKind): ReturnLineDraft[] {
  return documentLines(doc).map((line) => {
    const soldQty = Number(line.quantity || 0)
    const returnedQty = Number(line.returnedQuantity || 0)
    const returnableQty = Math.max(0, roundMoney(soldQty - returnedQty))
    return {
      lineId: String(line.id || ''),
      productId: String(line.productId || ''),
      name: String(line.name || ''),
      uom: String(line.uom || ''),
      soldQty,
      returnedQty,
      returnableQty,
      unitAmount: lineUnitAmount(line),
      qty: 0,
      restock: kind === 'sale',
    }
  }).filter(line => line.returnableQty > 0 && line.lineId)
}

export function documentHasReturnableLines(doc: AppRecord | null | undefined): boolean {
  return buildReturnLines(doc, 'sale').length > 0
}

export function returnRefundTotal(lines: ReturnLineDraft[]): number {
  return roundMoney(lines.reduce((sum, line) => {
    const qty = Math.max(0, Number(line.qty || 0))
    if (qty <= 0) return sum
    return sum + roundMoney(qty * line.unitAmount)
  }, 0))
}

export function validateReturnLines(lines: ReturnLineDraft[]): string | null {
  const active = lines.filter(line => Number(line.qty || 0) > 0)
  if (!active.length) return 'empty'
  for (const line of active) {
    const qty = Number(line.qty || 0)
    if (!Number.isFinite(qty) || qty <= 0) return 'invalid'
    if (qty > line.returnableQty + 1e-9) return 'over'
  }
  return null
}
