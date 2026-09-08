import {
  CalendarDate,
  CalendarDateTime,
  parseDate,
  parseDateTime,
} from '@internationalized/date'
import type { DateValue } from '@internationalized/date'

export type DatePickerGranularity = 'day' | 'hour' | 'minute' | 'second'

/** Anchor popover to input start (left), not centered on screen. */
export const datePickerPopoverContent = {
  side: 'bottom' as const,
  align: 'start' as const,
  sideOffset: 4,
  alignOffset: 0,
  collisionPadding: 8,
}

export function isDateTimeGranularity(granularity: DatePickerGranularity) {
  return granularity !== 'day'
}

export function parsePickerValue(
  value?: string | null,
  isDateTime = false,
): DateValue | undefined {
  if (!value) return undefined
  try {
    if (isDateTime) {
      const normalized = value.includes('T')
        ? value.slice(0, 16)
        : `${value.slice(0, 10)}T00:00`
      return parseDateTime(normalized)
    }
    return parseDate(value.slice(0, 10))
  }
  catch {
    return undefined
  }
}

export function serializePickerValue(value?: DateValue | null): string {
  if (!value) return ''
  if ('hour' in value) {
    const dt = value as CalendarDateTime
    const hh = String(dt.hour).padStart(2, '0')
    const mm = String(dt.minute).padStart(2, '0')
    return `${dt.toString().slice(0, 10)}T${hh}:${mm}`
  }
  return value.toString()
}

export function toCalendarDate(value?: DateValue | null): CalendarDate | undefined {
  if (!value) return undefined
  return new CalendarDate(value.year, value.month, value.day)
}

export function mergeDateWithTime(
  date: CalendarDate,
  current?: DateValue | null,
  fallbackHour = 0,
  fallbackMinute = 0,
): DateValue {
  if (current && 'hour' in current) {
    return new CalendarDateTime(date.year, date.month, date.day, current.hour, current.minute)
  }
  return new CalendarDateTime(date.year, date.month, date.day, fallbackHour, fallbackMinute)
}

