import { describe, expect, it, beforeEach } from 'vitest'
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  hasTokens,
  setAccessToken,
  setTokens,
} from '../app/utils/auth/tokens'

describe('token storage (server-side memory mirror)', () => {
  beforeEach(() => {
    clearTokens()
  })

  it('stores and retrieves both tokens', () => {
    setTokens('access-1', 'refresh-1')
    expect(getAccessToken()).toBe('access-1')
    expect(getRefreshToken()).toBe('refresh-1')
    expect(hasTokens()).toBe(true)
  })

  it('rotates only the access token', () => {
    setTokens('access-1', 'refresh-1')
    setAccessToken('access-2')
    expect(getAccessToken()).toBe('access-2')
    expect(getRefreshToken()).toBe('refresh-1')
  })

  it('clears both tokens', () => {
    setTokens('access-1', 'refresh-1')
    clearTokens()
    expect(getAccessToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
    expect(hasTokens()).toBe(false)
  })
})
