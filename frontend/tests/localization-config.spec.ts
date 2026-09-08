import { describe, expect, it } from 'vitest'
import {
  isHour12TimeFormat,
  normalizeLocalization,
  timeFormatHasSeconds,
} from '../app/utils/format/localization-config'

describe('localization-config', () => {
  it('normalizes first day of week and locale defaults', () => {
    const config = normalizeLocalization({
      defaultLanguage: 'km',
      firstDayOfWeek: 0,
      dateFormat: 'DD/MM/YYYY',
      timeFormat: 'h:mm A',
    })

    expect(config.firstDayOfWeek).toBe(0)
    expect(config.locale).toBe('km-KH')
    expect(config.dateFormat).toBe('DD/MM/YYYY')
  })

  it('detects 12-hour and second-based time formats', () => {
    expect(isHour12TimeFormat('h:mm A')).toBe(true)
    expect(isHour12TimeFormat('HH:mm')).toBe(false)
    expect(timeFormatHasSeconds('HH:mm:ss')).toBe(true)
    expect(timeFormatHasSeconds('HH:mm')).toBe(false)
  })
})
