import { describe, expect, it, beforeEach } from 'vitest'
import {
  configureFormats,
  DEFAULT_FORMAT_CONFIG,
  formatCompact,
  formatDate,
  formatDateTime,
  formatMoney,
  formatNumber,
  formatRelativeTime,
  formatTime,
} from '../app/utils/format/format-service'

describe('format-service', () => {
  beforeEach(() => {
    configureFormats(DEFAULT_FORMAT_CONFIG)
  })

  it('formats dates from settings dateFormat', () => {
    configureFormats({ dateFormat: 'DD/MM/YYYY' })
    expect(formatDate('2026-08-20')).toBe('20/08/2026')
    expect(formatDate('2026-08-20T15:30:00')).toMatch(/20\/08\/2026/)
  })

  it('formats numbers from settings numberFormat locale', () => {
    configureFormats({ numberFormat: '1.234,56', locale: 'de-DE' })
    expect(formatNumber(1234.5)).toBe('1.234,5')
  })

  it('formats money with record currency and settings locale', () => {
    configureFormats({ currency: 'USD', locale: 'en-US', numberFormat: '1,234.56' })
    const formatted = formatMoney(1250, 'USD')
    expect(formatted).toMatch(/1,?250\.00/)
    expect(formatted).toMatch(/USD|\$/)
  })

  it('formats compact numbers', () => {
    configureFormats({ locale: 'en-US', numberFormat: '1,234.56' })
    expect(formatCompact(1500)).toMatch(/1\.5K|1,5K/i)
  })

  it('formats time using configured timezone and 24h pattern', () => {
    configureFormats({
      timezone: 'UTC',
      timeFormat: 'HH:mm',
      locale: 'en-US',
    })
    const label = formatTime('2026-08-20T14:30:00Z')
    expect(label).toMatch(/14:30|2:30/)
  })

  it('joins date and time for datetime values', () => {
    configureFormats({
      dateFormat: 'YYYY-MM-DD',
      timeFormat: 'HH:mm',
      timezone: 'UTC',
      locale: 'en-US',
    })
    const value = formatDateTime('2026-08-20T14:30:00Z')
    expect(value).toContain('2026-08-20')
    expect(value).toMatch(/14:30|2:30/)
  })

  it('relative time uses labels and falls back to absolute date', () => {
    const labels = {
      justNow: 'Just now',
      minutesAgo: (n: number) => `${n}m`,
      hoursAgo: (n: number) => `${n}h`,
      daysAgo: (n: number) => `${n}d`,
    }
    const recent = formatRelativeTime(new Date(Date.now() - 120_000).toISOString(), labels)
    expect(recent).toBe('2m')

    const old = formatRelativeTime('2020-01-15', labels, { absoluteAfterDays: 7 })
    expect(old).toBe('2020-01-15')
  })
})
