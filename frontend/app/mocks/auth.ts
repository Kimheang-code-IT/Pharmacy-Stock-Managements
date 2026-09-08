import type { AuthUser } from '~/types/auth-user'

/**
 * Mock-only session. Accepts any non-empty email/password in demo mode so the
 * app is explorable without a backend. Tokens are opaque placeholders stored
 * through the normal bearer token utils, keeping the auth gate identical.
 */
export const MOCK_DEMO_EMAIL = 'admin@stockpos.local'
export const MOCK_DEMO_PASSWORD = 'admin123'

export const MOCK_AUTH_USER: AuthUser = {
  id: 1,
  name: 'Sokha Chan',
  email: MOCK_DEMO_EMAIL,
  role: 'Administrator',
  roleId: 1,
  effectivePermissions: ['ALL_PAGES'],
  permissions: ['ALL_PAGES'],
}

export function mockLoginUser(email: string, _password: string): AuthUser {
  const normalized = email.trim().toLowerCase()
  if (!normalized) throw new Error('Email is required')
  if (!_password) throw new Error('Password is required')
  if (normalized === MOCK_DEMO_EMAIL) return { ...MOCK_AUTH_USER }
  return { ...MOCK_AUTH_USER, email: normalized }
}
