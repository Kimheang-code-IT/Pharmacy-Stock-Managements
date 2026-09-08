const EXTERNAL_PROTOCOLS = new Set(['http:', 'https:'])
const IMAGE_DATA_URL = /^data:image\/(?:png|jpeg|webp|gif);base64,[a-z0-9+/=\s]+$/i
const FILE_DATA_URL = /^data:(?:application\/pdf|image\/(?:png|jpeg|webp|gif|svg\+xml)|text\/(?:plain|csv));base64,[a-z0-9+/=\s]+$/i

/** Return a browser-safe external URL, or null for executable/unsupported schemes. */
export function safeExternalUrl(value: unknown): string | null {
  const raw = typeof value === 'string' ? value.trim() : ''
  if (!raw) return null
  try {
    const parsed = new URL(raw)
    if (parsed.username || parsed.password) return null
    return EXTERNAL_PROTOCOLS.has(parsed.protocol) ? parsed.toString() : null
  }
  catch {
    return null
  }
}

/** Validate the configured backend origin before credentials are attached. */
export function safeApiBase(value: unknown, requireHttps = false): string | null {
  const url = safeExternalUrl(value)
  if (!url) return null
  const parsed = new URL(url)
  if (requireHttps && parsed.protocol !== 'https:') return null
  return parsed.toString().replace(/\/$/, '')
}

/** Blob, previewable data URLs, or http(s) — never javascript: or other schemes. */
export function safeFilePreviewUrl(value: unknown): string | null {
  const raw = typeof value === 'string' ? value.trim() : ''
  if (!raw) return null
  if (FILE_DATA_URL.test(raw)) return raw
  try {
    const parsed = new URL(raw)
    if (parsed.protocol === 'blob:') return parsed.toString()
  }
  catch {
    return null
  }
  return safeExternalUrl(raw)
}

/** Restrict editor/image sources to raster data, blob, or normal web URLs. */
export function safeImageSource(value: unknown): string | null {
  const raw = typeof value === 'string' ? value.trim() : ''
  if (!raw) return null
  if (IMAGE_DATA_URL.test(raw)) return raw
  if (raw.startsWith('blob:') && import.meta.client) return raw
  return safeExternalUrl(raw)
}

/** Resolve uploads against the API origin without ever forwarding auth cross-origin. */
export function sameOriginApiUrl(path: string, apiBase: string): string | null {
  try {
    const base = new URL(apiBase)
    const resolved = new URL(path, base)
    return resolved.origin === base.origin ? resolved.toString() : null
  }
  catch {
    return null
  }
}
