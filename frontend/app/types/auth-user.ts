import type { SourcePermission } from '~/types/stock-pos/domain'

export interface AuthUser {
  id?: number
  name: string
  email: string
  role?: string
  roleId?: number
  avatar?: string
  telegramLinked?: boolean
  /** Flat UI page keys. Frontend hiding is not authorization. */
  permissions?: string[]
  effectivePermissions?: string[]
  /** Legacy mirror of effectivePermissions. */
  pageAccess?: string[]
  sourcePermissions?: SourcePermission[]
}
