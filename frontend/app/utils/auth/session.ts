import type { AuthUser } from '~/types/auth-user'

export const AUTH_STORAGE_KEY = 'stockpos:auth:user'

/** Cookie-safe user: drop bulky permission lists that overflow the 4KB cookie limit. */
export function compactAuthUser(user: AuthUser): AuthUser {
  const effective = user.effectivePermissions ?? user.permissions ?? user.pageAccess ?? []
  const isAllAccess = effective.includes('ALL_PAGES')
  return {
    id: user.id,
    name: user.name,
    email: user.email,
    role: user.role,
    roleId: user.roleId,
    avatar: user.avatar,
    effectivePermissions: isAllAccess ? ['ALL_PAGES'] : effective,
    pageAccess: isAllAccess ? ['ALL_PAGES'] : effective,
    permissions: isAllAccess ? ['ALL_PAGES'] : effective,
    sourcePermissions: user.sourcePermissions,
  }
}

/** Allow application-relative navigation only; rejects protocol-relative, control chars, and /auth/ loops. */
export function safeInternalPath(value: unknown): string | null {
  const raw = typeof value === 'string' ? value.trim() : ''
  const containsControlCharacter = [...raw].some(character => character.charCodeAt(0) <= 31)
  if (!raw.startsWith('/') || raw.startsWith('//') || containsControlCharacter || raw.startsWith('/auth/')) return null
  return raw
}

