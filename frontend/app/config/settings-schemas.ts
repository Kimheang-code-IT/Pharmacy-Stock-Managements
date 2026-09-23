import type { DocumentTabSchema } from '~/types/stock-pos/common'
import {
  CURRENCY_OPTIONS,
  DATE_FORMAT_OPTIONS,
  LANDING_PAGE_OPTIONS,
  NUMBER_FORMAT_OPTIONS,
  PAGE_SIZE_OPTIONS,
  TIME_FORMAT_OPTIONS,
  TIMEZONE_OPTIONS,
} from '~/utils/constants/select-options'

/** App Info — flat form (no tabs UI when single tab). */
export const appInfoTabs: DocumentTabSchema[] = [
  {
    id: 'info',
    labelKey: 'core.pages.appInfo',
    sections: [
      {
        id: 'info',
        fields: [
          { key: 'applicationName', labelKey: 'core.settings.applicationName', type: 'text', required: true, colSpan: 2 },
          { key: 'description', labelKey: 'core.fields.description', type: 'textarea', colSpan: 2, rows: 3 },
          { key: 'supportEmail', labelKey: 'core.settings.supportEmail', type: 'text' },
          { key: 'supportPhone', labelKey: 'core.settings.supportPhone', type: 'text' },
          { key: 'branding.mainLogoUrl', labelKey: 'core.settings.logo', type: 'image' },
          { key: 'website', labelKey: 'core.settings.website', type: 'url' },
          { key: 'address', labelKey: 'core.settings.address', type: 'text' },
          { key: 'footer.copyrightText', labelKey: 'core.settings.copyright', type: 'text', colSpan: 2 },
          {
            key: 'branding.primaryColor',
            labelKey: 'core.settings.primaryColor',
            type: 'color',
          },
        ],
      },
    ],
  },
]

/** App Config tabs. */
export const appConfigTabs: DocumentTabSchema[] = [
  {
    id: 'general',
    labelKey: 'core.settings.tabs.general',
    sections: [
      {
        id: 'general',
        titleKey: 'core.settings.tabs.general',
        fields: [
          {
            key: 'general.defaultLandingPage',
            labelKey: 'core.settings.defaultLandingPage',
            type: 'select',
            options: LANDING_PAGE_OPTIONS,
          },
          {
            key: 'general.defaultPageSize',
            labelKey: 'core.settings.defaultPageSize',
            type: 'select',
            options: PAGE_SIZE_OPTIONS,
          },
          {
            key: 'general.defaultRecordView',
            labelKey: 'core.settings.defaultRecordView',
            type: 'select',
            options: [
              { label: 'Table', value: 'table' },
              { label: 'Kanban', value: 'kanban' },
            ],
          },
          { key: 'general.maxUploadSizeMb', labelKey: 'core.config.maxFileSizeMb', type: 'number' },
          { key: 'general.enableSharing', labelKey: 'core.config.feature.sharing', type: 'boolean' },
          { key: 'general.enableExport', labelKey: 'core.config.feature.export', type: 'boolean' },
        ],
      },
    ],
  },
  {
    id: 'localization',
    labelKey: 'core.settings.tabs.localization',
    sections: [
      {
        id: 'localization',
        titleKey: 'core.settings.tabs.localization',
        fields: [
          {
            key: 'localization.defaultLanguage',
            labelKey: 'core.settings.defaultLanguage',
            type: 'select',
            options: [
              { label: 'English', value: 'en' },
              { label: 'Khmer', value: 'km' },
            ],
          },
          {
            key: 'localization.timezone',
            labelKey: 'core.settings.timezone',
            type: 'select',
            options: TIMEZONE_OPTIONS,
          },
          {
            key: 'localization.dateFormat',
            labelKey: 'core.settings.dateFormat',
            type: 'select',
            options: DATE_FORMAT_OPTIONS,
          },
          {
            key: 'localization.timeFormat',
            labelKey: 'core.settings.timeFormat',
            type: 'select',
            options: TIME_FORMAT_OPTIONS,
          },
          {
            key: 'localization.numberFormat',
            labelKey: 'core.settings.numberFormat',
            type: 'select',
            options: NUMBER_FORMAT_OPTIONS,
          },
          {
            key: 'localization.currency',
            labelKey: 'core.settings.currency',
            type: 'select',
            options: CURRENCY_OPTIONS,
          },
        ],
      },
    ],
  },
  {
    id: 'email',
    labelKey: 'core.settings.tabs.email',
    sections: [
      {
        id: 'email',
        titleKey: 'core.settings.tabs.email',
        fields: [
          { key: 'email.enabled', labelKey: 'core.settings.enableEmail', type: 'boolean' },
          { key: 'email.smtpHost', labelKey: 'core.settings.smtpHost', type: 'text' },
          { key: 'email.smtpPort', labelKey: 'core.settings.smtpPort', type: 'number' },
          { key: 'email.username', labelKey: 'core.settings.username', type: 'text' },
          { key: 'email.password', labelKey: 'core.settings.password', type: 'secret' },
          {
            key: 'email.encryption',
            labelKey: 'core.settings.encryption',
            type: 'select',
            options: [
              { label: 'None', value: 'none' },
              { label: 'SSL', value: 'ssl' },
              { label: 'TLS', value: 'tls' },
              { label: 'STARTTLS', value: 'starttls' },
            ],
          },
          { key: 'email.fromName', labelKey: 'core.settings.fromName', type: 'text' },
          { key: 'email.fromEmail', labelKey: 'core.settings.fromEmail', type: 'text' },
          { key: 'email.replyToEmail', labelKey: 'core.settings.replyTo', type: 'text' },
        ],
      },
    ],
  },
  {
    id: 'stock',
    labelKey: 'core.settings.tabs.stock',
    sections: [
      {
        id: 'stock-alerts',
        titleKey: 'core.settings.stockAlertsTitle',
        fields: [
          { key: 'stock.expiryAlert1Days', labelKey: 'core.settings.expiryAlert1Days', type: 'number', helpKey: 'core.fieldHelp.expiryAlert1Days' },
          { key: 'stock.expiryAlert2Days', labelKey: 'core.settings.expiryAlert2Days', type: 'number', helpKey: 'core.fieldHelp.expiryAlert2Days' },
        ],
      },
      {
        id: 'stock-telegram-alerts',
        titleKey: 'core.settings.telegramAlertsTitle',
        fields: [
          { key: 'stock.telegramExpiryAlertsEnabled', labelKey: 'core.settings.enableExpiryAlerts', type: 'boolean', helpKey: 'core.fieldHelp.expiryAlertsToggle' },
        ],
      },
    ],
  },
  {
    id: 'telegram',
    labelKey: 'core.settings.tabs.telegram',
    sections: [
      {
        id: 'telegram',
        titleKey: 'core.settings.tabs.telegram',
        fields: [
          { key: 'telegram.enabled', labelKey: 'core.settings.enableTelegram', type: 'boolean' },
          { key: 'telegram.botToken', labelKey: 'core.settings.botToken', type: 'secret', helpKey: 'core.fieldHelp.botToken' },
          { key: 'telegram.chatId', labelKey: 'core.settings.chatId', type: 'text' },
          { key: 'telegram.messageLanguage', labelKey: 'core.settings.messageLanguage', type: 'select', options: [{ label: 'English', value: 'en' }, { label: 'ខ្មែរ', value: 'km' }] },
        ],
      },
      {
        id: 'telegram-notifications',
        titleKey: 'core.settings.telegramNotificationsTitle',
        fields: [
          { key: 'telegram.expiryAlertsEnabled', labelKey: 'core.settings.expiryNotifications', type: 'boolean' },
          { key: 'telegram.saleNotificationsEnabled', labelKey: 'core.settings.saleNotifications', type: 'boolean' },
          { key: 'telegram.purchaseNotificationsEnabled', labelKey: 'core.settings.purchaseNotifications', type: 'boolean' },
          { key: 'telegram.dailySummaryEnabled', labelKey: 'core.settings.dailySummary', type: 'boolean' },
          { key: 'telegram.dailySummaryTime', labelKey: 'core.settings.dailySummaryTime', type: 'text' },
          { key: 'telegram.notificationLanguage', labelKey: 'core.settings.notificationLanguage', type: 'select', options: [{ label: 'English', value: 'en' }, { label: 'ខ្មែរ', value: 'km' }] },
        ],
      },
    ],
  },
  {
    id: 'notifications',
    labelKey: 'core.settings.tabs.notifications',
    sections: [
      {
        id: 'notifications',
        titleKey: 'core.settings.tabs.notifications',
        fields: [
          { key: 'notifications.inAppEnabled', labelKey: 'core.settings.inApp', type: 'boolean' },
          { key: 'notifications.emailEnabled', labelKey: 'core.settings.emailChannel', type: 'boolean' },
          { key: 'notifications.telegramEnabled', labelKey: 'core.settings.telegramChannel', type: 'boolean' },
          { key: 'notifications.deliveryRetries', labelKey: 'core.settings.deliveryRetries', type: 'number' },
          {
            key: 'notifications.rules',
            labelKey: 'core.settings.eventRules',
            type: 'notification-rules',
            colSpan: 2,
          },
        ],
      },
    ],
  },
  {
    id: 'security',
    labelKey: 'core.settings.tabs.security',
    sections: [
      {
        id: 'security',
        titleKey: 'core.settings.tabs.security',
        fields: [
          { key: 'security.accountLockMinutes', labelKey: 'core.settings.accountLockMinutes', type: 'number' },
          { key: 'security.auditRetentionDays', labelKey: 'core.settings.auditRetentionDays', type: 'number' },
          { key: 'security.requirePasswordChange', labelKey: 'core.settings.requirePasswordChange', type: 'boolean' },
          {
            key: 'security.passwordResetChannel',
            labelKey: 'core.settings.passwordResetChannel',
            type: 'select',
            options: [{ label: 'Telegram', value: 'telegram' }],
          },
          { key: 'security.passwordResetCodeExpiryMinutes', labelKey: 'core.settings.passwordResetCodeExpiryMinutes', type: 'number' },
          { key: 'security.jwtRefreshTokenDays', labelKey: 'core.settings.jwtRefreshTokenDays', type: 'number' },
        ],
      },
    ],
  },
  {
    id: 'system',
    labelKey: 'core.settings.tabs.system',
    sections: [
      {
        id: 'system',
        titleKey: 'core.settings.tabs.system',
        fields: [
          { key: 'system.maintenanceMode', labelKey: 'core.settings.maintenanceMode', type: 'boolean' },
          { key: 'system.readOnlyMode', labelKey: 'core.settings.readOnlyMode', type: 'boolean' },
          {
            key: 'system.paginationDefault',
            labelKey: 'core.settings.paginationDefault',
            type: 'select',
            options: PAGE_SIZE_OPTIONS,
          },
          { key: 'system.configurationVersion', labelKey: 'core.settings.configurationVersion', type: 'text', readOnly: true },
          { key: 'system.environment', labelKey: 'core.settings.environment', type: 'text', readOnly: true },
          { key: 'system.cacheStatus', labelKey: 'core.settings.cacheStatus', type: 'text', readOnly: true },
          { key: 'system.backgroundJobStatus', labelKey: 'core.settings.jobStatus', type: 'text', readOnly: true },
        ],
      },
    ],
  },
]

const SYSTEM_SETTINGS_TAB_IDS = new Set(['localization', 'stock', 'telegram', 'security'])
const SETTINGS_FIELD_HELP: Record<string, string> = {
  'localization.timezone': 'core.fieldHelp.timezone',
  'localization.dateFormat': 'core.fieldHelp.dateFormat',
  'localization.timeFormat': 'core.fieldHelp.timeFormat',
  'localization.numberFormat': 'core.fieldHelp.numberFormat',
  'email.enabled': 'core.fieldHelp.enableEmail',
  'email.replyToEmail': 'core.fieldHelp.replyTo',
  'telegram.enabled': 'core.fieldHelp.enableTelegram',
  'telegram.botToken': 'core.fieldHelp.botToken',
  'telegram.passwordResetEnabled': 'core.fieldHelp.passwordResetEnabled',
  'telegram.paymentInvoiceNotifyEnabled': 'core.fieldHelp.paymentInvoiceNotify',
  'telegram.stockInquiryEnabled': 'core.fieldHelp.stockInquiry',
  'stock.expiryAlert1Days': 'core.fieldHelp.expiryAlert1Days',
  'stock.expiryAlert2Days': 'core.fieldHelp.expiryAlert2Days',
  'stock.telegramExpiryAlertsEnabled': 'core.fieldHelp.expiryAlertsToggle',
}

/** Administration system settings — Localization, Stock, Telegram, Security only. */
export const systemSettingsTabs: DocumentTabSchema[] = [
  ...appConfigTabs
    .filter(tab => SYSTEM_SETTINGS_TAB_IDS.has(tab.id))
    .map(tab => ({
      ...tab,
      sections: tab.sections.map(section => ({
        ...section,
        fields: section.fields.map(field => ({
          ...field,
          helpKey: field.helpKey || SETTINGS_FIELD_HELP[field.key],
        })),
      })),
    })),
  // Backup tab: standard settings form (same layout as Localization). The
  // run/test/history/restore actions live in the page header; `frequencyHours`
  // options are filled at runtime from the loaded config.
  {
    id: 'backup',
    labelKey: 'core.settings.tabs.backup',
    sections: [
      {
        id: 'backup-connection',
        titleKey: 'core.settings.backupConnection',
        fields: [
          {
            key: 'backup.sheetId',
            labelKey: 'core.settings.backupSheetId',
            type: 'text',
            helpKey: 'core.fieldHelp.backupSheetId',
            placeholderKey: 'core.settings.backupSheetIdPlaceholder',
          },
          {
            key: 'backup.serviceAccountJson',
            labelKey: 'core.settings.backupServiceAccount',
            type: 'textarea',
            colSpan: 2,
            helpKey: 'core.fieldHelp.backupServiceAccount',
            placeholderKey: 'core.settings.backupServiceAccountPlaceholder',
          },
        ],
      },
      {
        id: 'backup-schedule',
        titleKey: 'core.settings.backupSchedule',
        fields: [
          { key: 'backup.enabled', labelKey: 'core.settings.backupEnabled', type: 'boolean', helpKey: 'core.settings.backupEnabledHint' },
          { key: 'backup.frequencyHours', labelKey: 'core.settings.backupFrequency', type: 'select', options: [] },
          { key: 'backup.backupNewRecords', labelKey: 'core.settings.backupNewRecords', type: 'boolean' },
          { key: 'backup.backupChangedRecords', labelKey: 'core.settings.backupChangedRecords', type: 'boolean' },
          { key: 'backup.autoRetry', labelKey: 'core.settings.backupAutoRetry', type: 'boolean' },
          { key: 'backup.telegramNotify', labelKey: 'core.settings.backupTelegramNotify', type: 'boolean' },
        ],
      },
      {
        id: 'backup-status',
        titleKey: 'core.settings.backupStatus',
        fields: [
          { key: 'backup.lastSuccessAt', labelKey: 'core.settings.backupLastSuccess', type: 'text', readOnly: true },
          { key: 'backup.nextRunAt', labelKey: 'core.settings.backupNextRun', type: 'text', readOnly: true },
        ],
      },
    ],
  },
]

/** Storage is local disk on the API. No S3 / MinIO / Google Drive settings. */
export const storageSettingsTabs: DocumentTabSchema[] = []
