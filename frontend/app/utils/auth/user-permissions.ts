import type { AuthUser } from '~/types/auth-user'
import type { AppRolePermissionRow } from '~/types/stock-pos/entities'
import {
  ROLE_DOCUMENT_TYPES,
  permissionRowsToFlatKeys,
  type RolePermissionAction,
} from '~/utils/role/permissions'

export type UserPermissionGroup = {
  documentType: string
  labelKey: string
  permissionPrefix: string
  actions: RolePermissionAction[]
}

/** All permission keys defined by the system matrix. */
export function getAllSystemPermissionKeys(): string[] {
  const rows: AppRolePermissionRow[] = ROLE_DOCUMENT_TYPES.map(definition => ({
    id: `perm_${definition.value}`,
    documentType: definition.value,
    onlyIfCreator: false,
    level: 0,
    actions: [...definition.actions],
  }))
  return permissionRowsToFlatKeys(rows)
}

/** Resolve flat permission keys for the signed-in user. */
export function resolveUserPermissionKeys(user: AuthUser | null | undefined): string[] {
  if (!user) return []
  const access = user.effectivePermissions ?? user.permissions ?? user.pageAccess
  if (!Array.isArray(access)) return []
  if (access.includes('ALL_PAGES')) return getAllSystemPermissionKeys()
  return [...access].sort()
}

/** Group granted keys by module for profile display. */
export function groupUserPermissions(keys: readonly string[]): UserPermissionGroup[] {
  const granted = new Set(keys)
  return ROLE_DOCUMENT_TYPES
    .map((definition) => {
      const actions = definition.actions.filter(action =>
        granted.has(`${definition.permissionPrefix}.${action}`),
      )
      return {
        documentType: definition.value,
        labelKey: definition.labelKey,
        permissionPrefix: definition.permissionPrefix,
        actions,
      }
    })
    .filter(group => group.actions.length > 0)
}

export function countUserPermissions(groups: readonly UserPermissionGroup[]): number {
  return groups.reduce((sum, group) => sum + group.actions.length, 0)
}
