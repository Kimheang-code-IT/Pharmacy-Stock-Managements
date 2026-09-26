import type {
  AppConfigRepository,
  AppInfoRepository,
  ClearTransactionsResult,
  DestructiveActionInput,
  ResetAllDataResult,
} from '~/repositories/contracts/settings'
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
      let model: AppConfig = { ...(input as AppConfig) }
      if (Object.keys(adminValues).length > 0) {
        const response = unwrapApiData(
          await api.patch<Record<string, Record<string, unknown>> | ApiResponse<Record<string, Record<string, unknown>>>>(
            ApiEndpoints.ADMIN_SETTINGS,
            { values: adminValues },
          ),
        ) as (Record<string, Record<string, unknown>> & { groups?: Record<string, Record<string, unknown>> })
        // SettingsOut wraps the groups under `groups`; unwrap before applying.
        const groups = response?.groups ?? response
        // Server truth for the mapped groups; the rest of the form model is
        // kept as submitted (sections without a backend settings group).
        model = applyAdminSettingsGroups(model, groups)
      }
      // Localization lives on the App Config document (system + currency groups).
      if (input.localization) {
        const updated = unwrapApiData(
          await api.patch<AppConfig | ApiResponse<AppConfig>>(
            ApiEndpoints.APP_CONFIG,
            { localization: input.localization },
          ),
        ) as AppConfig
        model = {
          ...model,
          localization: { ...model.localization, ...(updated?.localization ?? {}) },
        }
      }
      return model
    },
    resetAllData: async (input: DestructiveActionInput) => unwrapApiData(
      await api.post<ResetAllDataResult | ApiResponse<ResetAllDataResult>>(ApiEndpoints.RESET_ALL_DATA, {
        confirmation_phrase: input.confirmationPhrase,
      }),
    ),
    clearTransactions: async (input: DestructiveActionInput) => unwrapApiData(
      await api.post<ClearTransactionsResult | ApiResponse<ClearTransactionsResult>>(ApiEndpoints.CLEAR_TRANSACTIONS, {
        confirmation_phrase: input.confirmationPhrase,
      }),
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
