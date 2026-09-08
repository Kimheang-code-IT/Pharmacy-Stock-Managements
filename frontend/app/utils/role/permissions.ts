import type { AppRolePermissionRow } from '~/types/stock-pos/entities'

/**
 * Actions used by Stock & POS page authorization.
 * Keys expand to `{permissionPrefix}.{action}` (e.g. products.view).
 */
export const ROLE_PERMISSION_ACTIONS = [
  'view',
  'create',
  'edit',
  'delete',
  'update',
  'confirm',
  'deliver',
  'cancel',
  'export',
  'print',
  'operate',
  'configure',
] as const

export type RolePermissionAction = (typeof ROLE_PERMISSION_ACTIONS)[number]

export interface RoleDocumentTypeDefinition {
  value: string
  labelKey: string
  permissionPrefix: string
  actions: readonly RolePermissionAction[]
}

const CRUD: readonly RolePermissionAction[] = ['view', 'create', 'edit', 'delete']
const CRUD_EXPORT: readonly RolePermissionAction[] = ['view', 'create', 'edit', 'delete', 'export']
const POS: readonly RolePermissionAction[] = ['view', 'create', 'edit', 'delete', 'export', 'print', 'operate']
const VIEW_EXPORT: readonly RolePermissionAction[] = ['view', 'export']
const VIEW_EXPORT_PRINT: readonly RolePermissionAction[] = ['view', 'export', 'print']
const SETTINGS: readonly RolePermissionAction[] = ['view', 'edit', 'configure']
const DELIVERY: readonly RolePermissionAction[] = ['view', 'create', 'update', 'confirm', 'deliver', 'cancel']

/**
 * One matrix row per app page / menu entry.
 * Keep in sync with `useMenu` routes and `definePageMeta({ permission })`.
 */
export const ROLE_DOCUMENT_TYPES: readonly RoleDocumentTypeDefinition[] = [
  { value: 'dashboard', labelKey: 'app.pages.dashboard', permissionPrefix: 'dashboard', actions: ['view'] },
  { value: 'categories', labelKey: 'app.nav.categories', permissionPrefix: 'categories', actions: CRUD_EXPORT },
  { value: 'uoms', labelKey: 'app.nav.uoms', permissionPrefix: 'uom', actions: CRUD_EXPORT },
  { value: 'brands', labelKey: 'app.nav.brands', permissionPrefix: 'brand', actions: CRUD_EXPORT },
  { value: 'products', labelKey: 'app.nav.stock', permissionPrefix: 'products', actions: CRUD_EXPORT },
  { value: 'suppliers', labelKey: 'app.nav.suppliers', permissionPrefix: 'suppliers', actions: CRUD_EXPORT },
  { value: 'customers', labelKey: 'app.nav.customers', permissionPrefix: 'customers', actions: CRUD_EXPORT },
  { value: 'delivery', labelKey: 'app.nav.deliveryNotes', permissionPrefix: 'delivery', actions: DELIVERY },
  { value: 'pos', labelKey: 'app.nav.pos', permissionPrefix: 'pos', actions: POS },
  { value: 'sales', labelKey: 'app.pages.salesReport', permissionPrefix: 'sales', actions: VIEW_EXPORT_PRINT },
  { value: 'reports', labelKey: 'app.nav.reports', permissionPrefix: 'reports', actions: VIEW_EXPORT_PRINT },
  { value: 'admin_users', labelKey: 'app.pages.users', permissionPrefix: 'admin.users', actions: CRUD },
  { value: 'admin_roles', labelKey: 'app.pages.roles', permissionPrefix: 'admin.roles', actions: CRUD },
  { value: 'admin_sequences', labelKey: 'app.pages.documentSequences', permissionPrefix: 'configuration', actions: CRUD },
  { value: 'app_config', labelKey: 'app.pages.settings', permissionPrefix: 'settings.app_config', actions: SETTINGS },
  { value: 'admin_audit', labelKey: 'app.pages.auditLogs', permissionPrefix: 'admin.audit_logs', actions: VIEW_EXPORT },
] as const

const ACTION_SET = new Set<string>(ROLE_PERMISSION_ACTIONS)
const LEGACY_ACTION_MAP: Record<string, RolePermissionAction | undefined> = {
  select: 'view',
  read: 'view',
  write: 'edit',
  manage: 'edit',
  archive: 'delete',
  purge: 'delete',
  share: 'export',
  report: 'view',
  import: 'create',
  transition: 'edit',
  assign: 'edit',
  mask: 'view',
}

export function normalizePermissionActions(actions: readonly string[] | null | undefined): RolePermissionAction[] {
  const normalized = new Set<RolePermissionAction>()
  for (const raw of actions || []) {
    const action = ACTION_SET.has(raw)
      ? raw as RolePermissionAction
      : LEGACY_ACTION_MAP[raw]
    if (action) normalized.add(action)
  }
  if ([...normalized].some(action => action !== 'view')) normalized.add('view')
  return ROLE_PERMISSION_ACTIONS.filter(action => normalized.has(action))
}

/** Merge API rows with the current matrix catalog and discard unknown rows/actions. */
export function normalizePermissionRows(
  rows: readonly AppRolePermissionRow[] | null | undefined,
  includeEmpty = true,
): AppRolePermissionRow[] {
  const byType = new Map((rows || []).map(row => [row.documentType, row]))
  const normalized = ROLE_DOCUMENT_TYPES.map((definition) => {
    const existing = byType.get(definition.value)
    const actions = normalizePermissionActions(existing?.actions)
      .filter(action => definition.actions.includes(action))
    return {
      id: existing?.id || `perm_${definition.value}`,
      documentType: definition.value,
      onlyIfCreator: false,
      level: 0,
      actions,
    }
  })
  return includeEmpty ? normalized : normalized.filter(row => row.actions.length > 0)
}

/** Enforce action dependencies consistently for checkbox and API payload flows. */
export function setPermissionAction(
  row: AppRolePermissionRow,
  action: string,
  enabled: boolean,
): AppRolePermissionRow {
  const normalizedAction = ACTION_SET.has(action)
    ? action as RolePermissionAction
    : LEGACY_ACTION_MAP[action]
  if (!normalizedAction) return row
  const actions = new Set(normalizePermissionActions(row.actions))
  if (enabled) {
    actions.add(normalizedAction)
    actions.add('view')
  }
  else if (normalizedAction === 'view') {
    actions.clear()
  }
  else {
    actions.delete(normalizedAction)
  }
  const ordered = ROLE_PERMISSION_ACTIONS.filter(item => actions.has(item))
  return {
    ...row,
    actions: ordered,
    onlyIfCreator: false,
  }
}

/** Expanded capabilities sent with structured rows for fast authorization checks. */
export function permissionRowsToFlatKeys(rows: AppRolePermissionRow[]): string[] {
  const definitions = new Map(ROLE_DOCUMENT_TYPES.map(item => [item.value, item]))
  const keys = new Set<string>()
  for (const row of normalizePermissionRows(rows, false)) {
    const prefix = definitions.get(row.documentType)?.permissionPrefix
    if (!prefix) continue
    for (const action of row.actions) keys.add(`${prefix}.${action}`)
  }
  return [...keys].sort()
}

export function flatKeysToPermissionRows(keys: readonly string[]): AppRolePermissionRow[] {
  const rows = ROLE_DOCUMENT_TYPES.map(definition => ({
    id: `perm_${definition.value}`,
    documentType: definition.value,
    onlyIfCreator: false,
    level: 0,
    actions: keys.includes('ALL_PAGES')
      ? [...definition.actions]
      : definition.actions.filter(action => keys.includes(`${definition.permissionPrefix}.${action}`)),
  }))
  return normalizePermissionRows(rows)
}

export type SeedRolePermissionMode = 'all' | 'staff' | 'viewer'

/** Fixture rows for seeded roles (Admin / Store Staff / Report Viewer). */
export function seedRolePermissionRows(mode: SeedRolePermissionMode): AppRolePermissionRow[] {
  const allow = (prefix: string) => {
    if (mode === 'all') return true
    if (mode === 'staff') {
      return prefix === 'dashboard'
        || ['categories', 'uom', 'brand', 'products', 'suppliers', 'customers', 'delivery', 'pos', 'sales'].includes(prefix)
        || prefix === 'reports'
    }
    // viewer
    return prefix === 'dashboard' || prefix === 'reports' || prefix === 'sales'
  }

  const allowedActions = (prefix: string, actions: readonly RolePermissionAction[]) => {
    if (mode === 'viewer') {
      return actions.filter(action => action === 'view' || action === 'export' || action === 'print')
    }
    if (mode === 'staff' && (prefix.startsWith('admin.') || prefix === 'configuration' || prefix.startsWith('settings.'))) {
      return []
    }
    return [...actions]
  }

  return normalizePermissionRows(
    ROLE_DOCUMENT_TYPES.map(definition => ({
      id: `perm_${definition.value}`,
      documentType: definition.value,
      onlyIfCreator: false,
      level: 0,
      actions: allow(definition.permissionPrefix)
        ? allowedActions(definition.permissionPrefix, definition.actions)
        : [],
    })),
  )
}
