import type { StorageRepository } from '~/repositories/contracts/settings'
import type {
  ConnectionStatus,
  CreateStorageProviderInput,
  StorageProvider,
  UpdateStorageProviderInput,
} from '~/types/stock-pos/settings'
import { ApiEndpoints } from '~/utils/constants/api-endpoints'
import type { ApiResponse } from '~/types/stock-pos/common'
import { unwrapApiData } from './response'

/**
 * HTTP Storage repository — ready for real backend.
 * Page UI stays independent from transport details.
 *
 * Expected API shape (v2):
 * - GET    /api/v1/settings/storage
 * - GET    /api/v1/settings/storage/:id
 * - POST   /api/v1/settings/storage
 * - PUT    /api/v1/settings/storage/:id
 * - POST   /api/v1/settings/storage/:id/set-default
 * - POST   /api/v1/settings/storage/:id/set-active  { active }
 * - POST   /api/v1/settings/storage/:id/test-connection
 * - DELETE /api/v1/settings/storage/:id
 */
export function createHttpStorageRepository(): StorageRepository {
  const api = useApi()

  return {
    async list() {
      const res = await api.get<StorageProvider[] | ApiResponse<StorageProvider[]>>(
        ApiEndpoints.STORAGE_PROVIDERS,
      )
      return unwrapApiData(res)
    },

    async getById(id) {
      return unwrapApiData(await api.get<StorageProvider | ApiResponse<StorageProvider>>(ApiEndpoints.STORAGE_PROVIDER(id)))
    },

    async create(input: CreateStorageProviderInput) {
      return unwrapApiData(await api.post<StorageProvider | ApiResponse<StorageProvider>>(ApiEndpoints.STORAGE_PROVIDERS, input))
    },

    async update(id, input: UpdateStorageProviderInput) {
      return unwrapApiData(await api.put<StorageProvider | ApiResponse<StorageProvider>>(ApiEndpoints.STORAGE_PROVIDER(id), input))
    },

    async setDefault(id) {
      return unwrapApiData(await api.post<StorageProvider | ApiResponse<StorageProvider>>(ApiEndpoints.STORAGE_PROVIDER_SET_DEFAULT(id), {}))
    },

    async setActive(id, active) {
      return unwrapApiData(await api.post<StorageProvider | ApiResponse<StorageProvider>>(ApiEndpoints.STORAGE_PROVIDER_SET_ACTIVE(id), { active }))
    },

    async testConnection(id) {
      return unwrapApiData(await api.post<
        { status: ConnectionStatus, message: string } | ApiResponse<{ status: ConnectionStatus, message: string }>
      >(
        ApiEndpoints.STORAGE_PROVIDER_TEST(id),
        {},
      ))
    },

    async remove(id) {
      await api.delete(ApiEndpoints.STORAGE_PROVIDER(id))
    },
  }
}

