import type {
  AppConfig,
  AppInfo,
  ConnectionStatus,
  CreateStorageProviderInput,
  StorageProvider,
  UpdateStorageProviderInput,
} from '~/types/stock-pos/settings'

export interface AppInfoRepository {
  get: () => Promise<AppInfo>
  update: (input: Partial<AppInfo>) => Promise<AppInfo>
  reset: () => Promise<AppInfo>
}

export interface ResetAllDataResult {
  message: string
  requiresReauth?: boolean
}

export interface AppConfigRepository {
  get: () => Promise<AppConfig>
  update: (input: Partial<AppConfig>) => Promise<AppConfig>
  resetAllData: () => Promise<ResetAllDataResult>
  testEmailConnection: () => Promise<{ status: ConnectionStatus, message: string }>
  sendTestEmail: (to: string) => Promise<{ status: ConnectionStatus, message: string }>
  testTelegramConnection: () => Promise<{ status: ConnectionStatus, message: string }>
  sendTestTelegramMessage: (destinationId?: string) => Promise<{ status: ConnectionStatus, message: string }>
}

export interface StorageRepository {
  list: () => Promise<StorageProvider[]>
  getById: (id: string) => Promise<StorageProvider>
  create: (input: CreateStorageProviderInput) => Promise<StorageProvider>
  update: (id: string, input: UpdateStorageProviderInput) => Promise<StorageProvider>
  setDefault: (id: string) => Promise<StorageProvider>
  setActive: (id: string, active: boolean) => Promise<StorageProvider>
  testConnection: (id: string) => Promise<{ status: ConnectionStatus, message: string }>
  remove: (id: string) => Promise<void>
}
