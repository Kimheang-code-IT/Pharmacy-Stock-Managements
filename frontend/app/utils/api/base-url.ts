import { safeApiBase } from '~/utils/security/url'

const AUTO_VALUES = new Set(['', 'auto'])
const SAME_ORIGIN_VALUES = new Set(['same-origin', 'same', '/'])

export interface ResolveApiBaseOptions {
  configured: string
  internalBase?: string
  requireHttps?: boolean
  /** Override client detection (tests). */
  client?: boolean
  /** Override window location (tests). */
  location?: Pick<Location, 'protocol' | 'hostname'> | Pick<Location, 'protocol' | 'hostname' | 'origin'>
}

function isAutoApiBase(configured: string): boolean {
  return AUTO_VALUES.has(String(configured || '').trim().toLowerCase())
}

function isSameOriginApiBase(configured: string): boolean {
  const value = String(configured || '').trim().toLowerCase()
  return SAME_ORIGIN_VALUES.has(value)
}

/**
 * Resolve the backend origin for API calls.
 *
 * - `same-origin` / empty: use the current page origin (Docker nginx proxies `/api`).
 * - `auto` (default in dev): current hostname with port 8000 for local split-stack dev.
 * - SSR and server-side jobs use `internalBase` instead.
 */
export function resolveApiBase(options: ResolveApiBaseOptions): string | null {
  const configured = String(options.configured || '').trim()
  const requireHttps = options.requireHttps ?? false

  const onClient = options.client ?? import.meta.client
  if (isSameOriginApiBase(configured)) {
    if (onClient) {
      const location = options.location ?? (typeof window !== 'undefined' ? window.location : null)
      if (location) {
        const origin = 'origin' in location && location.origin
          ? location.origin
          : `${location.protocol}//${location.hostname}`
        return safeApiBase(origin, requireHttps)
      }
    }
    const internal = String(options.internalBase || 'http://127.0.0.1:8000').trim()
    return safeApiBase(internal, requireHttps)
  }

  if (!isAutoApiBase(configured)) {
    return safeApiBase(configured, requireHttps)
  }

  if (onClient) {
    const location = options.location ?? (typeof window !== 'undefined' ? window.location : null)
    if (location) {
      const candidate = `${location.protocol}//${location.hostname}:8000`
      return safeApiBase(candidate, requireHttps)
    }
  }

  const internal = String(options.internalBase || 'http://127.0.0.1:8000').trim()
  return safeApiBase(internal, requireHttps)
}

export { isAutoApiBase, isSameOriginApiBase }
