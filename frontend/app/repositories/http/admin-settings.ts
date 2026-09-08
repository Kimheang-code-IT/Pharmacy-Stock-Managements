import type { AppConfig } from '~/types/stock-pos/settings'

/**
 * Mapping between the frontend settings form model (AppConfig) and the
 * grouped backend settings payload served by `PATCH/GET /api/v1/admin/settings`
 * (`{ values: { <group>: { <key>: value } } }`).
 *
 * Only keys that exist in the backend `SETTING_GROUPS` catalog are mapped;
 * unknown keys would be rejected by the API. The Telegram bot token is
 * env-only (`TELEGRAM_BOT_TOKEN`) and is never sent or stored from the UI.
 */

export type AdminSettingsGroups = Record<string, Record<string, unknown>>

export function toAdminSettingsValues(input: Partial<AppConfig>): AdminSettingsGroups {
  const values: AdminSettingsGroups = {}

  const stock = input.stock
  if (stock) {
    const group: Record<string, unknown> = {}
    if (stock.expiryAlert1Days !== undefined) group.expiry_alert_1_days = stock.expiryAlert1Days
    if (stock.expiryAlert2Days !== undefined) group.expiry_alert_2_days = stock.expiryAlert2Days
    if (Object.keys(group).length > 0) values.stock = group
  }

  const telegram: Record<string, unknown> = {}
  const telegramInput = input.telegram
  if (telegramInput) {
    if (telegramInput.passwordResetEnabled !== undefined) telegram.enable_password_reset = telegramInput.passwordResetEnabled
    if (telegramInput.paymentInvoiceNotifyEnabled !== undefined) telegram.payment_invoice_notify_enabled = telegramInput.paymentInvoiceNotifyEnabled
    if (telegramInput.stockInquiryEnabled !== undefined) telegram.stock_inquiry_enabled = telegramInput.stockInquiryEnabled
  }
  // The expiry-alerts toggle lives on the Stock tab of the UI but is stored
  // under the telegram settings group (spec section 3.6).
  if (stock?.telegramExpiryAlertsEnabled !== undefined) {
    telegram.expiry_alerts_enabled = stock.telegramExpiryAlertsEnabled
  }
  if (Object.keys(telegram).length > 0) values.telegram = telegram

  return values
}

function asNumber(value: unknown, fallback: number): number {
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

function asBoolean(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback
}

/** Overlay backend settings groups onto a config model (returns a new object). */
export function applyAdminSettingsGroups(config: AppConfig, groups: AdminSettingsGroups): AppConfig {
  const next: AppConfig = {
    ...config,
    stock: { ...config.stock },
    telegram: { ...config.telegram },
  }

  const stock = groups.stock
  if (stock) {
    if (stock.expiry_alert_1_days !== undefined) next.stock.expiryAlert1Days = asNumber(stock.expiry_alert_1_days, next.stock.expiryAlert1Days)
    if (stock.expiry_alert_2_days !== undefined) next.stock.expiryAlert2Days = asNumber(stock.expiry_alert_2_days, next.stock.expiryAlert2Days)
  }

  const telegram = groups.telegram
  if (telegram) {
    if (telegram.enable_password_reset !== undefined) next.telegram.passwordResetEnabled = asBoolean(telegram.enable_password_reset, next.telegram.passwordResetEnabled)
    if (telegram.payment_invoice_notify_enabled !== undefined) next.telegram.paymentInvoiceNotifyEnabled = asBoolean(telegram.payment_invoice_notify_enabled, next.telegram.paymentInvoiceNotifyEnabled)
    if (telegram.stock_inquiry_enabled !== undefined) next.telegram.stockInquiryEnabled = asBoolean(telegram.stock_inquiry_enabled, next.telegram.stockInquiryEnabled)
    if (telegram.expiry_alerts_enabled !== undefined) next.stock.telegramExpiryAlertsEnabled = asBoolean(telegram.expiry_alerts_enabled, next.stock.telegramExpiryAlertsEnabled)
  }

  return next
}
