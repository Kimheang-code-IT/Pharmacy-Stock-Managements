/**
 * Client-only bearer token storage.
 *
 * Tokens live in sessionStorage (per tab) and are mirrored into module memory so
 * `useApi()` can attach the Authorization header without async storage reads.
 * Tokens never enter the readable `auth_user` cookie/localStorage profile.
 */

const ACCESS_KEY = 'stockpos:auth:access-token'
const REFRESH_KEY = 'stockpos:auth:refresh-token'

let memoryAccess: string | null = null
let memoryRefresh: string | null = null

function readSession(key: string): string | null {
  if (!import.meta.client) return null
  try {
    return sessionStorage.getItem(key)
  }
  catch {
    return null
  }
}

function writeSession(key: string, value: string | null) {
  if (!import.meta.client) return
  try {
    if (value) sessionStorage.setItem(key, value)
    else sessionStorage.removeItem(key)
  }
  catch {
    // Storage may be unavailable (private mode); memory mirror still works.
  }
}

export function getAccessToken(): string | null {
  if (memoryAccess === null) memoryAccess = readSession(ACCESS_KEY)
  return memoryAccess
}

export function getRefreshToken(): string | null {
  if (memoryRefresh === null) memoryRefresh = readSession(REFRESH_KEY)
  return memoryRefresh
}

export function setTokens(access: string | null, refresh: string | null) {
  memoryAccess = access
  memoryRefresh = refresh
  writeSession(ACCESS_KEY, access)
  writeSession(REFRESH_KEY, refresh)
}

export function setAccessToken(access: string | null) {
  memoryAccess = access
  writeSession(ACCESS_KEY, access)
}

export function clearTokens() {
  setTokens(null, null)
}

export function hasTokens(): boolean {
  return Boolean(getAccessToken() || getRefreshToken())
}

