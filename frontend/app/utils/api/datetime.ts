/**
 * Deliberate datetime-local → ISO conversion for API payloads.
 *
 * The browser parses `YYYY-MM-DDTHH:mm` as local wall time; we re-emit the same
 * wall clock with the local UTC offset (e.g. `2026-09-01T08:00:00+07:00`) so the
 * backend stores the absolute instant the user selected.
 */

const OFFSET_PATTERN = /[Zz]$|[+-]\d{2}:?\d{2}$/

export function toIsoZoned(value: string | null | undefined): string | null {
  if (!value) return null
  if (OFFSET_PATTERN.test(value)) return value
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  const pad = (n: number) => String(n).padStart(2, '0')
  const local = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  const offsetMinutes = -date.getTimezoneOffset()
  const sign = offsetMinutes >= 0 ? '+' : '-'
  const abs = Math.abs(offsetMinutes)
  return `${local}${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`
}

export function toIsoZonedOrNow(value?: string | null): string {
  return toIsoZoned(value) || new Date().toISOString()
}
