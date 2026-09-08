import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { AuthUser } from '~/types/auth-user'
import { AUTH_STORAGE_KEY, compactAuthUser } from '~/utils/auth/session'
import { clearTokens, hasTokens } from '~/utils/auth/tokens'

export const useAuthStore = defineStore('auth', () => {
  const cookieUser = useCookie<AuthUser | null>('auth_user', {
    default: () => null,
    path: '/',
    sameSite: 'lax',
    secure: import.meta.env.PROD,
    maxAge: 60 * 60 * 24 * 30,
  })
  const storedUser = ref<AuthUser | null>(null)
  const user = computed(() => storedUser.value || cookieUser.value)
  const isLoggedIn = computed(() => {
    if (!user.value) return false
    // Bearer tokens live in sessionStorage; a stale profile cookie alone is not a session.
    if (import.meta.client) return hasTokens()
    return true
  })

  function persist(userData: AuthUser | null) {
    storedUser.value = userData
    cookieUser.value = userData ? compactAuthUser(userData) : null
    if (!import.meta.client) return
    if (userData) localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(userData))
    else localStorage.removeItem(AUTH_STORAGE_KEY)
  }

  function hydrateClient() {
    if (!import.meta.client) return
    try {
      const raw = localStorage.getItem(AUTH_STORAGE_KEY)
      const local = raw ? JSON.parse(raw) as AuthUser : null
      if (local?.email) {
        if (!hasTokens()) {
          localStorage.removeItem(AUTH_STORAGE_KEY)
          cookieUser.value = null
          storedUser.value = null
          return
        }
        persist(local)
        return
      }
    }
    catch {
      localStorage.removeItem(AUTH_STORAGE_KEY)
    }
    if (cookieUser.value?.email) {
      if (!hasTokens()) {
        cookieUser.value = null
        storedUser.value = null
        return
      }
      persist(cookieUser.value)
    }
  }

  function login(userData: AuthUser) {
    persist(userData)
  }

  function clearSession() {
    clearTokens()
    persist(null)
  }

  async function logout() {
    clearSession()
    await navigateTo('/auth/login')
  }

  /** True when bearer tokens exist client-side (display/hydration only). */
  function hasSessionTokens(): boolean {
    return import.meta.client && hasTokens()
  }

  /**
   * Frontend-only visibility check. Backend must still enforce authorization.
   * `permissions` is authoritative when present. `pageAccess` remains a
   * backwards-compatible fallback for older sessions.
   */
  function canAccessPage(pageId: string): boolean {
    const currentUser = user.value
    if (!currentUser) return false
    const access = currentUser.effectivePermissions ?? currentUser.permissions ?? currentUser.pageAccess
    if (!Array.isArray(access)) return false
    return access.includes('ALL_PAGES') || access.includes(pageId)
  }

  function updateUser(partial: Partial<AuthUser>) {
    if (!user.value) return
    const next = { ...user.value, ...partial }
    if ('avatar' in partial && partial.avatar == null) {
      delete next.avatar
    }
    persist(next)
  }

  return {
    user,
    isLoggedIn,
    login,
    hydrateClient,
    clearSession,
    logout,
    canAccessPage,
    updateUser,
    hasSessionTokens,
  }
})
