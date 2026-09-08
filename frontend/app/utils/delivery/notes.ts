import type { AppRecord } from '~/config/admin-seed'

/**
 * Delivery Notes domain helpers (spec §2.1.9).
 * Delivery notes never mutate stock — quantities here only track the
 * fulfillment state of already-sold (stock-out at POS) sale lines.
 */

export const DELIVERY_STATUSES = ['Draft', 'Confirmed', 'Out for Delivery', 'Delivered', 'Cancelled'] as const

export type DeliveryStatus = (typeof DELIVERY_STATUSES)[number]

export type DeliveryStatusAction = 'confirm' | 'out_for_delivery' | 'deliver' | 'cancel'

/** Allowed transitions per status; Delivered/Cancelled are terminal.
 *  Spec §5.13 (simplified UX): **Delivery OK** (`deliver`) is allowed from
 *  every non-terminal status so the user can mark a delivery complete in one
 *  click. Confirm / Out for Delivery remain valid intermediate steps. */
export const DELIVERY_TRANSITIONS: Record<DeliveryStatus, DeliveryStatusAction[]> = {
  Draft: ['confirm', 'deliver', 'cancel'],
  Confirmed: ['out_for_delivery', 'deliver', 'cancel'],
  'Out for Delivery': ['deliver', 'cancel'],
  Delivered: [],
  Cancelled: [],
}

export function isDeliveryStatus(value: unknown): value is DeliveryStatus {
  return (DELIVERY_STATUSES as readonly string[]).includes(String(value))
}

export function deliveryStatusOf(note: AppRecord | null | undefined): DeliveryStatus {
  const value = String(note?.status || '')
  return isDeliveryStatus(value) ? value : 'Draft'
}

export function deliveryLines(note: AppRecord | null | undefined): AppRecord[] {
  const items = note?.items
  return Array.isArray(items) ? items as AppRecord[] : []
}

export function isDeliveryActive(note: AppRecord): boolean {
  return deliveryStatusOf(note) !== 'Cancelled'
}

export function isDeliveryEditable(note: AppRecord): boolean {
  return deliveryStatusOf(note) === 'Draft'
}

/** Whether the action is a legal transition from the note's current status. */
export function canTransitionDelivery(note: AppRecord, action: DeliveryStatusAction): boolean {
  return DELIVERY_TRANSITIONS[deliveryStatusOf(note)].includes(action)
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
    if (String(note.saleId ?? '') !== String(saleId ?? '')) continue
    for (const line of deliveryLines(note)) {
      if (String(line.saleItemId ?? '') !== String(saleItemId ?? '')) continue
      total += Number(line.qtyToDeliver ?? 0)
    }
  }
  return total
}

export interface DeliveryLineAvailability {
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
  return items.map(item => ({
    saleItemId: String(item.id ?? ''),
    productId: String(item.productId ?? ''),
    product: String(item.name ?? ''),
    uomSymbol: String(item.uomSymbol ?? item.uom ?? ''),
    qtyOrdered: Number(item.quantity ?? 0),
    qtyReserved: saleItemReservedQty(sale?.id, item.id, notes),
    qtyRemaining: Number(item.quantity ?? 0) - saleItemReservedQty(sale?.id, item.id, notes),
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
