import { describe, expect, it } from 'vitest'
import { flatKeysToPermissionRows, permissionRowsToFlatKeys } from '../app/utils/role/permissions'
import { resolveUserPermissionKeys } from '../app/utils/auth/user-permissions'

describe('role-only authorization', () => {
  it('serializes the authoritative role matrix', () => {
    const keys = ['reports.view', 'reports.export', 'products.view', 'pos.view']
    expect(permissionRowsToFlatKeys(flatKeysToPermissionRows(keys))).toEqual([...keys].sort())
  })

  it('fails closed when permissions are absent', () => {
    expect(resolveUserPermissionKeys({ name: 'No access', email: 'none@example.com' })).toEqual([])
  })

  it('uses effective permissions before compatibility fields', () => {
    expect(resolveUserPermissionKeys({
      name: 'Restricted',
      email: 'restricted@example.com',
      effectivePermissions: ['reports.view'],
      permissions: ['ALL_PAGES'],
      pageAccess: ['ALL_PAGES'],
    })).toEqual(['reports.view'])
  })
})
