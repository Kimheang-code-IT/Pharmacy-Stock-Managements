/** JWT user permission and API error contract types for the Stock & POS API. */

export type ApiErrorCode =
  | 'AUTH_REQUIRED'
  | 'ACCESS_DENIED'
  | 'REFERENCE_NOT_FOUND'

export interface ApiErrorBody {
  code: ApiErrorCode | string
  message: string
  request_id: string
  field_errors?: Record<string, string>
}

/** Permission codes carried by the authenticated user's JWT claims. */
export const SOURCE_PERMISSIONS = [
  'settings.read',
  'settings.update',
  'user.read',
  'user.manage',
  'role.read',
  'role.manage',
  'attachment.read',
  'attachment.upload',
  'attachment.delete',
  'audit_log.read',
  'report.read',
] as const

export type SourcePermission = typeof SOURCE_PERMISSIONS[number]
