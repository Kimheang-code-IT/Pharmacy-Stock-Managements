/**
 * Resolve a path or URL to an absolute URL for Open Graph / Twitter crawlers.
 * Relative paths (e.g. `/logo.png`) are ignored by Telegram, WhatsApp, Facebook, etc.
 *
 * Important: call `useRequestURL()` during setup (not lazily inside a computed
 * callback), or Nitro/Vercel SSR loses the request origin and og:image stays relative.
 */
export function useSeoAbsoluteUrl() {
  const config = useRuntimeConfig()
  // Must run synchronously in setup so the Nitro request event is available.
  const requestUrl = useRequestURL()

  function siteOrigin(): string {
    const configured = String(config.public.siteUrl || '').replace(/\/$/, '')
    if (configured) return configured
    return requestUrl.origin || ''
  }

  function absoluteUrl(pathOrUrl: string | undefined | null): string {
    const raw = String(pathOrUrl || '').trim()
    if (!raw) return ''
    if (/^https?:\/\//i.test(raw)) return raw

    const origin = siteOrigin()
    if (!origin) return raw

    const path = raw.startsWith('/') ? raw : `/${raw}`
    return `${origin}${path}`
  }

  function absolutePageUrl(path?: string): string {
    const origin = siteOrigin()
    if (path) {
      if (!origin) return path.startsWith('/') ? path : `/${path}`
      return `${origin}${path.startsWith('/') ? path : `/${path}`}`
    }
    if (origin) return `${origin}${requestUrl.pathname}${requestUrl.search}`
    return requestUrl.href
  }

  return {
    absoluteUrl,
    absolutePageUrl,
  }
}
