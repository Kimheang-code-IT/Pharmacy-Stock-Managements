import type { AppConfigLocalization } from '~/types/stock-pos/settings'

/** Defaults aligned with mock settings seed and System Settings → Localization. */
export const DEFAULT_FORMAT_CONFIG: AppConfigLocalization = {
  defaultLanguage: 'en',
  availableLanguages: ['en', 'km'],
  timezone: 'Asia/Phnom_Penh',
  dateFormat: 'YYYY-MM-DD',
  timeFormat: 'HH:mm',
  firstDayOfWeek: 1,
  numberFormat: '1,234.56',
  currency: 'USD',
  locale: 'en-US',
}

const NUMBER_FORMAT_LOCALES: Record<string, string> = {
  '1,234.56': 'en-US',
  '1.234,56': 'de-DE',
  '1 234,56': 'fr-FR',
}

let activeConfig: AppConfigLocalization = {
  ...DEFAULT_FORMAT_CONFIG,
  availableLanguages: [...DEFAULT_FORMAT_CONFIG.availableLanguages],
}

export function configureFormats(next: Partial<AppConfigLocalization>) {
  activeConfig = {
    ...activeConfig,
    ...next,
    availableLanguages: next.availableLanguages?.length
      ? [...next.availableLanguages]
      : activeConfig.availableLanguages,
  }
}

export function getFormatConfig(): Readonly<AppConfigLocalization> {
  return activeConfig
}

function numberLocale() {
  return NUMBER_FORMAT_LOCALES[activeConfig.numberFormat] || activeConfig.locale
}

function validDate(value: unknown): Date | null {
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value
  if (value == null || value === '') return null
  const text = normalizeTimestampInput(String(value))
  const date = new Date(text)
  return Number.isNaN(date.getTime()) ? null : date
}

/** Normalize legacy `YYYY-MM-DD HH:mm` stamps to ISO for parsing. */
export function normalizeTimestampInput(text: string) {
  const trimmed = text.trim()
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(trimmed)) return trimmed.replace(' ', 'T')
  return trimmed
}

function dateOnlyParts(value: unknown): { year: string, month: string, day: string } | null {
  const text = normalizeTimestampInput(String(value || ''))
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:$|T)/)
  if (!match || text.includes('T')) return null
  return { year: match[1]!, month: match[2]!, day: match[3]! }
}

function configuredDateParts(date: Date, timeZone: string) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date)
  const read = (type: Intl.DateTimeFormatPartTypes) => parts.find(part => part.type === type)?.value || ''
  return { year: read('year'), month: read('month'), day: read('day') }
}

function formatPattern(
  parts: { year: string, month: string, day: string },
  pattern: string,
  locale: string,
) {
  if (pattern === 'DD/MM/YYYY') return `${parts.day}/${parts.month}/${parts.year}`
  if (pattern === 'MM/DD/YYYY') return `${parts.month}/${parts.day}/${parts.year}`
  if (pattern === 'DD-MM-YYYY') return `${parts.day}-${parts.month}-${parts.year}`
  if (pattern === 'D MMM YYYY') {
    const safe = new Date(Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day), 12))
    return new Intl.DateTimeFormat(locale, {
      timeZone: 'UTC',
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    }).format(safe)
  }
  return `${parts.year}-${parts.month}-${parts.day}`
}

export function formatDate(value: unknown, fallback = '—') {
  const rawParts = dateOnlyParts(value)
  const date = rawParts ? null : validDate(value)
  if (!rawParts && !date) return fallback
  try {
    const parts = rawParts || configuredDateParts(date!, activeConfig.timezone)
    return formatPattern(parts, activeConfig.dateFormat, activeConfig.locale)
  }
  catch {
    return rawParts ? `${rawParts.year}-${rawParts.month}-${rawParts.day}` : String(value || fallback)
  }
}

export function formatTime(value: unknown, fallback = '—') {
  const date = validDate(value)
  if (!date) return fallback
  const showSeconds = activeConfig.timeFormat.includes('ss')
  const hour12 = activeConfig.timeFormat.toLowerCase().includes('a')
  try {
    return new Intl.DateTimeFormat(activeConfig.locale, {
      timeZone: activeConfig.timezone,
      hour: hour12 ? 'numeric' : '2-digit',
      minute: '2-digit',
      ...(showSeconds ? { second: '2-digit' as const } : {}),
      hour12,
    }).format(date)
  }
  catch {
    return String(value || fallback)
  }
}

export function formatDateTime(value: unknown, fallback = '—') {
  const date = validDate(value)
  if (!date) return fallback
  return `${formatDate(value, fallback)} ${formatTime(value, '')}`.trim()
}

export function formatDatePart(
  value: unknown,
  options: Intl.DateTimeFormatOptions,
  fallback = '—',
) {
  const date = validDate(value)
  if (!date) return fallback
  try {
    return new Intl.DateTimeFormat(activeConfig.locale, {
      ...options,
      timeZone: options.timeZone || activeConfig.timezone,
    }).format(date)
  }
  catch {
    return String(value || fallback)
  }
}

export function formatNumber(value: unknown, options: Intl.NumberFormatOptions = {}) {
  const number = Number(value)
  if (!Number.isFinite(number)) return String(value ?? '')
  try {
    return new Intl.NumberFormat(numberLocale(), options).format(number)
  }
  catch {
    return String(number)
  }
}

export function formatCurrency(value: unknown, currency = activeConfig.currency) {
  return formatNumber(value, { style: 'currency', currency })
}

/** Money display: record currency when provided, otherwise System Settings default. */
export function formatMoney(value: unknown, currency?: string) {
  const code = String(currency || activeConfig.currency || 'USD').trim() || activeConfig.currency
  try {
    return formatCurrency(value, code)
  }
  catch {
    const amount = Number(value)
    const safe = Number.isFinite(amount) ? amount : 0
    return `${code} ${formatNumber(safe, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }
}

export function formatCompact(value: unknown) {
  const number = Number(value)
  if (!Number.isFinite(number)) return String(value ?? '')
  try {
    return new Intl.NumberFormat(numberLocale(), {
      notation: 'compact',
      maximumFractionDigits: 1,
    }).format(number)
  }
  catch {
    if (Math.abs(number) >= 1000) {
      return `${(number / 1000).toFixed(number % 1000 === 0 ? 0 : 1)}k`
    }
    return String(number)
  }
}

export type RelativeTimeLabels = {
  justNow: string
  minuteAgo?: string
  minutesAgo: (n: number) => string
  hourAgo?: string
  hoursAgo: (n: number) => string
  dayAgo?: string
  daysAgo: (n: number) => string
}

/** ERPNext-style relative stamp; switches to absolute date after `absoluteAfterDays`. */
export function formatRelativeTime(
  value: unknown,
  labels: RelativeTimeLabels,
  options?: { absoluteAfterDays?: number, fallback?: string },
) {
  const fallback = options?.fallback ?? '—'
  const raw = String(value ?? '').trim()
  if (!raw) return fallback

  const parsed = validDate(raw)
  if (!parsed) return raw

  const seconds = Math.round((Date.now() - parsed.getTime()) / 1000)
  const abs = Math.abs(seconds)

  if (abs < 45) return labels.justNow

  if (abs < 3600) {
    const mins = Math.max(1, Math.round(abs / 60))
    if (mins === 1 && labels.minuteAgo) return labels.minuteAgo
    return labels.minutesAgo(mins)
  }

  if (abs < 86400) {
    const hours = Math.max(1, Math.round(abs / 3600))
    if (hours === 1 && labels.hourAgo) return labels.hourAgo
    return labels.hoursAgo(hours)
  }

  const days = Math.max(1, Math.round(abs / 86400))
  const absoluteAfter = options?.absoluteAfterDays ?? 7
  if (days >= absoluteAfter) return formatDate(parsed, fallback)

  if (days === 1 && labels.dayAgo) return labels.dayAgo
  return labels.daysAgo(days)
}

/** Format date parts for date-picker placeholders (calendar day, not timezone-shifted). */
export function formatDateParts(parts: { year: number, month: number, day: number }) {
  const yyyy = String(parts.year)
  const mm = String(parts.month).padStart(2, '0')
  const dd = String(parts.day).padStart(2, '0')
  return formatPattern({ year: yyyy, month: mm, day: dd }, activeConfig.dateFormat, activeConfig.locale)
}
