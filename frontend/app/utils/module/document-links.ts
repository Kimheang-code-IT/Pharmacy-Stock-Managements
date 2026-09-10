/** Cross-document navigation for document-number table cells.
 *
 *  Document numbers link to the page that owns the document, pre-filtered by
 *  the number (e.g. Customer Debt `invoiceNo` → Sales Report showing that
 *  invoice). The owning page reads `?q=` into its search box so the linked
 *  document is right there. Document numbers owned by the same page (Sales
 *  Report `saleNo`, Purchase Report `purchaseNo`) open a detail dialog
 *  instead — see WorkspaceView / ReportsDocumentDetailDialog.
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
 *  cross-linked (self-owned numbers open the detail dialog instead). */
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

/** Collections whose document number opens the detail dialog on the same page. */
export function documentDetailKindFor(collection: string, key: string): 'sale' | 'purchase' | null {
  if (collection === 'sales' && key === 'saleNo') return 'sale'
  if (collection === 'stockIns' && key === 'purchaseNo') return 'purchase'
  return null
}
