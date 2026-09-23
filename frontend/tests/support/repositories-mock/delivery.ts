import type { AppRecord } from '~/config/admin-seed'
import type {
  DeliveryCommandRepository,
  DeliveryNoteCreateInput,
  DeliveryNoteFromSaleInput,
  DeliveryNoteUpdateInput,
} from '~/repositories/contracts/entities'
import { createId, mockLatency, nowIso } from '../mocks/query'
import { mockInsert, mockUpdate, useMockDb } from '../mocks/db'
import { deliveryStatusOf, normalizeDeliveryStatusInput, saleItemReservedQty, saleHasDeliverableLines } from '~/utils/delivery/notes'

/**
 * In-memory delivery-note commands mirroring the backend contract (spec
 * §2.1.9): same-customer multi-invoice notes, remaining-quantity validation
 * per sale line, DN sequence allocation, audited status transitions, and no
 * stock movements.
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
      // Group requested lines by parent sale (the request-level saleId is the
      // POS auto-entry shortcut for every line that omits its saleId).
      const groups = new Map<string, AppRecord>()
      for (const line of input.lines) {
        const saleId = String(line.saleId || input.saleId || '')
        if (!saleId) throw new Error('Every delivery line needs its parent sale')
        let sale = groups.get(saleId)
        if (!sale) {
          sale = db.collections.sales.find(row => String(row.id) === saleId)
          if (!sale) throw new Error(`Sale not found: ${saleId}`)
          groups.set(saleId, sale)
        }
      }
      const sales = [...groups.values()]
      if (!sales.length) throw new Error('Select at least one invoice with a quantity to deliver')

      // All invoices on one delivery note must share the same customer.
      const customerIds = new Set(sales.map(sale => String(sale.customerId ?? '')))
      if (customerIds.size > 1) {
        throw new Error('All invoices on one delivery note must belong to the same customer')
      }
      if (input.customerId && !customerIds.has(String(input.customerId))) {
        throw new Error('The selected customer does not match the invoices\' customer')
      }
      const customerId = customerIds.values().next().value!
      const customer = customerId && customerId !== 'null'
        ? db.collections.customers.find(row => String(row.id) === customerId) || null
        : null

      const lines: AppRecord[] = []
      const saleLinks: AppRecord[] = []
      for (const sale of sales) {
        saleLinks.push({
          id: createId('dls'),
          saleId: String(sale.id),
          invoiceNo: String(sale.invoiceNo || sale.saleNo || ''),
          saleDate: String(sale.date ?? sale.saleDate ?? ''),
        })
        const saleItems = Array.isArray(sale.items) ? sale.items as AppRecord[] : []
        for (const line of input.lines.filter(row => String(row.saleId || input.saleId || '') === String(sale.id))) {
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
            saleId: String(sale.id),
            saleItemId: String(item.id),
            productId: String(item.productId),
            product: String(item.name),
            uomSymbol: String(product?.uomSymbol || item.uom || ''),
            qtyOrdered: Number(item.quantity || 0),
            qtyToDeliver: qty,
            qtyDelivered: 0,
          })
        }
      }
      if (!lines.length) throw new Error('Select at least one line with a quantity to deliver')

      const deliveryNo = sequenceNext('DN', 6)
      const joinedInvoiceNos = saleLinks.map(link => String(link.invoiceNo)).filter(Boolean)
      const note = mockInsert('deliveryNotes', {
        deliveryNo,
        customerId: customerId || null,
        customer: String(customer?.name || sales[0]!.customer || 'Walk-in customer'),
        deliveryPhone: input.deliveryPhone || (customer?.phone ? String(customer.phone) : ''),
        deliveryLocation: input.deliveryLocation || String(customer?.location || customer?.address || ''),
        driverName: input.driverName || null,
        vehicleNo: input.vehicleNo || null,
        deliveryDate: input.deliveryDate || null,
        deliveredAt: null,
        // Simplified lifecycle: both draft and confirmed notes are Processing.
        status: 'Processing',
        note: input.note || null,
        cancelReason: null,
        // Same normalized shape as the HTTP adapter of DeliveryNoteOut:
        // linked invoices + joined display keys (multi-invoice, spec §2.1.9).
        sales: saleLinks,
        invoiceNos: joinedInvoiceNos,
        invoiceNo: joinedInvoiceNos.join(', '),
        saleId: saleLinks.length === 1 ? String(saleLinks[0]!.saleId) : '',
        createdAt: nowIso(),
        items: lines,
        itemCount: lines.length,
        createdBy: 'Sokha Chan',
      })
      addAudit('create', deliveryNo, deliveryNo)
      return mockLatency(note)
    },

    async createDeliveryNoteFromSale(saleId: string, input: DeliveryNoteFromSaleInput = {}): Promise<AppRecord> {
      const db = useMockDb()
      const sale = db.collections.sales.find(row => String(row.id) === String(saleId))
      if (!sale) throw new Error(`Sale not found: ${saleId}`)
      const saleItems = Array.isArray(sale.items) ? sale.items as AppRecord[] : []
      const lines = saleItems.flatMap((item) => {
        const reserved = saleItemReservedQty(sale.id, item.id, db.collections.deliveryNotes)
        const qty = Number(item.quantity || 0) - Number(item.returnedQuantity || 0) - reserved
        return qty > 0
          ? [{ saleId, saleItemId: String(item.id), productId: String(item.productId), qtyToDeliver: qty }]
          : []
      })
      if (!lines.length) throw new Error('This sale has no remaining quantity to deliver')
      return this.createDeliveryNote({
        saleId,
        deliveryPhone: input.deliveryPhone ?? null,
        deliveryLocation: input.deliveryLocation ?? null,
        deliveryFee: input.deliveryFee ?? null,
        note: input.note ?? null,
        confirm: input.confirm ?? false,
        lines,
      })
    },

    async updateDeliveryNote(id: string, input: DeliveryNoteUpdateInput): Promise<AppRecord> {
      const db = useMockDb()
      const note = db.collections.deliveryNotes.find(row => String(row.id) === String(id))
      if (!note) throw new Error(`Delivery note not found: ${id}`)
      if (deliveryStatusOf(note) !== 'Processing') {
        throw new Error('Only processing delivery notes can be edited')
      }

      const patch: Record<string, unknown> = {}

      if (input.lines) {
        // Rebuild the line set from the requested invoices (same-customer rule,
        // remaining qty excluding this note's own reservation).
        const groups = new Map<string, AppRecord>()
        for (const line of input.lines) {
          const saleId = String(line.saleId || '')
          if (!saleId) throw new Error('Every line needs its parent sale')
          if (!groups.has(saleId)) {
            const sale = db.collections.sales.find(row => String(row.id) === saleId)
            if (!sale) throw new Error(`Sale not found: ${saleId}`)
            if (String(sale.customerId ?? '') !== String(note.customerId ?? '')) {
              throw new Error('All invoices on one delivery note must belong to the same customer')
            }
            groups.set(saleId, sale)
          }
        }

        const lines: AppRecord[] = []
        const saleLinks: AppRecord[] = []
        for (const [saleId, sale] of groups) {
          saleLinks.push({
            id: createId('dls'),
            saleId,
            invoiceNo: String(sale.invoiceNo || sale.saleNo || ''),
            saleDate: String(sale.date ?? sale.saleDate ?? ''),
          })
          const saleItems = Array.isArray(sale.items) ? sale.items as AppRecord[] : []
          for (const line of input.lines.filter(row => String(row.saleId || '') === saleId)) {
            const qty = Number(line.qtyToDeliver ?? 0)
            if (!Number.isFinite(qty) || qty <= 0) continue
            const item = saleItems.find(row =>
              String(row.id) === String(line.saleItemId) || String(row.productId) === String(line.productId))
            if (!item) throw new Error(`Sale line not found: ${line.saleItemId}`)
            const reserved = saleItemReservedQty(saleId, item.id, db.collections.deliveryNotes, note.id)
            const remaining = Number(item.quantity || 0) - reserved
            if (qty > remaining) {
              throw new Error(`Only ${remaining} of ${Number(item.quantity)} remaining to deliver for ${item.name}`)
            }
            const product = db.collections.products.find(row => String(row.id) === String(item.productId))
            lines.push({
              id: createId('dline'),
              saleId,
              saleItemId: String(item.id),
              productId: String(item.productId),
              product: String(item.name),
              uomSymbol: String(product?.uomSymbol || item.uom || ''),
              qtyOrdered: Number(item.quantity || 0),
              qtyToDeliver: qty,
              qtyDelivered: 0,
            })
          }
        }
        if (!lines.length) throw new Error('Select at least one line with a quantity to deliver')
        const joined = saleLinks.map(link => String(link.invoiceNo)).filter(Boolean)
        Object.assign(patch, {
          sales: saleLinks,
          invoiceNos: joined,
          invoiceNo: joined.join(', '),
          saleId: saleLinks.length === 1 ? String(saleLinks[0]!.saleId) : '',
          items: lines,
          itemCount: lines.length,
        })
      }

      for (const field of ['deliveryPhone', 'deliveryLocation', 'note'] as const) {
        if (input[field] !== undefined) patch[field] = input[field] || null
      }
      if (input.driverName !== undefined) patch.driverName = input.driverName || null
      if (input.vehicleNo !== undefined) patch.vehicleNo = input.vehicleNo || null
      if (input.deliveryDate !== undefined) patch.deliveryDate = input.deliveryDate || null
      if (input.deliveryFee !== undefined) patch.deliveryFee = Number(input.deliveryFee) || null
      patch.updatedAt = nowIso()

      const updated = mockUpdate('deliveryNotes', String(note.id), patch)
      if (!updated) throw new Error(`Delivery note not found: ${id}`)
      addAudit('update', String(note.deliveryNo), String(note.deliveryNo))
      return mockLatency(updated)
    },

    async setDeliveryStatus(id: string, status: string, reason?: string | null): Promise<AppRecord> {
      const db = useMockDb()
      const note = db.collections.deliveryNotes.find(row => String(row.id) === String(id))
      if (!note) throw new Error(`Delivery note not found: ${id}`)

      // Accepts UI labels, verb aliases ('deliver') and backend enums
      // ('OUT_FOR_DELIVERY') — one transition service.
      const target = normalizeDeliveryStatusInput(status)
      // Mirrors DELIVERY_TRANSITIONS: Completed/Cancelled are terminal; a
      // cancel reason is mandatory. Re-applying the current status is a no-op.
      const current = deliveryStatusOf(note)
      if (current === target) return mockLatency(note)
      const transitions: Record<string, string[]> = {
        Processing: ['Completed', 'Cancelled'],
        Completed: [],
        Cancelled: [],
      }
      if (!transitions[current]?.includes(target)) {
        throw new Error(`Cannot move a ${current} delivery note to ${target}`)
      }
      if (target === 'Cancelled') {
        const reasonText = String(reason || '').trim()
        if (!reasonText) throw new Error('A reason is required to cancel a delivery note')
      }

      const patch: Record<string, unknown> = { status: target }
      if (target === 'Completed') {
        patch.deliveredAt = nowIso()
        patch.items = (Array.isArray(note.items) ? note.items as AppRecord[] : []).map(line => ({
          ...line,
          qtyDelivered: Number(line.qtyToDeliver ?? 0),
        }))
      }
      else if (target === 'Cancelled') {
        patch.cancelReason = String(reason || '').trim()
      }

      const updated = mockUpdate('deliveryNotes', String(note.id), patch)
      if (!updated) throw new Error(`Delivery note not found: ${id}`)
      addAudit(target, String(note.deliveryNo), String(note.deliveryNo))
      return mockLatency(updated)
    },

    async deliverableInvoices(search?: string | null): Promise<AppRecord[]> {
      const db = useMockDb()
      const needle = String(search || '').trim().toLowerCase()
      // Normalized row shape — identical to the HTTP adapter output of
      // GET /delivery/deliverable-invoices (see DeliverableInvoice).
      const rows: AppRecord[] = []
      for (const sale of db.collections.sales) {
        if (!saleHasDeliverableLines(sale, db.collections.deliveryNotes)) continue
        if (needle
          && !String(sale.invoiceNo || sale.saleNo || '').toLowerCase().includes(needle)
          && !String(sale.customer || '').toLowerCase().includes(needle)) continue
        const items = (Array.isArray(sale.items) ? sale.items : []) as AppRecord[]
        rows.push({
          id: String(sale.id),
          saleId: String(sale.id),
          invoiceNo: String(sale.invoiceNo || sale.saleNo || ''),
          customerId: String(sale.customerId ?? ''),
          customer: String(sale.customer ?? ''),
          phone: '',
          location: '',
          saleStatus: String(sale.saleStatus || sale.status || ''),
          // Create-table autofill: invoice date + derived fulfillment status.
          sale_date: String(sale.date ?? sale.saleDate ?? ''),
          delivery_status: items.some(item =>
            Number(item.qtyRemaining) === Number(item.qtyOrdered))
            ? 'PENDING'
            : 'PARTIALLY_DELIVERED',
          qtyRemaining: items.reduce((sum, item) => {
            const remaining = Number(item.quantity || 0)
              - Number(item.returnedQuantity || 0)
              - saleItemReservedQty(sale.id, item.id, db.collections.deliveryNotes)
            return sum + Math.max(0, remaining)
          }, 0),
          items: items.map(item => ({
            saleItemId: String(item.id ?? ''),
            productId: String(item.productId ?? ''),
            product: String(item.name ?? ''),
            uomSymbol: String(item.uom ?? ''),
            qtyOrdered: Number(item.quantity ?? 0),
            qtyRemaining: Math.max(0, Number(item.quantity || 0)
              - Number(item.returnedQuantity || 0)
              - saleItemReservedQty(sale.id, item.id, db.collections.deliveryNotes)),
          })).filter(item => item.qtyRemaining > 0),
        } as AppRecord)
      }
      return rows
    },
  }
}
