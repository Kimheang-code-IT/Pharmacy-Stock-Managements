import type {
  AppConfig,
  AppInfo,
  BackupConfig,
  BackupJob,
  BackupTableState,
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

export type MaintenanceAction = 'RESET_ALL_DATA' | 'CLEAR_TRANSACTIONS'

/** One-use reauthentication token for a guarded destructive action. */
export interface MaintenanceConfirmation {
  confirmationToken: string
  phrase: string
  expiresIn: number
}

/** Confirmation supplied to a guarded destructive endpoint. */
export interface DestructiveActionInput {
  /** Required for database restore; reset/clear only require the phrase. */
  confirmationToken?: string
  confirmationPhrase: string
}

export interface ResetAllDataResult {
  message: string
  requiresReauth?: boolean
  backup?: { filename: string, totalRows: number }
}

export interface ClearTransactionsResult {
  cleared: boolean
  message: string
  backup?: { filename: string, totalRows: number }
}

export interface AppConfigRepository {
  get: () => Promise<AppConfig>
  update: (input: Partial<AppConfig>) => Promise<AppConfig>
  resetAllData: (input: DestructiveActionInput) => Promise<ResetAllDataResult>
  /** Delete all sales + purchases and zero stock (master data kept). */
  clearTransactions: (input: DestructiveActionInput) => Promise<ClearTransactionsResult>
  testEmailConnection: () => Promise<{ status: ConnectionStatus, message: string }>
  sendTestEmail: (to: string) => Promise<{ status: ConnectionStatus, message: string }>
  testTelegramConnection: () => Promise<{ status: ConnectionStatus, message: string }>
  sendTestTelegramMessage: (destinationId?: string) => Promise<{ status: ConnectionStatus, message: string }>
}

export interface BackupRepository {
  getSettings: () => Promise<BackupConfig>
  updateSettings: (input: Partial<BackupConfig>) => Promise<BackupConfig>
  testConnection: () => Promise<{ status: ConnectionStatus, message: string }>
  run: () => Promise<{ job: BackupJob, settings: BackupConfig }>
  history: (page?: number, limit?: number) => Promise<{ jobs: BackupJob[], total: number }>
  jobDetail: (id: string) => Promise<BackupJob>
  tables: () => Promise<BackupTableState[]>
  /** Reauthenticate (password) and mint a one-use restore token. */
  requestRestoreConfirmation: (password: string) => Promise<MaintenanceConfirmation>
  restore: (
    input: DestructiveActionInput & { confirmationToken: string, tables?: string[] },
  ) => Promise<{ restored: Record<string, number>, skipped: string[], totalRows: number }>
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
