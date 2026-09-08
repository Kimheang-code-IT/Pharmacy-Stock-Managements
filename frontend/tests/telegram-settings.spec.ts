import { describe, expect, it } from 'vitest'
import { systemSettingsTabs } from '../app/config/settings-schemas'
import { MOCK_APP_CONFIG } from '../app/repositories/mock/settings'
import { applyAdminSettingsGroups, toAdminSettingsValues } from '../app/repositories/http/admin-settings'
import type { AppConfig } from '../app/types/stock-pos/settings'

describe('telegram settings', () => {
  const telegramFields = systemSettingsTabs
    .find(tab => tab.id === 'telegram')
    ?.sections.flatMap(section => section.fields) ?? []

  it('configures the Stock & POS password-reset Telegram bot connection', () => {
    const keys = telegramFields.map(field => field.key)
    expect(keys).toContain('telegram.enabled')
    expect(keys).toContain('telegram.botToken')
    expect(keys).toContain('telegram.chatId')
    expect(keys).toContain('__telegramConnection')
  })

  it('exposes the Phase 8 Telegram feature toggles', () => {
    const byKey = new Map(telegramFields.map(field => [field.key, field]))
    expect(byKey.get('telegram.passwordResetEnabled')?.type).toBe('boolean')
    expect(byKey.get('telegram.paymentInvoiceNotifyEnabled')?.type).toBe('boolean')
    expect(byKey.get('telegram.stockInquiryEnabled')?.type).toBe('boolean')
  })

  it('never exposes an editable bot token input (env-only secret)', () => {
    const tokenField = telegramFields.find(field => field.key === 'telegram.botToken')
    expect(tokenField).toBeDefined()
    expect(tokenField?.type).not.toBe('secret')
    expect(tokenField?.readOnly).toBe(true)
  })

  it('does not expose legacy rental notification settings', () => {
    const keys = telegramFields.map(field => field.key)
    expect(keys).not.toContain('telegram.notifyNewRental')
    expect(keys).not.toContain('telegram.deadlineReminderEnabled')
    expect(keys).not.toContain('telegram.deadlineReminderDuration')
    expect(keys).not.toContain('telegram.userAccess')
  })

  it('keeps the mock Telegram config free of rental/motorcycle state', () => {
    const telegram = MOCK_APP_CONFIG.telegram as Record<string, unknown>
    for (const key of Object.keys(telegram)) {
      expect(key.toLowerCase()).not.toContain('rental')
      expect(key.toLowerCase()).not.toContain('motorcycle')
    }
    expect(telegram.passwordResetEnabled).toBe(true)
    expect(telegram.paymentInvoiceNotifyEnabled).toBe(true)
    expect(telegram.stockInquiryEnabled).toBe(true)
  })
})

describe('stock settings (spec section 3.6)', () => {
  const stockTab = systemSettingsTabs.find(tab => tab.id === 'stock')
  const stockFields = stockTab?.sections.flatMap(section => section.fields) ?? []

  it('has a Stock tab with the two expiry-alert lead times', () => {
    expect(stockTab).toBeDefined()
    const byKey = new Map(stockFields.map(field => [field.key, field]))
    expect(byKey.get('stock.expiryAlert1Days')?.type).toBe('number')
    expect(byKey.get('stock.expiryAlert2Days')?.type).toBe('number')
  })

  it('toggles Telegram expiry alerts from the Stock tab', () => {
    const byKey = new Map(stockFields.map(field => [field.key, field]))
    expect(byKey.get('stock.telegramExpiryAlertsEnabled')?.type).toBe('boolean')
  })

  it('mock defaults match the spec examples (90 / 7, alerts on)', () => {
    expect(MOCK_APP_CONFIG.stock.expiryAlert1Days).toBe(90)
    expect(MOCK_APP_CONFIG.stock.expiryAlert2Days).toBe(7)
    expect(MOCK_APP_CONFIG.stock.telegramExpiryAlertsEnabled).toBe(true)
  })
})

describe('security settings', () => {
  const securityFields = systemSettingsTabs
    .find(tab => tab.id === 'security')
    ?.sections.flatMap(section => section.fields) ?? []

  it('keeps password-reset delivery on Telegram with a code expiry window', () => {
    const byKey = new Map(securityFields.map(field => [field.key, field]))
    const channel = byKey.get('security.passwordResetChannel')
    expect(channel?.type).toBe('select')
    expect(channel?.options?.map(option => option.value)).toEqual(['telegram'])
    expect(byKey.has('security.passwordResetCodeExpiryMinutes')).toBe(true)
  })
})

describe('admin settings mapping (PATCH /api/v1/admin/settings)', () => {
  const base = structuredClone(MOCK_APP_CONFIG) as AppConfig

  it('maps the Stock tab lead times and expiry toggle to backend groups', () => {
    const values = toAdminSettingsValues({
      stock: { ...base.stock, expiryAlert1Days: 60, expiryAlert2Days: 3, telegramExpiryAlertsEnabled: false },
    })
    expect(values).toEqual({
      stock: { expiry_alert_1_days: 60, expiry_alert_2_days: 3 },
      telegram: { expiry_alerts_enabled: false },
    })
  })

  it('maps the Telegram feature toggles to backend keys', () => {
    const values = toAdminSettingsValues({
      telegram: { ...base.telegram, passwordResetEnabled: false, paymentInvoiceNotifyEnabled: false, stockInquiryEnabled: false },
    })
    expect(values).toEqual({
      telegram: {
        enable_password_reset: false,
        payment_invoice_notify_enabled: false,
        stock_inquiry_enabled: false,
      },
    })
  })

  it('never sends the Telegram bot token (env-only secret)', () => {
    const values = toAdminSettingsValues(base) as Record<string, Record<string, unknown>>
    expect(values.telegram?.bot_token).toBeUndefined()
    expect(JSON.stringify(values)).not.toContain('bot_token')
  })

  it('applies returned backend groups back onto the form model', () => {
    const next = applyAdminSettingsGroups(base, {
      stock: { expiry_alert_1_days: 45, expiry_alert_2_days: 5 },
      telegram: { enable_password_reset: false, expiry_alerts_enabled: false },
    })
    expect(next.stock.expiryAlert1Days).toBe(45)
    expect(next.stock.expiryAlert2Days).toBe(5)
    expect(next.stock.telegramExpiryAlertsEnabled).toBe(false)
    expect(next.telegram.passwordResetEnabled).toBe(false)
    // Unmapped sections are untouched.
    expect(next.localization).toEqual(base.localization)
  })

  it('returns an empty patch when no mappable sections change', () => {
    expect(toAdminSettingsValues({ localization: { ...base.localization } })).toEqual({})
  })
})
