import type { AppRecord } from '~/config/admin-seed'
import type {
  DeliveryCommandRepository,
  DeliveryNoteCreateInput,
  DeliveryStatusActionInput,
} from '~/repositories/contracts/entities'
import { createId, mockLatency, nowIso } from '~/mocks/query'
import { mockInsert, mockUpdate, useMockDb } from '~/mocks/db'
import { saleItemReservedQty } from '~/utils/delivery/notes'

/**
 * In-memory delivery-note commands mirroring the backend contract (spec
 * §2.1.9): remaining-quantity validation per sale line, DN sequence
 * allocation, audited status transitions, and no stock movements.
 */
export function createMockDeliveryRepository(): DeliveryCommandRepository {
  function sequenceNext(prefix: string, padding: number): string {
    const db = useMockDb()
    const row = db.collections.documentSequences.find(seq => seq.documentType === 'DELIVERY_NOTE')
    const next = Number(row?.lastValue || 0) + 1
    if (row) row.lastValue = next
    return `${prefix}-${String(next).padStart(padding, '0')}`
  }

  function addAudit(action: string, entityId: string, entityLabel: string, result = 'SUCCESS') {
    const db = useMockDb()
    db.collections.auditLogs.unshift({
      id: createId('al'),
      occurredAt: nowIso(),
      userName: 'Sokha Chan',
      user: 'Sokha Chan',
      eventType: 'DELIVERY',
      action,
      entityType: 'DeliveryNote',
      entityId,
      entityLabel,
      entity: entityLabel,
      result,
      ipAddress: '127.0.0.1',
      ipDevice: '127.0.0.1',
    } as AppRecord)
  }

  return {
    async createDeliveryNote(input: DeliveryNoteCreateInput): Promise<AppRecord> {
      const db = useMockDb()
      const sale = db.collections.sales.find(row =>
        String(row.id) === String(input.saleId) || String(row.saleNo) === String(input.saleId))
      if (!sale) throw new Error(`Sale not found: ${input.saleId}`)

      const saleItems = Array.isArray(sale.items) ? sale.items as AppRecord[] : []
      const lines: AppRecord[] = []
      for (const line of input.lines) {
        const qty = Number(line.qtyToDeliver ?? 0)
        if (!Number.isFinite(qty) || qty <= 0) continue
        const item = saleItems.find(row =>
          String(row.id) === String(line.saleItemId) || String(row.productId) === String(line.productId))
        if (!item) throw new Error(`Sale line not found: ${line.saleItemId}`)
        const reserved = saleItemReservedQty(sale.id, item.id, db.collections.deliveryNotes)
        const remaining = Number(item.quantity || 0) - reserved
        if (qty > remaining) {
          throw new Error(`Only ${remaining} of ${Number(item.quantity)} remaining to deliver for ${item.name}`)
        }
        const product = db.collections.products.find(row => String(row.id) === String(item.productId))
        lines.push({
          id: createId('dline'),
          saleItemId: String(item.id),
          productId: String(item.productId),
          product: String(item.name),
          uomSymbol: String(product?.uomSymbol || item.uom || ''),
          qtyOrdered: Number(item.quantity || 0),
          qtyToDeliver: qty,
          qtyDelivered: 0,
        })
      }
      if (!lines.length) throw new Error('Select at least one line with a quantity to deliver')

      const customer = sale.customerId
        ? db.collections.customers.find(row => String(row.id) === String(sale.customerId)) || null
        : null
      const deliveryNo = sequenceNext('DN', 6)
      const note = mockInsert('deliveryNotes', {
        deliveryNo,
        saleId: String(sale.id),
        saleNo: String(sale.saleNo),
        invoiceNo: String(sale.invoiceNo || sale.saleNo),
        customerId: sale.customerId ?? null,
        customer: String(sale.customer || 'Walk-in customer'),
        deliveryName: input.deliveryName || (customer?.name ? String(customer.name) : String(sale.customer || '')),
        deliveryPhone: input.deliveryPhone || (customer?.phone ? String(customer.phone) : ''),
        deliveryAddress: input.deliveryAddress || String(customer?.location || customer?.address || ''),
        scheduledDate: input.scheduledDate || nowIso().slice(0, 10),
        deliveredAt: null,
        status: input.confirm ? 'Confirmed' : 'Draft',
        driverName: input.driverName || null,
        vehicleNote: input.vehicleNote || null,
        note: input.note || null,
        cancelReason: null,
        items: lines,
        itemCount: lines.length,
        createdBy: 'Sokha Chan',
      })
      addAudit('create', deliveryNo, deliveryNo)
      return mockLatency(note)
    },

    async setDeliveryStatus(id: string, action: DeliveryStatusActionInput, reason?: string | null): Promise<AppRecord> {
      const db = useMockDb()
      const note = db.collections.deliveryNotes.find(row => String(row.id) === String(id))
      if (!note) throw new Error(`Delivery note not found: ${id}`)

      const status = String(note.status || 'Draft')
      // Mirrors DELIVERY_TRANSITIONS (spec §5.13): Delivery OK from any
      // non-terminal status; Delivered/Cancelled are terminal.
      const transitions: Record<string, string[]> = {
        Draft: ['confirm', 'deliver', 'cancel'],
        Confirmed: ['out_for_delivery', 'deliver', 'cancel'],
        'Out for Delivery': ['deliver', 'cancel'],
        Delivered: [],
        Cancelled: [],
      }
      if (!transitions[status]?.includes(action)) {
        throw new Error(`Cannot ${action.replaceAll('_', ' ')} a delivery note in status ${status}`)
      }

      const patch: Record<string, unknown> = {}
      if (action === 'confirm') {
        patch.status = 'Confirmed'
      }
      else if (action === 'out_for_delivery') {
        patch.status = 'Out for Delivery'
      }
      else if (action === 'deliver') {
        patch.status = 'Delivered'
        patch.deliveredAt = nowIso()
        patch.items = (Array.isArray(note.items) ? note.items as AppRecord[] : []).map(line => ({
          ...line,
          qtyDelivered: Number(line.qtyToDeliver ?? 0),
        }))
      }
      else {
        const reasonText = String(reason || '').trim()
        if (!reasonText) throw new Error('A reason is required to cancel a delivery note')
        patch.status = 'Cancelled'
        patch.cancelReason = reasonText
        patch.cancelledAt = nowIso()
      }

      const updated = mockUpdate('deliveryNotes', String(note.id), patch)
      if (!updated) throw new Error(`Delivery note not found: ${id}`)
      addAudit(action, String(note.deliveryNo), String(note.deliveryNo))
      return mockLatency(updated)
    },
  }
}
