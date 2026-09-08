import type { AppConfigRepository, AppInfoRepository, ResetAllDataResult } from '~/repositories/contracts/settings'
import type { ApiResponse } from '~/types/stock-pos/common'
import type { AppConfig, AppInfo, ConnectionStatus } from '~/types/stock-pos/settings'
import { ApiEndpoints } from '~/utils/constants/api-endpoints'
import { applyAdminSettingsGroups, toAdminSettingsValues } from './admin-settings'
import { unwrapApiData } from './response'

type ConnectionResult = { status: ConnectionStatus; message: string }

export function createHttpAppInfoRepository(): AppInfoRepository {
  const api = useApi()
  return {
    get: async () => unwrapApiData(await api.get<AppInfo | ApiResponse<AppInfo>>(ApiEndpoints.APP_INFO)),
    update: async input => unwrapApiData(await api.patch<AppInfo | ApiResponse<AppInfo>>(ApiEndpoints.APP_INFO, input)),
    reset: async () => unwrapApiData(await api.post<AppInfo | ApiResponse<AppInfo>>(ApiEndpoints.APP_INFO_RESET, {})),
  }
}

export function createHttpAppConfigRepository(): AppConfigRepository {
  const api = useApi()
  const postResult = async (endpoint: string, body: Record<string, unknown> = {}) =>
    unwrapApiData(await api.post<ConnectionResult | ApiResponse<ConnectionResult>>(endpoint, body))

  return {
    get: async () => unwrapApiData(await api.get<AppConfig | ApiResponse<AppConfig>>(ApiEndpoints.APP_CONFIG)),
    update: async (input) => {
      // Persist Stock & POS settings through the canonical grouped endpoint.
      const adminValues = toAdminSettingsValues(input)
      if (Object.keys(adminValues).length > 0) {
        const groups = unwrapApiData(
          await api.patch<Record<string, Record<string, unknown>> | ApiResponse<Record<string, Record<string, unknown>>>>(
            ApiEndpoints.ADMIN_SETTINGS,
            { values: adminValues },
          ),
        )
        // Server truth for the mapped groups; the rest of the form model is
        // kept as submitted (sections without a backend settings group).
        return applyAdminSettingsGroups({ ...(input as AppConfig) }, groups)
      }
      return input as AppConfig
    },
    resetAllData: async () => unwrapApiData(
      await api.post<ResetAllDataResult | ApiResponse<ResetAllDataResult>>(ApiEndpoints.RESET_ALL_DATA, {}),
    ),
    testEmailConnection: () => postResult(ApiEndpoints.APP_CONFIG_TEST_EMAIL),
    sendTestEmail: to => postResult(ApiEndpoints.APP_CONFIG_SEND_TEST_EMAIL, { to }),
    testTelegramConnection: () => postResult(ApiEndpoints.APP_CONFIG_TEST_TELEGRAM),
    sendTestTelegramMessage: destinationId => postResult(
      ApiEndpoints.APP_CONFIG_SEND_TEST_TELEGRAM,
      destinationId ? { destinationId } : {},
    ),
  }
}
