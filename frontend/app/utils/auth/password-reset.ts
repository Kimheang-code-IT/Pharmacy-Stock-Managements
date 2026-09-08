const STORAGE_KEY = 'stockpos:auth:password-reset'

export interface PasswordResetSession {
  email: string
  verified: boolean
  /** Short-lived JWT returned by verification; required to submit the reset. */
  resetToken?: string
  updatedAt: string
}

function readRaw(): PasswordResetSession | null {
  if (!import.meta.client) return null
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    return JSON.parse(raw) as PasswordResetSession
  }
  catch {
    return null
  }
}

function writeRaw(session: PasswordResetSession | null) {
  if (!import.meta.client) return
  if (!session) {
    sessionStorage.removeItem(STORAGE_KEY)
    return
  }
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session))
}

/** Persist the email after "send reset code". */
export function startPasswordReset(email: string) {
  writeRaw({
    email: email.trim().toLowerCase(),
    verified: false,
    updatedAt: new Date().toISOString(),
  })
}

export function getPasswordResetSession(): PasswordResetSession | null {
  return readRaw()
}

/** Store the short-lived reset token returned by a successful verification. */
export function markPasswordResetVerified(resetToken: string) {
  const current = readRaw()
  if (!current?.email) return null
  const next: PasswordResetSession = {
    ...current,
    verified: true,
    resetToken,
    updatedAt: new Date().toISOString(),
  }
  writeRaw(next)
  return next
}

export function clearPasswordResetSession() {
  writeRaw(null)
}

/** Initialize reset session from Telegram web handoff token. */
export function applyPasswordResetHandoff(email: string, resetToken: string) {
  writeRaw({
    email: email.trim().toLowerCase(),
    verified: true,
    resetToken,
    updatedAt: new Date().toISOString(),
  })
}

export const MOCK_RESET_CODE = '123456'

