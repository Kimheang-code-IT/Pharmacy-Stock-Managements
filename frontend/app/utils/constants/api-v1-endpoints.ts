/** Reserved `/api/v1` auth and admin operations for future API wiring. */
export const ApiV1Endpoints = {
  LOGIN: '/api/v1/auth/login',
  LOGOUT: '/api/v1/auth/logout',
  REFRESH: '/api/v1/auth/refresh',
  USERS: '/api/v1/users',
  ROLE_ASSIGNMENTS: (userId: number) => `/api/v1/users/${userId}/role-assignments`,
  ATTACHMENTS_PRESIGN: '/api/v1/attachments/presign',
  AUDIT_EVENTS: '/api/v1/audit-events',
} as const
