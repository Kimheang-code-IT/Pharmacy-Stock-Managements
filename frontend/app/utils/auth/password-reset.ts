const STORAGE_KEY = 'stockpos:auth:password-reset'

export interface PasswordResetSession {
  email: string
  verified: boolean
  /** Short-lived JWT returned by verification; required to submit the reset. */
  resetToken?: string
  /** One-time /link code to send to the Telegram bot when no chat is linked. */
  linkCode?: string | null
  updatedAt: string
}

/** Parsed `POST /auth/forgot-password` result (linked vs. link-required). */
export interface PasswordResetStart {
  channel: 'telegram' | 'telegram_link'
  linkCode: string | null
  expiresIn: number
}

/**
 * Read the reset-start result. When the account has no linked Telegram chat
 * the backend returns `channel: "telegram_link"` plus a one-time `/link` code
 * the user sends to the bot; the bot then replies with the reset code.
 */
export function parsePasswordResetStart(data: unknown): PasswordResetStart {
  const row = (data && typeof data === 'object') ? data as Record<string, unknown> : {}
  const linkCode = row.linkCode ?? row.link_code
  return {
    channel: row.channel === 'telegram_link' ? 'telegram_link' : 'telegram',
    linkCode: linkCode ? String(linkCode) : null,
    expiresIn: Number(row.expiresIn ?? row.expires_in ?? 0) || 0,
  }
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

/** Persist the email after "send reset code" (plus the bot link code if any). */
export function startPasswordReset(email: string, linkCode: string | null = null) {
  writeRaw({
    email: email.trim().toLowerCase(),
    verified: false,
    linkCode,
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

