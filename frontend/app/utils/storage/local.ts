/**
 * Universal safe wrappers for LocalStorage that prevent SSR crash errors.
 */
export const localStore = {
  get: <T = string>(key: string): T | null => {
    if (typeof window === 'undefined') return null
    try {
      const item = localStorage.getItem(key)
      if (!item) return null
      return JSON.parse(item) as T
    } catch {
      return localStorage.getItem(key) as unknown as T
    }
  },
  
  set: (key: string, value: unknown): void => {
    if (typeof window === 'undefined') return
    const storedValue = typeof value === 'string' ? value : JSON.stringify(value)
    localStorage.setItem(key, storedValue)
  },
  
  remove: (key: string): void => {
    if (typeof window === 'undefined') return
    localStorage.removeItem(key)
  }
}
