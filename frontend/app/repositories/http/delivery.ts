import type { AppRecord } from '~/config/admin-seed'
import type {
  DeliveryCommandRepository,
  DeliveryNoteCreateInput,
} from '~/repositories/contracts/entities'
import { ApiEndpoints } from '~/utils/constants/api-endpoints'
import { deliveryApiStatus } from '~/utils/delivery/notes'
import { unwrap } from './entities'

/**

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
      // Canonical body {status, cancel_reason}; UI labels and legacy verb
      // aliases both normalize through deliveryApiStatus (spec §5.13).
      const canonical = deliveryApiStatus(status)
      return unwrap<Record<string, unknown>>(await api.post<unknown>(
        ApiEndpoints.DELIVERY_NOTE_STATUS(id),
        {
          status: canonical,
          cancel_reason: canonical === 'CANCELLED' ? (reason || null) : null,
        },
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
