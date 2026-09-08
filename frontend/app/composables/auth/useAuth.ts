import type { AuthUser } from '~/types/auth-user'
import { ok } from '~/mocks/query'
import { MOCK_DEMO_EMAIL, MOCK_DEMO_PASSWORD, mockLoginUser } from '~/mocks/auth'
import { clearTokens, getAccessToken, hasTokens, setTokens } from '~/utils/auth/tokens'
import { ApiEndpoints } from '~/utils/constants/api-endpoints'

type LoginResult = { user: AuthUser }

interface AuthTokenPairResponse {
  accessToken: string
  refreshToken: string
  tokenType: string
  expiresIn: number
  refreshExpiresIn?: number
  user?: AuthUser
}

function useMockAuthMode(): boolean {
  try {
    return useRuntimeConfig().public.useMockData === true
  }
  catch {
    return false
  }
}

/**
 * HTTP auth operations against `/api/v1/auth/*`. In mock mode every operation
 * is answered locally with placeholder tokens and the seeded demo profile.
 */
export function useAuth() {
  const api = useApi()
  const authStore = useAuthStore()

  async function unwrap<T>(response: { data: T } | T): Promise<T> {
    if (response && typeof response === 'object' && 'data' in (response as object)) {
      return (response as { data: T }).data
    }
    return response as T
  }

  async function loginWithCredentials(email: string, password: string) {
    if (useMockAuthMode()) {
      const user = mockLoginUser(email, password)
      setTokens('mock-access-token', 'mock-refresh-token')
      return ok<LoginResult>({ user })
    }
    const payload = await unwrap<AuthTokenPairResponse>(await api.post<AuthTokenPairResponse | { data: AuthTokenPairResponse }>(
      ApiEndpoints.AUTH_LOGIN,
      { email, password },
      { isAuthRequest: true, suppressErrorToast: true },
    ))
    setTokens(payload.accessToken, payload.refreshToken)
    const user = payload.user
    if (!user) throw createError({ statusCode: 401, statusMessage: 'Invalid credentials' })
    return ok<LoginResult>({ user })
  }

  async function requestPasswordReset(email: string) {
    if (useMockAuthMode()) return ok({ sent: true, channel: 'telegram' as const })
    await api.post(ApiEndpoints.AUTH_FORGOT_PASSWORD, { email }, { isAuthRequest: true })
    return ok({ sent: true, channel: 'telegram' as const })
  }

  async function verifyPasswordResetCode(email: string, code: string) {
    if (useMockAuthMode()) return ok({ verified: true, resetToken: 'mock-reset-token' })
    const result = await unwrap<{ resetToken: string }>(await api.post<{ resetToken: string } | { data: { resetToken: string } }>(
      ApiEndpoints.AUTH_RESET_VERIFY,
      { email, code },
      { isAuthRequest: true, suppressErrorToast: true },
    ))
    return ok({ verified: true, resetToken: result.resetToken })
  }

  async function resendPasswordResetCode(email: string) {
    if (useMockAuthMode()) return ok({ sent: true, channel: 'telegram' as const })
    await api.post(ApiEndpoints.AUTH_RESET_RESEND, { email }, { isAuthRequest: true })
    return ok({ sent: true, channel: 'telegram' as const })
  }

  async function resetPasswordWithCode(input: {
    email: string
    resetToken?: string
    code?: string
    password: string
    passwordConfirmation: string
  }) {
    if (!useMockAuthMode()) {
      if (!input.resetToken) {
        throw createError({ statusCode: 400, statusMessage: 'Reset session expired. Verify the code again.' })
      }
    }
    if (input.password !== input.passwordConfirmation) {
      throw createError({ statusCode: 400, statusMessage: 'Passwords do not match' })
    }
    if (useMockAuthMode()) return ok({ reset: true })
    await api.post(ApiEndpoints.AUTH_RESET_PASSWORD, {
      email: input.email,
      resetToken: input.resetToken,
      newPassword: input.password,
    }, { isAuthRequest: true })
    return ok({ reset: true })
  }

  async function exchangePasswordResetHandoff(handoff: string) {
    if (useMockAuthMode()) return ok({ email: MOCK_DEMO_EMAIL, resetToken: 'mock-reset-token' })
    const result = await unwrap<{ email: string, resetToken: string }>(await api.post<{ email: string, resetToken: string } | { data: { email: string, resetToken: string } }>(
      ApiEndpoints.AUTH_RESET_HANDOFF,
      { handoff },
      { isAuthRequest: true, suppressErrorToast: true },
    ))
    return ok(result)
  }

  async function createTelegramLinkCode() {
    if (useMockAuthMode()) return ok({ code: 'MOCK-1234', expiresIn: 600 })
    const result = await unwrap<{ code: string, expiresIn: number }>(await api.post<{ code: string, expiresIn: number } | { data: { code: string, expiresIn: number } }>(
      ApiEndpoints.AUTH_TELEGRAM_LINK_CODE,
      {},
    ))
    return ok(result)
  }

  async function changePassword(input: {
    currentPassword: string
    password: string
    passwordConfirmation: string
  }) {
    const auth = useAuthStore()
    if (!auth.user) throw createError({ statusCode: 401, statusMessage: 'Not signed in' })
    if (input.password !== input.passwordConfirmation) {
      throw createError({ statusCode: 400, statusMessage: 'Passwords do not match' })
    }
    if (useMockAuthMode()) return ok({ changed: true })
    await api.post(ApiEndpoints.AUTH_CHANGE_PASSWORD, {
      currentPassword: input.currentPassword,
      newPassword: input.password,
    })
    return ok({ changed: true })
  }

  async function updateProfileAvatar(avatar: string) {
    const auth = useAuthStore()
    if (!auth.user) throw createError({ statusCode: 401, statusMessage: 'Not signed in' })
    if (!useMockAuthMode()) {
      await api.patch(ApiEndpoints.AUTH_PROFILE_AVATAR, { avatar })
    }
    auth.updateUser({ avatar })
    return ok({ avatar })
  }

  async function removeProfileAvatar() {
    const auth = useAuthStore()
    if (!auth.user) throw createError({ statusCode: 401, statusMessage: 'Not signed in' })
    if (!useMockAuthMode()) {
      await api.patch(ApiEndpoints.AUTH_PROFILE_AVATAR, { avatar: null })
    }
    auth.updateUser({ avatar: undefined })
    return ok({ removed: true })
  }

  async function logoutServer(refreshToken: string | null) {
    if (useMockAuthMode() || !refreshToken) return ok({ message: 'Logged out' })
    try {
      await api.post(ApiEndpoints.AUTH_LOGOUT, { refreshToken }, { isAuthRequest: true, suppressErrorToast: true, suppressAccessAlert: true })
    }
    catch {
      // Server logout is best-effort; client state is cleared regardless.
    }
    return ok({ message: 'Logged out' })
  }

  /** Refresh the stored user profile from `GET /auth/me`. */
  async function hydrateSessionFromApi(): Promise<AuthUser | null> {
    if (!hasTokens()) return null
    if (useMockAuthMode()) {
      const cached = authStore.user
      const user = cached ?? mockLoginUser(MOCK_DEMO_EMAIL, MOCK_DEMO_PASSWORD)
      authStore.login(user)
      return user
    }
    try {
      const me = await api.get<AuthUser | { data: AuthUser }>(ApiEndpoints.AUTH_ME, {
        suppressAccessAlert: true,
        suppressErrorToast: true,
      })
      const user = me && typeof me === 'object' && 'data' in (me as object)
        ? (me as { data: AuthUser }).data
        : me as AuthUser
      if (user?.email) {
        authStore.login(user)
        return user
      }
    }
    catch {
      if (!getAccessToken()) clearTokens()
    }
    return null
  }

  async function logout() {
    const { getRefreshToken } = await import('~/utils/auth/tokens')
    await logoutServer(getRefreshToken())
    await authStore.logout()
  }

  return {
    loginWithCredentials,
    requestPasswordReset,
    verifyPasswordResetCode,
    resendPasswordResetCode,
    resetPasswordWithCode,
    exchangePasswordResetHandoff,
    createTelegramLinkCode,
    changePassword,
    updateProfileAvatar,
    removeProfileAvatar,
    logout,
    hydrateSessionFromApi,
    isHttpMode: true,
  }
}
