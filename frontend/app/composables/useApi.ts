import { useAuthStore } from '~/stores/auth'
import { ref } from 'vue'
import type { TableQueryParams } from '~/types/api'
import { compactQuery } from '~/utils/api/query'
import { normalizeApiError } from '~/utils/api/errors'
import { getAccessToken, getRefreshToken, setAccessToken } from '~/utils/auth/tokens'
import { createAuthRefresher } from '~/utils/api/auth-refresher'
import { isAutoApiBase, isSameOriginApiBase, resolveApiBase } from '~/utils/api/base-url'
import { useAccessAlert } from '~/composables/common/useAccessAlert'
import type { AuthUser } from '~/types/auth-user'
import { ApiEndpoints } from '~/utils/constants/api-endpoints'

type ApiRequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'
  headers?: Record<string, string>
  body?: Record<string, unknown> | BodyInit | null
  query?: object | TableQueryParams
  suppressErrorToast?: boolean
  suppressAccessAlert?: boolean
  requestKey?: string
  cancelPrevious?: boolean
  /** Requests that must never trigger refresh/retry (login, refresh itself). */
  isAuthRequest?: boolean
}

type ApiErrorPayload = {
  message?: string
}

type ApiFetchError = Error & {
  name: string
  statusCode?: number
  data?: ApiErrorPayload
}

// Shared across every useApi() consumer so a later request can cancel an older
// request even when composables created separate useApi instances.
const requestControllers = new Map<string, AbortController>()
let authMeRefreshPromise: Promise<void> | null = null

function refreshCurrentUserAfterForbidden(baseURL: string, timeout: number): Promise<void> {
  if (authMeRefreshPromise) return authMeRefreshPromise
  authMeRefreshPromise = (async () => {
    const token = getAccessToken()
    if (!token) return
    try {
      const response = await $fetch<{ data?: AuthUser }>(ApiEndpoints.AUTH_ME, {
        baseURL,
        method: 'GET',
        timeout,
        credentials: 'omit',
        headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
      })
      if (response?.data) useAuthStore().login(response.data)
    }
    catch {
      // Keep the original 403 as the user-facing result.
    }
  })().finally(() => {
    authMeRefreshPromise = null
  })
  return authMeRefreshPromise
}

/**
 * Normalize any thrown request failure into a consistent error carrying
 * statusCode / code / message / fieldErrors parsed from the FastAPI payload.
 */
export function toNormalizedApiError(error: unknown): Error & { statusCode: number, code: string, fieldErrors: Record<string, string>, data?: unknown } {
  const fetchError = error as ApiFetchError
  const statusCode = fetchError?.statusCode || 500
  const normalized = normalizeApiError(fetchError?.data, statusCode)
  const output = new Error(normalized.message) as Error & { statusCode: number, code: string, fieldErrors: Record<string, string>, data?: unknown }
  output.statusCode = normalized.statusCode
  output.code = normalized.code
  output.message = normalized.message
  output.fieldErrors = normalized.fieldErrors
  output.data = fetchError?.data
  return output
}

export function useApi() {
  const toast = useToast()
  const { showPermissionDenied, showSessionExpired } = useAccessAlert()
  const { t } = useI18n()
  const route = useRoute()
  const config = useRuntimeConfig()
  const activeRequests = ref(0)
  const pending = computed(() => activeRequests.value > 0)
  const error = ref<string | null>(null)

  const configuredBase = String(config.public.apiBase || '')
  const requireSecureApi = import.meta.env.PROD
    && config.public.useMockData === false
    && !isAutoApiBase(configuredBase)
    && !isSameOriginApiBase(configuredBase)

  function getApiBase(): string {
    const resolved = resolveApiBase({
      configured: configuredBase,
      internalBase: import.meta.server ? String(config.apiInternalBase || '') : undefined,
      requireHttps: requireSecureApi,
    })
    if (!resolved) {
      throw new Error('Invalid API base URL. Production APIs must use HTTPS.')
    }
    return resolved
  }

  const bearerMode = config.public.authMode === 'bearer'

  // Single-flight refresh: concurrent 401s share one rotation request.
  const refresher = createAuthRefresher({
    refreshEndpoint: () => `${getApiBase()}/api/v1/auth/refresh`,
    timeoutMs: Number(config.public.apiTimeoutMs) || 30000,
    getRefreshToken: () => getRefreshToken(),
    setAccessToken: token => setAccessToken(token),
    onSessionExpired: () => handleSessionFailure(),
  })

  function getRequestKey(url: string, options: ApiRequestOptions): string {
    return options.requestKey || `${options.method || 'GET'}:${url}`
  }

  function cancelRequest(key: string) {
    const controller = requestControllers.get(key)
    if (controller) {
      controller.abort()
      requestControllers.delete(key)
    }
  }

  async function rotateRefreshToken(): Promise<boolean> {
    return refresher.rotate()
  }

  function handleSessionFailure() {
    const authStore = useAuthStore()
    authStore.clearSession()
    if (!optionsSuppressAccessAlert()) {
      showSessionExpired()
      void navigateTo('/auth/login')
    }
  }

  // Mutable per-call flag access for the retry path.
  let currentSuppressAccessAlert = false
  function optionsSuppressAccessAlert() {
    return currentSuppressAccessAlert
  }

  const fetch = async <T>(url: string, options: ApiRequestOptions = {}) => {
    const baseURL = getApiBase()
    if (!sameOriginApiUrl(url, baseURL)) {
      throw new Error('API requests must use the configured API origin')
    }
    const requestKey = getRequestKey(url, options)
    const shouldCancelPrevious = options.cancelPrevious !== false

    if (shouldCancelPrevious) {
      cancelRequest(requestKey)
    }

    currentSuppressAccessAlert = Boolean(options.suppressAccessAlert)

    const execute = async () => {
      const controller = new AbortController()
      requestControllers.set(requestKey, controller)

      const method = options.method || 'GET'
      const headers: Record<string, string> = {
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        ...options.headers,
      }
      if (bearerMode) {
        const accessToken = getAccessToken()
        if (accessToken) headers.Authorization = `Bearer ${accessToken}`
      }

      try {
        activeRequests.value += 1
        error.value = null
        return await $fetch<T>(url, {
          baseURL,
          ...options,
          method,
          query: compactQuery(options.query),
          signal: controller.signal,
          timeout: Number(config.public.apiTimeoutMs) || 30000,
          credentials: 'omit',
          headers,
          async onResponseError({ response }) {
            if (response.status === 401) {
              return
            }

            if (response.status === 403) {
              handledAccessError = true
              await refreshCurrentUserAfterForbidden(baseURL, Number(config.public.apiTimeoutMs) || 30000)
              if (!options.suppressAccessAlert) {
                showPermissionDenied({
                  requestedPath: route.fullPath,
                  description: response._data?.detail?.message || response._data?.message,
                })
              }
              return
            }

            if (!options.suppressErrorToast) {
              const normalized = normalizeApiError(response._data, response.status)
              toast.add({
                title: t('api.errorTitle', { status: response.status }),
                description: normalized.message || t('api.somethingWentWrong'),
                color: 'error'
              })
            }
          }
        })
      }
      catch (err: unknown) {
        const fetchError = err as ApiFetchError
        if (fetchError.name === 'AbortError') {
          return Promise.reject(err)
        }

        error.value = fetchError?.message || t('api.requestFailed')

        if (
          fetchError.name === 'FetchError'
          && !handledAccessError
          && !options.suppressErrorToast
          && fetchError.statusCode !== 401
          && (fetchError.statusCode == null || fetchError.statusCode < 400)
        ) {
          toast.add({
            title: t('api.connectionErrorTitle'),
            description: t('api.connectionErrorDescription'),
            color: 'error'
          })
        }

        throw err
      }
      finally {
        if (requestControllers.get(requestKey) === controller) {
          requestControllers.delete(requestKey)
        }
        activeRequests.value = Math.max(0, activeRequests.value - 1)
      }
    }

    let handledAccessError = false

    const runWithAuth = async (): Promise<T> => {
      try {
        return await execute()
      }
      catch (err: unknown) {
        const fetchError = err as ApiFetchError
        const isAuthEndpoint = options.isAuthRequest
          || String(url).includes('/auth/login')
          || String(url).includes('/auth/refresh')
          || String(url).includes('/auth/forgot-password')
        if (fetchError.statusCode !== 401 || isAuthEndpoint || !bearerMode) {
          throw err
        }

        const hasSessionToken = Boolean(getAccessToken() || getRefreshToken())
        if (!hasSessionToken) {
          if (useAuthStore().user) handleSessionFailure()
          throw err
        }

        // One refresh for all concurrent 401s, then exactly one retry.
        const rotated = await rotateRefreshToken()
        if (!rotated) {
          // The refresher already clears the failed session exactly once.
          throw err
        }
        try {
          return await execute()
        }
        catch (retryError: unknown) {
          const retryStatus = (retryError as ApiFetchError)?.statusCode
          if (retryStatus === 401) {
            handleSessionFailure()
          }
          throw retryError
        }
      }
    }

    return runWithAuth()
  }

  return {
    pending,
    error,
    cancelRequest,
    get: <T>(url: string, opt?: ApiRequestOptions) => fetch<T>(url, { method: 'GET', ...opt }),
    post: <T>(url: string, body: ApiRequestOptions['body'], opt?: ApiRequestOptions) => fetch<T>(url, { method: 'POST', body, ...opt }),
    put: <T>(url: string, body: ApiRequestOptions['body'], opt?: ApiRequestOptions) => fetch<T>(url, { method: 'PUT', body, ...opt }),
    patch: <T>(url: string, body: ApiRequestOptions['body'], opt?: ApiRequestOptions) => fetch<T>(url, { method: 'PATCH', body, ...opt }),
    delete: <T>(url: string, opt?: ApiRequestOptions) => fetch<T>(url, { method: 'DELETE', ...opt }),
    request: fetch,
  }
}

