import type { BackupRepository, DestructiveActionInput, MaintenanceConfirmation } from '~/repositories/contracts/settings'
import type { ApiResponse } from '~/types/stock-pos/common'
import type {
  BackupConfig,
  BackupJob,
  BackupTableState,
  ConnectionStatus,
} from '~/types/stock-pos/settings'
import { ApiEndpoints } from '~/utils/constants/api-endpoints'
import { unwrapApiData } from './response'

type ConnectionResult = { status: ConnectionStatus; message: string }

export function createHttpBackupRepository(): BackupRepository {
  const api = useApi()

  return {
    getSettings: async () => unwrapApiData(
      await api.get<BackupConfig | ApiResponse<BackupConfig>>(ApiEndpoints.BACKUP_SETTINGS),
    ),

    updateSettings: async input => unwrapApiData(
      await api.patch<BackupConfig | ApiResponse<BackupConfig>>(ApiEndpoints.BACKUP_SETTINGS, input),
    ),

    testConnection: async () => unwrapApiData(
      await api.post<ConnectionResult | ApiResponse<ConnectionResult>>(
        ApiEndpoints.BACKUP_TEST_CONNECTION,
        {},
      ),
    ),

    run: async () => unwrapApiData(
      await api.post<{ job: BackupJob, settings: BackupConfig } | ApiResponse<{ job: BackupJob, settings: BackupConfig }>>(
        ApiEndpoints.BACKUP_RUN,
        {},
      ),
    ),

    history: async (page = 1, limit = 20) => {
      const response = await api.get<ApiResponse<BackupJob[]>>(ApiEndpoints.BACKUP_HISTORY, {
        query: { page, limit },
      })
      return {
        jobs: response?.data ?? [],
        total: Number(response?.meta?.total ?? response?.data?.length ?? 0),
      }
    },

    jobDetail: async id => unwrapApiData(
      await api.get<BackupJob | ApiResponse<BackupJob>>(ApiEndpoints.BACKUP_HISTORY_DETAIL(id)),
    ),

    tables: async () => unwrapApiData(
      await api.get<BackupTableState[] | ApiResponse<BackupTableState[]>>(ApiEndpoints.BACKUP_TABLES),
    ),

    requestRestoreConfirmation: async (password: string) => {
      const data = unwrapApiData(
        await api.post<MaintenanceConfirmation | ApiResponse<MaintenanceConfirmation>>(
          ApiEndpoints.BACKUP_REAUTH,
          { password, action: 'RESTORE_DATABASE' },
        ),
      ) as MaintenanceConfirmation & { confirmation_token?: string, expires_in?: number }
      return {
        confirmationToken: data.confirmationToken || data.confirmation_token || '',
        phrase: data.phrase || '',
        expiresIn: Number(data.expiresIn ?? data.expires_in ?? 0),
      }
    },

    restore: async (input: DestructiveActionInput & { confirmationToken: string, tables?: string[] }) => unwrapApiData(
      await api.post<{ restored: Record<string, number>, skipped: string[], totalRows: number }>(
        ApiEndpoints.BACKUP_RESTORE,
        {
          confirmation_token: input.confirmationToken,
          confirmation_phrase: input.confirmationPhrase,
          tables: input.tables,
        },
      ),
    ),
  }
}
