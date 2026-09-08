import type { AppConfigLocalization } from '~/types/stock-pos/settings'
import { DEFAULT_FORMAT_CONFIG } from '~/utils/format/format-service'

const LOCALE_BY_LANGUAGE: Record<string, string> = {
  en: 'en-US',
  km: 'km-KH',
}

function normalizeFirstDayOfWeek(value: unknown): 0 | 1 | 6 {
  const day = Number(value)
  if (day === 0 || day === 1 || day === 6) return day
  return DEFAULT_FORMAT_CONFIG.firstDayOfWeek
}

/** Normalize API/local settings into the shape used by format-service and pickers. */
export function normalizeLocalization(
  input?: Partial<AppConfigLocalization> | null,
): AppConfigLocalization {
  const merged = {
    ...DEFAULT_FORMAT_CONFIG,
    ...(input || {}),
  }

  const defaultLanguage = merged.defaultLanguage === 'km' ? 'km' : 'en'
  const locale = input?.locale
    ? String(merged.locale || LOCALE_BY_LANGUAGE[defaultLanguage] || 'en-US')
    : String(LOCALE_BY_LANGUAGE[defaultLanguage] || merged.locale || 'en-US')

  return {
    ...merged,
    defaultLanguage,
    locale,
    timezone: String(merged.timezone || DEFAULT_FORMAT_CONFIG.timezone),
    dateFormat: String(merged.dateFormat || DEFAULT_FORMAT_CONFIG.dateFormat),
    timeFormat: String(merged.timeFormat || DEFAULT_FORMAT_CONFIG.timeFormat),
    firstDayOfWeek: normalizeFirstDayOfWeek(merged.firstDayOfWeek),
    numberFormat: String(merged.numberFormat || DEFAULT_FORMAT_CONFIG.numberFormat),
    currency: String(merged.currency || DEFAULT_FORMAT_CONFIG.currency),
    availableLanguages: merged.availableLanguages?.length
      ? [...merged.availableLanguages]
      : [...DEFAULT_FORMAT_CONFIG.availableLanguages],
  }
}

export function isHour12TimeFormat(timeFormat: string): boolean {
  return String(timeFormat || '').toLowerCase().includes('a')
}

export function timeFormatHasSeconds(timeFormat: string): boolean {
  return String(timeFormat || '').includes('ss')
}
