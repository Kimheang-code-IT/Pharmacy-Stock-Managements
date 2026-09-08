import type {
  AppConfig,
  AppInfo,
  ConnectionStatus,
  CreateStorageProviderInput,
  StorageProvider,
  UpdateStorageProviderInput,
} from '~/types/stock-pos/settings'
import type {
  AppConfigRepository,
  AppInfoRepository,
  ResetAllDataResult,
  StorageRepository,
} from '~/repositories/contracts/settings'
import { DEFAULT_FORMAT_CONFIG } from '~/utils/format/format-service'
import { createId, mockLatency, nowIso } from '~/mocks/query'

const status = (value: ConnectionStatus) => value

export const MOCK_APP_INFO: AppInfo = {
  applicationName: 'Yoeun Sokhon Pharmacy',
  shortName: 'Yoeun Sokhon',
  businessName: 'Yoeun Sokhon Pharmacy',
  description: 'Yoeun Sokhon Pharmacy — stock, sales and point-of-sale management.',
  supportEmail: 'support@stockpos.local',
  supportPhone: '012 000 111',
  website: 'https://stockpos.local',
  address: 'Phnom Penh, Cambodia',
  branding: {
    primaryColor: '#057351',
    secondaryColor: '#1f2937',
  },
  footer: {
    copyrightText: '© Yoeun Sokhon Pharmacy. All rights reserved.',
  },
  updatedAt: nowIso(),
}

export const MOCK_APP_CONFIG: AppConfig = {
  general: {
    defaultLandingPage: '/',
    defaultPageSize: 20,
    defaultRecordView: 'table',
    enableComments: false,
    enableSharing: false,
    enableExport: true,
    maxUploadSizeMb: 10,
  },
  localization: {
    ...DEFAULT_FORMAT_CONFIG,
    availableLanguages: [...DEFAULT_FORMAT_CONFIG.availableLanguages],
    locale: 'en-US',
  },
  email: {
    enabled: false,
    smtpHost: '',
    smtpPort: 587,
    username: '',
    password: '',
    encryption: 'tls',
    fromName: 'Yoeun Sokhon Pharmacy',
    fromEmail: 'no-reply@stockpos.local',
    timeoutSeconds: 15,
    connectionStatus: status('not_tested'),
  },
  telegram: {
    enabled: false,
    botDisplayName: 'Yoeun Sokhon Pharmacy',
    // Env-only secret: the UI shows a masked, read-only status value.
    botToken: '********',
    chatId: '',
    messageLanguage: 'en',
    passwordResetEnabled: true,
    paymentInvoiceNotifyEnabled: true,
    stockInquiryEnabled: true,
    connectionStatus: status('disabled'),
  },
  stock: {
    lowStockLevel: 5,
    trackExpiry: false,
    expiryAlert1Days: 90,
    expiryAlert2Days: 7,
    telegramExpiryAlertsEnabled: true,
  },
  notifications: {
    inAppEnabled: true,
    emailEnabled: false,
    telegramEnabled: false,
    deliveryRetries: 3,
    quietHoursEnabled: false,
    language: 'en',
    rules: [],
  },
  security: {
    sessionTimeoutMinutes: 120,
    maxLoginAttempts: 5,
    accountLockMinutes: 15,
    passwordExpiryDays: 180,
    requirePasswordChange: false,
    allowedUploadExtensions: ['jpg', 'jpeg', 'png', 'pdf'],
    auditRetentionDays: 365,
    passwordResetChannel: 'telegram',
    passwordResetCodeExpiryMinutes: 10,
    jwtAccessTokenMinutes: 30,
    jwtRefreshTokenDays: 14,
    frontendOnly: true,
  },
  system: {
    maintenanceMode: false,
    readOnlyMode: false,
    paginationDefault: 20,
    configurationVersion: '1.0.0-mock',
    environment: 'development',
    cacheStatus: 'healthy',
    backgroundJobStatus: 'idle',
  },
  updatedAt: nowIso(),
}

export const MOCK_STORAGE_PROVIDERS: StorageProvider[] = [
  {
    id: 'sp1',
    name: 'Local disk',
    type: 'local',
    active: true,
    isDefault: true,
    maxFileSizeMb: 10,
    allowedFileTypes: ['jpg', 'png', 'pdf'],
    accessMode: 'private',
    uploadPathPattern: '{collection}/{yyyy}/{mm}/{id}',
    connectionStatus: status('connected'),
    updatedAt: nowIso(),
  },
]

function mergeSection<T>(current: T, input: Partial<T>): T {
  return { ...current, ...input }
}

export function createMockAppInfoRepository(): AppInfoRepository {
  let info: AppInfo = structuredClone(MOCK_APP_INFO)
  return {
    get: () => mockLatency(structuredClone(info)),
    update: async (input) => {
      info = { ...info, ...structuredClone(input), updatedAt: nowIso() }
      return structuredClone(info)
    },
    reset: async () => {
      info = structuredClone(MOCK_APP_INFO)
      return structuredClone(info)
    },
  }
}

export function createMockAppConfigRepository(): AppConfigRepository {
  let config: AppConfig = structuredClone(MOCK_APP_CONFIG)
  const connectionResult = (message: string) => mockLatency({
    status: 'connected' as ConnectionStatus,
    message,
  })
  return {
    get: () => mockLatency(structuredClone(config)),
    update: async (input) => {
      const next = structuredClone(config)
      if (input.general) next.general = mergeSection(next.general, input.general)
      if (input.localization) next.localization = mergeSection(next.localization, input.localization)
      if (input.email) next.email = mergeSection(next.email, input.email)
      if (input.telegram) next.telegram = mergeSection(next.telegram, input.telegram)
      if (input.stock) next.stock = mergeSection(next.stock, input.stock)
      if (input.notifications) next.notifications = mergeSection(next.notifications, input.notifications)
      if (input.security) next.security = mergeSection(next.security, input.security)
      if (input.system) next.system = mergeSection(next.system, input.system)
      next.updatedAt = nowIso()
      config = next
      return structuredClone(config)
    },
    resetAllData: async (): Promise<ResetAllDataResult> => mockLatency({
      message: 'Mock mode: data reset is a no-op.',
      requiresReauth: false,
    }),
    testEmailConnection: () => connectionResult('Mock SMTP connection is healthy.'),
    sendTestEmail: to => connectionResult(`Mock test email queued for ${to || 'demo@stockpos.local'}.`),
    testTelegramConnection: () => connectionResult('Mock Telegram bot is healthy.'),
    sendTestTelegramMessage: () => connectionResult('Mock Telegram message delivered.'),
  }
}

export function createMockStorageRepository(): StorageRepository {
  let providers = structuredClone(MOCK_STORAGE_PROVIDERS)
  const getById = (id: string): StorageProvider => {
    const found = providers.find(provider => provider.id === id)
    if (!found) throw new Error(`Storage provider ${id} not found`)
    return found
  }
  return {
    list: () => mockLatency(structuredClone(providers)),
    getById: id => mockLatency(structuredClone(getById(id))),
    create: async (input: CreateStorageProviderInput) => {
      const provider: StorageProvider = {
        ...structuredClone(input),
        id: createId('sp'),
        isDefault: Boolean(input.isDefault) && providers.length === 0,
        connectionStatus: 'not_tested',
        updatedAt: nowIso(),
      }
      providers.push(provider)
      return structuredClone(provider)
    },
    update: async (id: string, input: UpdateStorageProviderInput) => {
      const provider = getById(id)
      const updated: StorageProvider = { ...provider, ...structuredClone(input), updatedAt: nowIso() }
      providers = providers.map(row => row.id === id ? updated : row)
      return structuredClone(updated)
    },
    setDefault: async (id: string) => {
      providers = providers.map(row => ({ ...row, isDefault: row.id === id }))
      return structuredClone(getById(id))
    },
    setActive: async (id: string, active: boolean) => {
      const provider = { ...getById(id), active }
      providers = providers.map(row => row.id === id ? provider : row)
      return structuredClone(provider)
    },
    testConnection: id => mockLatency({
      status: 'connected' as ConnectionStatus,
      message: `Mock connection for ${getById(id).name} is healthy.`,
    }),
    remove: async (id: string) => {
      providers = providers.filter(provider => provider.id !== id)
      await mockLatency(undefined)
    },
  }
}