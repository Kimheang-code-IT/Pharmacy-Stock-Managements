import type { AppRecord } from '~/config/admin-seed'
import type {
  DeliveryCommandRepository,
  DeliveryNoteCreateInput,
} from '~/repositories/contracts/entities'
import { createId, mockLatency, nowIso } from '~/mocks/query'
import { mockInsert, mockUpdate, useMockDb } from '~/mocks/db'
import { saleItemReservedQty, saleHasDeliverableLines } from '~/utils/delivery/notes'

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
      const note = mockInsert('deliveryNotes', {
        deliveryNo,
        customerId: customerId || null,
        customer: String(customer?.name || sales[0]!.customer || 'Walk-in customer'),
        deliveryPhone: input.deliveryPhone || (customer?.phone ? String(customer.phone) : ''),
        deliveryLocation: input.deliveryLocation || String(customer?.location || customer?.address || ''),
        deliveredAt: null,
        status: input.confirm ? 'Confirmed' : 'Draft',
        note: input.note || null,
        cancelReason: null,
        sales: saleLinks,
        items: lines,
        itemCount: lines.length,
        createdBy: 'Sokha Chan',
      })
      addAudit('create', deliveryNo, deliveryNo)
      return mockLatency(note)
    },

    async setDeliveryStatus(id: string, status: string, reason?: string | null): Promise<AppRecord> {
      const db = useMockDb()
      const note = db.collections.deliveryNotes.find(row => String(row.id) === String(id))
      if (!note) throw new Error(`Delivery note not found: ${id}`)

      // Mirrors DELIVERY_TRANSITIONS (spec §2.1.9): Delivered/Cancelled are
      // terminal; a cancel reason is mandatory.
      const transitions: Record<string, string[]> = {
        Draft: ['Confirmed', 'Cancelled'],
        Confirmed: ['Out for Delivery', 'Delivered', 'Cancelled'],
        'Out for Delivery': ['Delivered', 'Cancelled'],
        Delivered: [],
        Cancelled: [],
      }
      const current = String(note.status || 'Draft')
      if (!transitions[current]?.includes(status)) {
        throw new Error(`Cannot move a ${current} delivery note to ${status}`)
      }
      if (status === 'Cancelled') {
        const reasonText = String(reason || '').trim()
        if (!reasonText) throw new Error('A reason is required to cancel a delivery note')
      }

      const patch: Record<string, unknown> = { status }
      if (status === 'Delivered') {
        patch.deliveredAt = nowIso()
        patch.items = (Array.isArray(note.items) ? note.items as AppRecord[] : []).map(line => ({
          ...line,
          qtyDelivered: Number(line.qtyToDeliver ?? 0),
        }))
      }
      else if (status === 'Cancelled') {
        patch.cancelReason = String(reason || '').trim()
      }

      const updated = mockUpdate('deliveryNotes', String(note.id), patch)
      if (!updated) throw new Error(`Delivery note not found: ${id}`)
      addAudit(status, String(note.deliveryNo), String(note.deliveryNo))
      return mockLatency(updated)
    },

    async deliverableInvoices(search?: string | null): Promise<AppRecord[]> {
      const db = useMockDb()
      const needle = String(search || '').trim().toLowerCase()
      // Normalized row shape — identical to the HTTP adapter output of
      // GET /delivery-notes/deliverable-invoices (see DeliverableInvoice).
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
            sku: '',
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
