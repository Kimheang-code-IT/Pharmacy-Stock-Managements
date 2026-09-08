import type { AppRecord } from '~/config/admin-seed'
import type {
  DeliveryCommandRepository,
  DeliveryNoteCreateInput,
  DeliveryStatusActionInput,
} from '~/repositories/contracts/entities'
import { ApiEndpoints } from '~/utils/constants/api-endpoints'
import { unwrap } from './entities'

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

    async setDeliveryStatus(id: string, action: DeliveryStatusActionInput, reason?: string | null): Promise<AppRecord> {
      return unwrap<Record<string, unknown>>(await api.post<unknown>(
        ApiEndpoints.DELIVERY_NOTE_STATUS(id),
        { action, reason: reason || null },
      )) as AppRecord
    },
  }
}
