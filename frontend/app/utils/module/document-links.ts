/** Cross-document navigation for document-number table cells.
 *
 *  Document numbers link to the page that owns the document:
 *  - Cross-page links (debt invoice, returns, delivery, movements) open the
 *    owning report with `?q=` so the number is prefilled in search.
 *  - Sales Report `saleNo` opens POS checkout in view-only mode.
 *  - Purchase Report `purchaseNo` opens the purchase detail form in view-only.
 */

export type DocumentLinkTarget = {
  /** Page path that owns the document. */
  path: string
  /** Document number to prefill as the target page search. */
  search: string
}

/** collection → column → page that owns the document. */
const LINK_RULES: Record<string, Record<string, string>> = {
  customerDebts: { invoiceNo: '/reports/sales' },
  supplierDebts: { purchaseNo: '/reports/purchases' },
  saleReturns: { saleNo: '/reports/sales' },
  purchaseReturns: { purchaseNo: '/reports/purchases' },
  deliveryNotes: { invoiceNo: '/reports/sales' },
}

/** Stock movement references resolve through the movement type. */
const MOVEMENT_TARGETS: Record<string, string> = {
  Sale: '/reports/sales',
  'Stock In': '/reports/purchases',
}

/** Target page for a document-number cell, or null when the cell is not
 *  cross-linked. */
export function documentLinkTargetFor(
  collection: string,
  key: string,
  row: Record<string, unknown>,
): DocumentLinkTarget | null {
  if (collection === 'stockMovements' && key === 'reference') {
    const path = MOVEMENT_TARGETS[String(row.type || '')]
    const search = String(row.reference || '').trim()
    return path && search ? { path, search } : null
  }
  const path = LINK_RULES[collection]?.[key]
  const search = String(row[key] || '').trim()
  return path && search ? { path, search } : null
}

/**
 * Same-page document number → full detail route (no modal).
 * Sale No → POS checkout view; Purchase No → purchase detail view.
 */
export function documentDetailHrefFor(
  collection: string,
  key: string,
  row: Record<string, unknown>,
): string | null {
  const id = String(row.id || '').trim()
  if (!id) return null
  if (collection === 'sales' && key === 'saleNo') {
    return `/pos?viewSaleId=${encodeURIComponent(id)}`
  }
  if (collection === 'stockIns' && key === 'purchaseNo') {
    const purchaseNo = String(row.purchaseNo || '').trim()
    const qs = new URLSearchParams({ viewPurchaseId: id })
    if (purchaseNo) qs.set('purchaseNo', purchaseNo)
    return `/reports/purchases/new?${qs.toString()}`
  }
  return null
}
