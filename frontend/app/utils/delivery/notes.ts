import type { AppRecord } from '~/config/admin-seed'

/**
 * Delivery Notes domain helpers (spec §2.1.9 / §5.13).
 * Delivery notes never mutate stock — quantities here only track the
 * fulfillment state of already-sold (stock-out at POS) sale lines. One note
 * may cover MANY invoices of the SAME customer (`note.sales`).
 */

/**
 * Simplified delivery lifecycle shown in the UI: a note is still being
 * delivered (**Processing**) or it is done (**Completed**). `Cancelled` is a
 * terminal exception (backend RETURNED/CANCELLED/FAILED) kept out of the
 * selectable list but still displayable. All richer backend statuses
 * (PENDING/PREPARING/OUT_FOR_DELIVERY/…) collapse into these labels.
 */
export const DELIVERY_STATUSES = ['Processing', 'Completed'] as const

export type DeliveryStatus = 'Processing' | 'Completed' | 'Cancelled'

export type DeliveryStatusAction = 'confirm' | 'out_for_delivery' | 'deliver' | 'cancel'

/** Allowed next statuses per note status; Completed and Cancelled are terminal. */
export const DELIVERY_TRANSITIONS: Record<DeliveryStatus, DeliveryStatus[]> = {
  Processing: ['Completed', 'Cancelled'],
  Completed: [],
  Cancelled: [],
}

/** Action shortcuts of the same transition service (§5.13 aliases). */
const ACTION_TO_STATUS: Record<DeliveryStatusAction, DeliveryStatus> = {
  confirm: 'Processing',
  out_for_delivery: 'Processing',
  deliver: 'Completed',
  cancel: 'Cancelled',
}

export function isDeliveryStatus(value: unknown): value is DeliveryStatus {
  return value === 'Processing' || value === 'Completed' || value === 'Cancelled'
}

/** Canonical backend status for a UI label or legacy verb alias (§5.13). */
export const DELIVERY_STATUS_TO_API: Record<string, string> = {
  Processing: 'PREPARING',
  Completed: 'DELIVERED',
  Cancelled: 'CANCELLED',
  // §5.13 verb aliases of the same transition service.
  confirm: 'PREPARING',
  out_for_delivery: 'OUT_FOR_DELIVERY',
  deliver: 'DELIVERED',
  cancel: 'CANCELLED',
}

/** Accepts a UI status label ('Processing') or a legacy verb alias
 *  ('deliver'); returns the canonical backend status for POST /status. */
export function deliveryApiStatus(value: unknown): string {
  const raw = String(value ?? '').trim()
  return DELIVERY_STATUS_TO_API[raw]
    ?? DELIVERY_STATUS_TO_API[raw.toLowerCase().replaceAll(' ', '_')]
    ?? raw.toUpperCase()
}

/** Normalize any status dialect (UI label, verb alias, backend enum) to the
 *  simplified UI label the components use. */
export function normalizeDeliveryStatusInput(value: unknown): DeliveryStatus {
  const raw = String(value ?? '').trim()
  if (isDeliveryStatus(raw)) return raw
  const byVerb = ACTION_TO_STATUS[raw as DeliveryStatusAction]
  if (byVerb) return byVerb
  const byApi: Record<string, DeliveryStatus> = {
    // Backend vocabulary (delivery/models.py) plus legacy aliases.
    PENDING: 'Processing',
    DRAFT: 'Processing',
    PREPARING: 'Processing',
    CONFIRMED: 'Processing',
    OUT_FOR_DELIVERY: 'Processing',
    PARTIALLY_DELIVERED: 'Processing',
    FAILED: 'Processing',
    DELIVERED: 'Completed',
    RETURNED: 'Cancelled',
    CANCELLED: 'Cancelled',
  }
  return byApi[raw.toUpperCase()] ?? 'Processing'
}

export function deliveryStatusOf(note: AppRecord | null | undefined): DeliveryStatus {
  const value = String(note?.status || '')
  return isDeliveryStatus(value) ? value : normalizeDeliveryStatusInput(value)
}

/** i18n key of a delivery status label (must exist in every locale). */
export function deliveryStatusLabelKey(status: unknown): string {
  const normalized = normalizeDeliveryStatusInput(status)
  const keys: Record<DeliveryStatus, string> = {
    Processing: 'app.delivery.statusProcessing',
    Completed: 'app.delivery.statusCompleted',
    Cancelled: 'app.delivery.statusCancelled',
  }
  return keys[normalized]
}

/** i18n key of an invoice delivery-fulfillment status (backend enum). */
export function invoiceDeliveryStatusLabelKey(status: unknown): string {
  const raw = String(status ?? '').trim().toUpperCase()
  const keys: Record<string, string> = {
    FULLY_DELIVERED: 'app.delivery.statusDelivered',
    PARTIALLY_DELIVERED: 'app.delivery.statusPartiallyDelivered',
    PENDING: 'app.delivery.statusPending',
    UNDELIVERED: 'app.delivery.statusPending',
  }
  return keys[raw] ?? 'app.delivery.statusPending'
}

/** The statuses the list **Update Status** control may offer (spec §5.13). */
export function allowedNextStatuses(note: AppRecord | null | undefined): DeliveryStatus[] {
  return DELIVERY_TRANSITIONS[deliveryStatusOf(note)]
}

/** Accepts a UI status label or a legacy verb alias as the target. */
export function canTransitionDelivery(note: AppRecord, target: DeliveryStatus | DeliveryStatusAction): boolean {
  return allowedNextStatuses(note).includes(normalizeDeliveryStatusInput(target))
}

export function deliveryLines(note: AppRecord | null | undefined): AppRecord[] {
  const items = note?.items
  return Array.isArray(items) ? items as AppRecord[] : []
}

/** Linked invoices of a note (multi-invoice support, spec §2.1.9). */
export function noteSales(note: AppRecord | null | undefined): Array<{ saleId: string, invoiceNo: string, saleDate: string }> {
  const sales = Array.isArray(note?.sales) ? note.sales as AppRecord[] : []
  if (sales.length) {
    return sales.map(sale => ({
      saleId: String(sale.saleId ?? sale.id ?? ''),
      invoiceNo: String(sale.invoiceNo ?? ''),
      saleDate: String(sale.saleDate ?? sale.sale_date ?? sale.date ?? ''),
    }))
  }
  // Legacy single-sale shape.
  const saleId = String(note?.saleId ?? '')
  const invoiceNo = String(note?.invoiceNo ?? note?.saleNo ?? '')
  if (!saleId && !invoiceNo) return []
  return [{ saleId, invoiceNo, saleDate: '' }]
}

export function isDeliveryActive(note: AppRecord): boolean {
  return deliveryStatusOf(note) !== 'Cancelled'
}

export function isDeliveryEditable(note: AppRecord): boolean {
  // Only a not-yet-confirmed note is editable (backend: PENDING/DRAFT). The
  // HTTP adapter keeps the raw enum in `statusRaw` because `status` is the
  // collapsed Processing/Completed label.
  const raw = String((note as Record<string, unknown>)?.statusRaw ?? note?.status ?? '')
    .trim()
    .toUpperCase()
  return raw === 'PENDING' || raw === 'DRAFT' || raw === 'PROCESSING'
}

/**
 * Sum of quantities already committed to delivery notes (non-cancelled) for a
 * sale line. Cancelled notes release their reserved quantities automatically.
 */
export function saleItemReservedQty(
  saleId: unknown,
  saleItemId: unknown,
  notes: AppRecord[],
  excludeNoteId?: unknown,
): number {
  let total = 0
  for (const note of notes) {
    if (!isDeliveryActive(note)) continue
    if (excludeNoteId && String(note.id) === String(excludeNoteId)) continue
    const linked = noteSales(note).some(link => link.saleId === String(saleId ?? ''))
    if (!linked) continue
    for (const line of deliveryLines(note)) {
      if (String(line.saleItemId ?? '') !== String(saleItemId ?? '')) continue
      total += Number(line.qtyToDeliver ?? 0)
    }
  }
  return total
}

export interface DeliveryLineAvailability {
  saleId: string
  invoiceNo: string
  saleItemId: string
  productId: string
  product: string
  uomSymbol: string
  qtyOrdered: number
  qtyReserved: number
  qtyRemaining: number
}

/** Sale lines with their remaining deliverable quantity for a given sale. */
export function deliverableLines(sale: AppRecord | null | undefined, notes: AppRecord[]): DeliveryLineAvailability[] {
  const items = Array.isArray(sale?.items) ? sale.items as AppRecord[] : []
  const invoiceNo = String(sale?.invoiceNo || sale?.saleNo || '')
  const saleId = String(sale?.id ?? '')
  return items.map(item => ({
    saleId,
    invoiceNo,
    saleItemId: String(item.id ?? ''),
    productId: String(item.productId ?? ''),
    product: String(item.name ?? ''),
    uomSymbol: String(item.uomSymbol ?? item.uom ?? ''),
    qtyOrdered: Number(item.quantity ?? 0),
    qtyReserved: saleItemReservedQty(saleId, item.id, notes),
    qtyRemaining: Number(item.quantity ?? 0) - saleItemReservedQty(saleId, item.id, notes),
  }))
}

/** True when at least one sale line still has quantity left to deliver. */
export function saleHasDeliverableLines(sale: AppRecord | null | undefined, notes: AppRecord[]): boolean {
  return deliverableLines(sale, notes).some(line => line.qtyRemaining > 0)
}

/**
 * One confirmed invoice with remaining deliverable qty — the normalized row
 * shape of `deliverableInvoices()`.
 * Mirrors GET /delivery/deliverable-invoices (spec §2.1.9).
 */
export interface DeliverableInvoiceItem {
  saleItemId: string
  productId: string
  product: string
  sku: string
  uomSymbol: string
  qtyOrdered: number
  qtyRemaining: number
}

export interface DeliverableInvoice {
  saleId: string
  invoiceNo: string
  customerId: string
  customer: string
  phone: string
  location: string
  saleStatus: string
  /** Invoice date (sale_date snapshot) — auto-filled in the create table. */
  date: string
  /** Derived delivery-fulfillment status (NOT_DELIVERED | PARTIALLY_DELIVERED). */
  deliveryStatus: string
  qtyRemaining: number
  items: DeliverableInvoiceItem[]
}

function num4(value: unknown): number {
  return Math.round((Number(value ?? 0) + Number.EPSILON) * 10000) / 10000
}

/** Normalize one deliverable-invoice row (backend snake_case or camelCase). */
export function normalizeDeliverableInvoice(row: Record<string, unknown>): DeliverableInvoice {
  const rawItems = Array.isArray(row.items) ? row.items as Record<string, unknown>[] : []
  return {
    saleId: String(row.saleId ?? row.sale_id ?? row.id ?? ''),
    invoiceNo: String(row.invoiceNo ?? row.invoice_no ?? row.saleNo ?? ''),
    customerId: String(row.customerId ?? row.customer_id ?? ''),
    customer: String(row.customerName ?? row.customer_name ?? row.customer ?? ''),
    phone: String(row.phone ?? ''),
    location: String(row.location ?? row.address ?? ''),
    saleStatus: String(row.saleStatus ?? row.sale_status ?? ''),
    date: String(row.date ?? row.saleDate ?? row.sale_date ?? ''),
    deliveryStatus: String(row.deliveryStatus ?? row.delivery_status ?? 'NOT_DELIVERED'),
    qtyRemaining: num4(row.qtyRemaining ?? row.qty_remaining),
    items: rawItems.map(item => ({
      saleItemId: String(item.saleItemId ?? item.sale_item_id ?? item.id ?? ''),
      productId: String(item.productId ?? item.product_id ?? ''),
      product: String(item.product ?? item.product_name ?? item.name ?? ''),
      sku: String(item.sku ?? ''),
      uomSymbol: String(item.uomSymbol ?? item.uom_symbol ?? item.uom ?? ''),
      qtyOrdered: num4(item.qtyOrdered ?? item.qty_ordered ?? item.quantity),
      qtyRemaining: num4(item.qtyRemaining ?? item.qty_remaining),
    })).filter(item => item.qtyRemaining > 0 && item.saleItemId),
  }
}

/** Total item count across a note's lines (for list columns). */
export function deliveryItemCount(note: AppRecord): number {
  return deliveryLines(note).length
}
