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

/**
 * Build Purchase Edit line drafts from an original purchase document: every
 * line with its original quantity, unit cost, batch/expiry and UOM so the
 * purchase can be edited and re-saved via PATCH.
 */
export function buildPurchaseEditLines(
  doc: AppRecord | null | undefined,
  productById: Map<string, AppRecord> = new Map(),
): PurchaseReturnLineDraft[] {
  return documentLines(doc).map((line) => {
    const product = productById.get(String(line.productId || '')) || null
    const qty = roundMoney(Number(line.quantity || 0))
    const cost = Number(line.price || line.unitCost || 0)
    return {
      lineId: String(line.id || ''),
      name: String(line.name || product?.name || ''),
      productId: String(line.productId || ''),
      batchNo: String(line.batchNo || ''),
      expiryDate: String(line.expiryDate || ''),
      uomId: String(product?.uomId || ''),
      quantity: qty,
      unitAmount: cost,
      returnableQuantity: qty,
      amount: roundMoney(qty * cost),
    }
  }).filter(line => line.lineId && line.productId)
}

export function documentHasReturnableLines(doc: AppRecord | null | undefined): boolean {
  return buildReturnLines(doc, 'sale').length > 0
}

/** One fixed original purchase line for Purchase Return mode. */
export type PurchaseReturnLineDraft = {
  lineId: string
  name: string
  productId: string
  batchNo: string
  expiryDate: string
  uomId: string
  quantity: number
  unitAmount: number
  returnableQuantity: number
  amount: number
}

/**
 * Build Purchase Return line drafts from an original purchase document:
 * only lines that still have a returnable quantity, carrying the original
 * batch, expiry, UOM and unit cost. Quantity defaults to the full returnable
 * amount (the user may reduce it before submitting).
 */
export function buildPurchaseReturnLines(
  doc: AppRecord | null | undefined,
  productById: Map<string, AppRecord> = new Map(),
): PurchaseReturnLineDraft[] {
  return documentLines(doc)
    .filter(line => Number(line.returnableQuantity || 0) > 0)
    .map((line) => {
      const product = productById.get(String(line.productId || '')) || null
      const receivedReturnable = roundMoney(Number(line.returnableQuantity || 0))
      // Cap at what is still physically in stock: a lot that was already sold
      // cannot be returned to the supplier. Falls back to the received qty when
      // the backend did not report availability.
      const available = line.availableQuantity == null
        ? receivedReturnable
        : roundMoney(Number(line.availableQuantity))
      const qty = Math.max(0, Math.min(receivedReturnable, available))
      const cost = Number(line.price || line.unitCost || 0)
      return {
        lineId: String(line.id || ''),
        name: String(line.name || product?.name || ''),
        productId: String(line.productId || ''),
        batchNo: String(line.batchNo || ''),
        expiryDate: String(line.expiryDate || ''),
        uomId: String(product?.uomId || ''),
        quantity: qty,
        unitAmount: cost,
        returnableQuantity: qty,
        amount: roundMoney(qty * cost),
      }
    })
    .filter(line => line.lineId && line.returnableQuantity > 0)
}
