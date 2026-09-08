import type { AppRecord } from '~/config/admin-seed'
import type {
  DeliveryCommandRepository,
  DeliveryNoteCreateInput,
} from '~/repositories/contracts/entities'
import { ApiEndpoints } from '~/utils/constants/api-endpoints'
import { unwrap } from './entities'

/** Status verbs accepted by the legacy alias surface of /status. */
const STATUS_TO_ACTION: Record<string, string> = {
  Confirmed: 'confirm',
  'Out for Delivery': 'out_for_delivery',
  Delivered: 'deliver',
  Cancelled: 'cancel',
}

/**
 * HTTP delivery-note commands against `/api/v1/delivery-notes`. The backend
 * owns sequence allocation, remaining-quantity validation, permissions and
 * audit trails; the UI only forwards the operation.
 */
export function createHttpDeliveryRepository(): DeliveryCommandRepository {
  const api = useApi()

  return {
    async createDeliveryNote(input: DeliveryNoteCreateInput): Promise<AppRecord> {
      return unwrap<Record<string, unknown>>(await api.post<unknown>(
        ApiEndpoints.DELIVERY_NOTES,
        input as unknown as Record<string, unknown>,
      )) as AppRecord
    },

    async setDeliveryStatus(id: string, status: string, reason?: string | null): Promise<AppRecord> {
      // The canonical body is {status, cancel_reason}; the verb aliases
      // (confirm/deliver/cancel) hit the same transition service.
      const action = STATUS_TO_ACTION[status]
      return unwrap<Record<string, unknown>>(await api.post<unknown>(
        ApiEndpoints.DELIVERY_NOTE_STATUS(id),
        action
          ? { action, reason: reason || null }
          : { status, cancel_reason: reason || null },
      )) as AppRecord
    },

    async deliverableInvoices(search?: string | null): Promise<AppRecord[]> {
      const query = new URLSearchParams()
      if (search && String(search).trim()) query.set('search', String(search).trim())
      const suffix = query.toString() ? `?${query.toString()}` : ''
      const rows = await unwrap<Record<string, unknown>[]>(await api.get<unknown>(
        `${ApiEndpoints.DELIVERY_NOTE_DELIVERABLE_INVOICES}${suffix}`,
      ))
      return rows as AppRecord[]
    },
  }
}
