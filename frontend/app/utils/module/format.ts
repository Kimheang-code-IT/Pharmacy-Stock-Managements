/** Shared display formatting for data tables, strips, and badges. */

import { formatDate } from '~/utils/format/format-service'

type Translate = (key: string) => string
type TranslateExists = (key: string) => boolean

/**
 * Compact day cell via System Settings date format.
 * Pass `fallback` explicitly when a page needs `''` instead of `—`.
 */
export function shortDay(value: unknown, fallback = '—') {
  return formatDate(value, fallback)
}

/** Select items for status constants, using `app.reportCatalog.statuses.*` when present. */
export function labeledStatusOptions(
  values: readonly string[],
  t: Translate,
  te: TranslateExists,
) {
  return values.map((value) => {
    const slug = value.toLowerCase().replaceAll(' ', '_')
    const key = `app.reportCatalog.statuses.${slug}`
    return {
      label: te(key) ? String(t(key)) : value.replaceAll('_', ' '),
      value,
    }
  })
}

/** Title-cased label for UPPER_SNAKE codes (e.g. `CUSTOMER_INVOICE` → `Customer Invoice`). */
export function codeTitle(value: unknown) {
  return String(value ?? '')
    .replaceAll('_', ' ')
    .toLowerCase()
    .replace(/\b\w/g, ch => ch.toUpperCase())
}
