import { describe, expect, it } from 'vitest'
import { resolveApiBase } from '../app/utils/api/base-url'

describe('resolveApiBase', () => {
  it('uses explicit configured API base', () => {
    expect(resolveApiBase({
      configured: 'http://localhost:8000',
      client: false,
    })).toBe('http://localhost:8000')
  })

  it('derives LAN API base from the page hostname in auto mode', () => {
    expect(resolveApiBase({
      configured: 'auto',
      client: true,
      location: { protocol: 'http:', hostname: '192.168.1.42' },
    })).toBe('http://192.168.1.42:8000')
  })

  it('uses internal base for SSR when auto mode is enabled', () => {
    expect(resolveApiBase({
      configured: 'auto',
      client: false,
      internalBase: 'http://api:8000',
    })).toBe('http://api:8000')
  })

  it('uses page origin in same-origin mode', () => {
    expect(resolveApiBase({
      configured: 'same-origin',
      client: true,
      location: { protocol: 'http:', hostname: 'localhost' },
    })).toBe('http://localhost')
  })
})
