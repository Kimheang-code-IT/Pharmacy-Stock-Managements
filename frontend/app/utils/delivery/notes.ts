import type { AppRecord } from '~/config/admin-seed'

/**
 * Delivery Notes domain helpers (spec §2.1.9 / §5.13).
 * Delivery notes never mutate stock — quantities here only track the
 * fulfillment state of already-sold (stock-out at POS) sale lines. One note
 * may cover MANY invoices of the SAME customer (`note.sales`).
 */

export const DELIVERY_STATUSES = ['Draft', 'Confirmed', 'Out for Delivery', 'Delivered', 'Cancelled'] as const

export type DeliveryStatus = (typeof DELIVERY_STATUSES)[number]

export type DeliveryStatusAction = 'confirm' | 'out_for_delivery' | 'deliver' | 'cancel'

/** Allowed next statuses per note status (spec §2.1.9 transition table);
 *  Delivered and Cancelled are terminal. */
export const DELIVERY_TRANSITIONS: Record<DeliveryStatus, DeliveryStatus[]> = {
  Draft: ['Confirmed', 'Cancelled'],
  Confirmed: ['Out for Delivery', 'Delivered', 'Cancelled'],
  'Out for Delivery': ['Delivered', 'Cancelled'],
  Delivered: [],
  Cancelled: [],
}

/** Action shortcuts of the same transition service (§5.13 aliases). */
const ACTION_TO_STATUS: Record<DeliveryStatusAction, DeliveryStatus> = {
  confirm: 'Confirmed',
  out_for_delivery: 'Out for Delivery',
  deliver: 'Delivered',
  cancel: 'Cancelled',
}

export function isDeliveryStatus(value: unknown): value is DeliveryStatus {
  return (DELIVERY_STATUSES as readonly string[]).includes(String(value))
}

export function deliveryStatusOf(note: AppRecord | null | undefined): DeliveryStatus {
  const value = String(note?.status || '')
  return isDeliveryStatus(value) ? value : 'Draft'
}

/** The statuses the list **Update Status** control may offer (spec §5.13). */
export function allowedNextStatuses(note: AppRecord | null | undefined): DeliveryStatus[] {
  return DELIVERY_TRANSITIONS[deliveryStatusOf(note)]
}

export function canTransitionDelivery(note: AppRecord, target: DeliveryStatus): boolean {
  return allowedNextStatuses(note).includes(target)
}

export function canTransitionAction(note: AppRecord, action: DeliveryStatusAction): boolean {
  return canTransitionDelivery(note, ACTION_TO_STATUS[action])
}

export function deliveryLines(note: AppRecord | null | undefined): AppRecord[] {
  const items = note?.items
  return Array.isArray(items) ? items as AppRecord[] : []
}

/** Linked invoices of a note (multi-invoice support, spec §2.1.9). */
export function noteSales(note: AppRecord | null | undefined): Array<{ saleId: string, invoiceNo: string }> {
  const sales = Array.isArray(note?.sales) ? note.sales as AppRecord[] : []
  if (sales.length) {
    return sales.map(sale => ({
      saleId: String(sale.saleId ?? sale.id ?? ''),
      invoiceNo: String(sale.invoiceNo ?? ''),
    }))
  }
  // Legacy single-sale shape.
  const saleId = String(note?.saleId ?? '')
  const invoiceNo = String(note?.invoiceNo ?? note?.saleNo ?? '')
  if (!saleId && !invoiceNo) return []
  return [{ saleId, invoiceNo }]
}

export function noteInvoiceNos(note: AppRecord | null | undefined): string[] {
  const nos = note?.invoiceNos ?? note?.invoiceNo
  if (Array.isArray(nos)) return nos.map(no => String(no)).filter(Boolean)
  return noteSales(note).map(link => link.invoiceNo).filter(Boolean)
}

export function isDeliveryActive(note: AppRecord): boolean {
  return deliveryStatusOf(note) !== 'Cancelled'
}

export function isDeliveryEditable(note: AppRecord): boolean {
  return deliveryStatusOf(note) === 'Draft'
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

/** Total item count across a note's lines (for list columns). */
export function deliveryItemCount(note: AppRecord): number {
  return deliveryLines(note).length
}
