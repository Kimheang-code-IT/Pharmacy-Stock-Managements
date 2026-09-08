const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

export function isMutatingMethod(method?: string) {
  return MUTATING_METHODS.has(String(method || 'GET').toUpperCase())
}

/** Read a non-HttpOnly double-submit CSRF cookie set by the API. */
export function readBrowserCookie(name: string): string | null {
  if (!import.meta.client || !name) return null
  const prefix = `${encodeURIComponent(name)}=`
  const item = document.cookie.split('; ').find(cookie => cookie.startsWith(prefix))
  if (!item) return null
  try {
    return decodeURIComponent(item.slice(prefix.length))
  }
  catch {
    return null
  }
}

export function csrfRequestHeaders(
  method: string | undefined,
  cookieName: string,
  headerName: string,
): Record<string, string> {
  if (!isMutatingMethod(method)) return {}
  const token = readBrowserCookie(cookieName)
  return token ? { [headerName]: token } : {}
}
