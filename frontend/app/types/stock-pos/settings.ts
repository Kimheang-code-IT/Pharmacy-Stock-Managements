export type ConnectionStatus =
  | 'not_tested'
  | 'testing'
  | 'connected'
  | 'failed'
  | 'disabled'

export type StorageProviderType = 'local'

export type EncryptionType = 'none' | 'ssl' | 'tls' | 'starttls'

export type NotificationChannel = 'in_app' | 'email' | 'telegram'

export type NotificationEvent =
  | 'password_reset_requested'
  | 'record_created'
  | 'record_assigned'
  | 'stage_changed'
  | 'record_overdue'
  | 'file_uploaded'

export type AppFontSize = 'sm' | 'md' | 'lg' | 'xl'

export interface AppBranding {
  mainLogoUrl?: string
  sidebarLogoUrl?: string
  faviconUrl?: string
  loginBackgroundUrl?: string
  /** System primary color (hex, e.g. #e8472a). */
  primaryColor: string
  secondaryColor: string
  /** @deprecated Per-user preference — use preferences store / user menu. */
  fontSize?: AppFontSize
}

export interface AppFooterInfo {
  copyrightText: string
  privacyPolicyUrl?: string
  termsUrl?: string
}

export interface AppInfo {
  applicationName: string
  shortName: string
  businessName: string
  description?: string
  supportEmail?: string
  supportPhone?: string
  website?: string
  address?: string
  branding: AppBranding
  footer: AppFooterInfo
  updatedAt: string
}

export interface EmailConfig {
  enabled: boolean
  smtpHost: string
  smtpPort: number
  username: string
  /** Masked in UI; never log plaintext. */
  password: string
  encryption: EncryptionType
  fromName: string
  fromEmail: string
  replyToEmail?: string
  timeoutSeconds: number
  connectionStatus: ConnectionStatus
  lastTestedAt?: string
  lastTestMessage?: string
}

/**
 * Telegram bot config (spec section 3.6).
 * The bot token is env-only (TELEGRAM_BOT_TOKEN): it is never editable in the
 * UI and is only surfaced masked / as connection status.
 */
export interface TelegramConfig {
  enabled: boolean
  botDisplayName: string
  botToken: string
  botUsername?: string
  chatId: string
  messageLanguage: 'en' | 'km'
  /** Enable Telegram password-reset code delivery. */
  passwordResetEnabled: boolean
  /** Enable plain-text payment / invoice notifications after settlement. */
  paymentInvoiceNotifyEnabled: boolean
  /** Enable the view-only stock inquiry bot (no mutations via Telegram). */
  stockInquiryEnabled: boolean
  connectionStatus: ConnectionStatus
  lastTestedAt?: string
  lastTestMessage?: string
}

/** Stock settings incl. the two Telegram expiry-alert lead times (spec 3.6). */
export interface AppConfigStock {
  lowStockLevel: number
  trackExpiry: boolean
  /** First expiry-alert lead time in days (e.g. 90). */
  expiryAlert1Days: number
  /** Second expiry-alert lead time in days (e.g. 7). */
  expiryAlert2Days: number
  /** Enable Telegram expiry-alert delivery (uses the two lead times). */
  telegramExpiryAlertsEnabled: boolean
}

export interface NotificationRule {
  id: string
  event: NotificationEvent
  channels: NotificationChannel[]
  enabled: boolean
}

export interface AppConfigGeneral {
  defaultLandingPage: string
  defaultPageSize: number
  defaultRecordView: 'table' | 'kanban'
  enableComments: boolean
  enableSharing: boolean
  enableExport: boolean
  maxUploadSizeMb: number
}

export interface AppConfigLocalization {
  defaultLanguage: 'en' | 'km'
  availableLanguages: Array<'en' | 'km'>
  timezone: string
  dateFormat: string
  timeFormat: string
  firstDayOfWeek: 0 | 1 | 6
  numberFormat: string
  currency: string
  locale: string
}

export interface AppConfigNotifications {
  inAppEnabled: boolean
  emailEnabled: boolean
  telegramEnabled: boolean
  deliveryRetries: number
  quietHoursEnabled: boolean
  quietHoursStart?: string
  quietHoursEnd?: string
  language: 'en' | 'km'
  rules: NotificationRule[]
}

export interface AppConfigSecurity {
  sessionTimeoutMinutes: number
  maxLoginAttempts: number
  accountLockMinutes: number
  passwordExpiryDays: number
  requirePasswordChange: boolean
  allowedUploadExtensions: string[]
  auditRetentionDays: number
  passwordResetChannel: 'telegram'
  passwordResetCodeExpiryMinutes: number
  jwtAccessTokenMinutes: number
  jwtRefreshTokenDays: number
  /** UI disclaimer: not enforced without backend. */
  frontendOnly: true
}

export interface AppConfigSystem {
  maintenanceMode: boolean
  readOnlyMode: boolean
  paginationDefault: number
  configurationVersion: string
  environment: 'development' | 'staging' | 'production'
  cacheStatus: 'healthy' | 'degraded' | 'unknown'
  backgroundJobStatus: 'idle' | 'running' | 'failed' | 'unknown'
}

export interface AppConfig {
  general: AppConfigGeneral
  localization: AppConfigLocalization
  email: EmailConfig
  telegram: TelegramConfig
  stock: AppConfigStock
  notifications: AppConfigNotifications
  security: AppConfigSecurity
  system: AppConfigSystem
  updatedAt: string
}

export interface StorageProvider {
  id: string
  name: string
  type: StorageProviderType
  active: boolean
  isDefault: boolean
  maxFileSizeMb: number
  allowedFileTypes: string[]
  accessMode: 'public' | 'private'
  uploadPathPattern: string
  connectionStatus: ConnectionStatus
  lastTestedAt?: string
  lastTestMessage?: string
  /** S3-compatible */
  endpoint?: string
  region?: string
  bucket?: string
  accessKey?: string
  secretKey?: string
  publicUrl?: string
  pathStyle?: boolean
  /** Google Drive */
  folderId?: string
  clientId?: string
  clientSecret?: string
  credentialStatus?: ConnectionStatus
  syncStatus?: ConnectionStatus
  syncSchedule?: string
  updatedAt: string
}

export type CreateStorageProviderInput = Omit<
  StorageProvider,
  'id' | 'updatedAt' | 'connectionStatus' | 'isDefault'
> & { isDefault?: boolean }

export type UpdateStorageProviderInput = Partial<CreateStorageProviderInput>
