import type { AppRolePermissionRow } from '~/types/stock-pos/entities'

/**
 * Frontend projection of the backend permission catalog
 * (`backend/app/core/permissions.py`). The backend catalog from
 * `GET /admin/permissions` is authoritative: the matrix only ever stores and
 * sends the exact `module.action` codes that the backend exposes here.
 *
 * Rows are **pages/modules** (Products, Stock Movements, each Report, …) and
 * columns are semantic actions (View, Create, Stock In, …). One backend code
 * may back more than one page cell (e.g. `stock.view` gates both the Products
 * and the Stock Movements pages), so the matrix keeps a single granted-code set
 * and derives every cell from it instead of storing per-row state.
 */
export type MatrixGroupId =
  | 'dashboard'
  | 'stock'
  | 'pos'
  | 'delivery'
  | 'setup'
  | 'reports'
  | 'administration'

export interface MatrixGroupDefinition {
  id: MatrixGroupId
  labelKey: string
}

export interface MatrixActionDefinition {
  /** Semantic action key (i18n under `core.rolePermissions.actions`). */
  key: string
  /** Exact backend permission code (`module.action`). */
  permission: string
}

export interface MatrixPageDefinition {
  /** Stable matrix row id (also `AppRolePermissionRow.documentType`). */
  value: string
  labelKey: string
  /** Sidebar group the page belongs to (matrix filter). */
  group: MatrixGroupId
  actions: readonly MatrixActionDefinition[]
}

const a = (key: string, permission: string): MatrixActionDefinition => ({ key, permission })

const crud = (module: string): MatrixActionDefinition[] => [
  a('view', `${module}.view`),
  a('create', `${module}.create`),
  a('update', `${module}.update`),
  a('delete', `${module}.delete`),
]

/**
 * Every page/module in the system with the actions the backend actually
 * supports for it. Actions the backend does not expose a distinct code for
 * (Export, delivery Print, Activate/Deactivate, …) are intentionally omitted —
 * never invent a permission the backend cannot enforce.
 */
export const PERMISSION_MATRIX_PAGES: readonly MatrixPageDefinition[] = [
  {
    value: 'dashboard',
    labelKey: 'app.nav.dashboard',
    group: 'dashboard',
    actions: [a('view', 'dashboard.view'), a('view_profit', 'dashboard.view_profit')],
  },
  {
    value: 'products',
    labelKey: 'app.pages.products',
    group: 'stock',
    actions: [
      a('view', 'stock.view'),
      a('create', 'product.create'),
      a('update', 'product.update'),
      a('delete', 'product.delete'),
      a('stock_in', 'stock.in'),
      a('adjust', 'stock.adjust'),
      a('damage', 'stock.damage'),
      a('expire', 'stock.expire'),
    ],
  },
  {
    value: 'stock_movements',
    labelKey: 'app.pages.stockMovements',
    group: 'stock',
    actions: [a('view', 'stock.view'), a('stock_valuation', 'report.stock_valuation')],
  },

  {
    value: 'pos',
    labelKey: 'app.nav.pos',
    group: 'pos',
    actions: [
      a('checkout', 'pos.access'),
      a('discount', 'pos.discount'),
      a('debt_sale', 'pos.debt_sale'),
      a('print_invoice', 'pos.print'),
      a('sale_edit', 'pos.sale_edit'),
      a('return', 'pos.return'),
      a('refund', 'pos.refund'),
    ],
  },
  {
    value: 'delivery',
    labelKey: 'app.nav.deliveryNotes',
    group: 'delivery',
    actions: [
      a('view', 'delivery.view'),
      a('create', 'delivery.create'),
      a('update', 'delivery.update'),
      a('confirm', 'delivery.confirm'),
      a('deliver', 'delivery.deliver'),
      a('cancel', 'delivery.cancel'),
    ],
  },
  { value: 'categories', labelKey: 'app.nav.categories', group: 'setup', actions: crud('category') },
  { value: 'uoms', labelKey: 'app.nav.uoms', group: 'setup', actions: crud('uom') },
  { value: 'brands', labelKey: 'app.nav.brands', group: 'setup', actions: crud('brand') },
  {
    value: 'suppliers',
    labelKey: 'app.nav.suppliers',
    group: 'setup',
    actions: [...crud('supplier'), a('pay_debt', 'supplier.debt.pay')],
  },
  {
    value: 'customers',
    labelKey: 'app.nav.customers',
    group: 'setup',
    actions: [...crud('customer'), a('pay_debt', 'customer.debt.pay')],
  },
  {
    value: 'sales_report',
    labelKey: 'app.pages.salesReport',
    group: 'reports',
    actions: [a('view', 'report.sales')],
  },
  {
    value: 'purchase_report',
    labelKey: 'app.pages.purchaseReport',
    group: 'reports',
    actions: [a('view', 'report.purchase')],
  },
  {
    value: 'customer_debt_report',
    labelKey: 'app.pages.customerDebtReport',
    group: 'reports',
    actions: [a('view', 'report.customer_debt'), a('pay_debt', 'customer.debt.pay')],
  },
  {
    value: 'supplier_debt_report',
    labelKey: 'app.pages.supplierDebtReport',
    group: 'reports',
    actions: [a('view', 'report.supplier_debt'), a('pay_debt', 'supplier.debt.pay')],
  },
  {
    value: 'finance_report',
    labelKey: 'app.pages.financeReport',
    group: 'reports',
    actions: [
      a('view', 'report.finance'),
      a('view_expense', 'expense.view'),
      a('create_expense', 'expense.create'),
      a('approve_expense', 'expense.approve'),
      a('void_expense', 'expense.void'),
      a('expense_report', 'report.expense'),
    ],
  },
  { value: 'users', labelKey: 'app.pages.users', group: 'administration', actions: crud('user') },
  { value: 'roles', labelKey: 'app.pages.roles', group: 'administration', actions: crud('role') },
  { value: 'document_sequences', labelKey: 'app.pages.documentSequences', group: 'administration', actions: crud('sequence') },
  { value: 'audit_logs', labelKey: 'app.pages.auditLogs', group: 'administration', actions: [a('view', 'audit.view')] },
  {
    value: 'settings',
    labelKey: 'app.pages.settings',
    group: 'administration',
    actions: [
      a('view', 'settings.view'),
      a('update', 'settings.update'),
      a('maintenance', 'system.maintenance'),
      a('data_reset', 'system.data_reset'),
      a('backup', 'system.backup'),
      a('restore', 'system.restore'),
    ],
  },
] as const

/**
 * Display order of the action columns in the matrix. Any action returned by
 * the live catalog but missing here is appended after these (alphabetically),
 * so a backend catalog addition still renders without a frontend change.
 */
export const ACTION_COLUMN_ORDER: readonly string[] = [
  'view',
  'view_profit',
  'create',
  'update',
  'delete',
  'stock_in',
  'adjust',
  'damage',
  'expire',
  'checkout',
  'discount',
  'debt_sale',
  'print_invoice',
  'sale_edit',
  'return',
  'refund',
  'approve_expense',
  'void_expense',
  'view_expense',
  'expense_report',
  'stock_valuation',
  'confirm',
  'deliver',
  'cancel',
  'pay_debt',
  'create_expense',
  'maintenance',
  'data_reset',
  'backup',
  'restore',
]

/** Fallback sidebar group for a raw backend module code. */
const MODULE_GROUP: Record<string, MatrixGroupId> = {
  dashboard: 'dashboard',
  stock: 'stock',
  product: 'stock',
  pos: 'pos',
  delivery: 'delivery',
  category: 'setup',
  uom: 'setup',
  brand: 'setup',
  supplier: 'setup',
  customer: 'setup',
  report: 'reports',
  expense: 'reports',
  user: 'administration',
  role: 'administration',
  sequence: 'administration',
  audit: 'administration',
  settings: 'administration',
  system: 'administration',
}

export const SUPER_ADMIN_PERMISSION = 'ALL_PAGES'

/**
 * Synthetic matrix row that represents the backend `ALL_PAGES` wildcard.
 * It keeps the "Full access" state editable/serializable without expanding
 * `ALL_PAGES` into every individual permission code (which the backend
 * rejects for the system Administrator role).
 */
export const FULL_ACCESS_ROW_ID = '__full_access__'

function fullAccessRow(): AppRolePermissionRow {
  return {
    id: `perm_${FULL_ACCESS_ROW_ID}`,
    documentType: FULL_ACCESS_ROW_ID,
    onlyIfCreator: false,
    level: 0,
    actions: [SUPER_ADMIN_PERMISSION],
  }
}

/** True when the rows represent the `ALL_PAGES` wildcard. */
export function isFullAccessRows(rows: readonly AppRolePermissionRow[] | null | undefined): boolean {
  return (rows || []).some(row =>
    row.documentType === FULL_ACCESS_ROW_ID || row.actions.includes(SUPER_ADMIN_PERMISSION),
  )
}

/** Sidebar group for a matrix row / backend module code. */
export function matrixGroupFor(value: string): MatrixGroupId {
  return PERMISSION_MATRIX_PAGES.find(def => def.value === value)?.group
    || MODULE_GROUP[value]
    || 'administration'
}

/** Every unique backend permission code covered by the page matrix. */
export function allFrontendPermissionCodes(): string[] {
  const codes = new Set<string>()
  for (const page of PERMISSION_MATRIX_PAGES) {
    for (const action of page.actions) codes.add(action.permission)
  }
  return [...codes]
}

/** Page/action cells that back a single backend permission code. */
export function pageActionsForPermission(permission: string): Array<{ page: MatrixPageDefinition, action: MatrixActionDefinition }> {
  const matches: Array<{ page: MatrixPageDefinition, action: MatrixActionDefinition }> = []
  for (const page of PERMISSION_MATRIX_PAGES) {
    for (const action of page.actions) {
      if (action.permission === permission) matches.push({ page, action })
    }
  }
  return matches
}

function normalizeActions(actions: readonly string[] | null | undefined): string[] {
  const seen = new Set<string>()
  for (const action of actions || []) {
    const value = String(action || '').trim()
    if (value) seen.add(value)
  }
  return [...seen]
}

/** Merge duplicate rows and trim action noise; order follows the page registry. */
export function normalizePermissionRows(
  rows: readonly AppRolePermissionRow[] | null | undefined,
  includeEmpty = true,
): AppRolePermissionRow[] {
  const byType = new Map<string, AppRolePermissionRow>()
  for (const row of rows || []) {
    const documentType = String(row.documentType || '').trim()
    if (!documentType) continue
    const actions = normalizeActions(row.actions)
    const existing = byType.get(documentType)
    byType.set(documentType, {
      id: row.id || `perm_${documentType}`,
      documentType,
      onlyIfCreator: Boolean(row.onlyIfCreator ?? existing?.onlyIfCreator),
      level: Number.isFinite(Number(row.level ?? existing?.level)) ? Number(row.level ?? existing?.level) : 0,
      actions: existing ? normalizeActions([...existing.actions, ...actions]) : actions,
    })
  }
  const ordered = PERMISSION_MATRIX_PAGES
    .filter(def => byType.has(def.value))
    .map(def => byType.get(def.value)!)
  const extras = [...byType.values()].filter(row => !PERMISSION_MATRIX_PAGES.some(def => def.value === row.documentType))
  const all = [...ordered, ...extras]
  return includeEmpty ? all : all.filter(row => row.actions.length > 0)
}

/**
 * Toggle one flat backend code (`module.action`) on the matrix rows, applying
 * the ERP view-dependency rules:
 * - granting a non-view action also grants the page's View permission;
 * - clearing View clears every dependent action on that page.
 */
export function setFlatPermission(
  rows: readonly AppRolePermissionRow[] | null | undefined,
  code: string,
  enabled: boolean,
): AppRolePermissionRow[] {
  const matches = pageActionsForPermission(code)
  const current = new Set(isFullAccessRows(rows) ? [] : permissionRowsToFlatKeys(rows as AppRolePermissionRow[]))
  if (enabled) {
    current.add(code)
    for (const { page, action } of matches) {
      if (action.key === 'view') continue
      const view = page.actions.find(item => item.key === 'view')
      if (view) current.add(view.permission)
    }
  }
  else {
    const viewPages = matches.filter(match => match.action.key === 'view').map(match => match.page)
    if (viewPages.length) {
      for (const page of viewPages) {
        for (const action of page.actions) current.delete(action.permission)
      }
    }
    else {
      current.delete(code)
    }
  }
  return flatKeysToPermissionRows([...current])
}

/** Matrix rows → flat backend codes (`module.action`); `ALL_PAGES` stays a wildcard. */
export function permissionRowsToFlatKeys(rows: AppRolePermissionRow[]): string[] {
  if (isFullAccessRows(rows)) return [SUPER_ADMIN_PERMISSION]
  const keys = new Set<string>()
  for (const row of normalizePermissionRows(rows, false)) {
    const page = PERMISSION_MATRIX_PAGES.find(def => def.value === row.documentType)
    for (const action of row.actions) {
      if (page) {
        const definition = page.actions.find(
          item => item.key === action || item.permission === action,
        )
        if (definition) {
          keys.add(definition.permission)
          continue
        }
      }
      // Already a fully-qualified backend code (e.g. supplier.debt.pay).
      if (action.includes('.') && !action.startsWith(`${row.documentType}.`)) {
        keys.add(action)
        continue
      }
      // Unknown row/action (catalog addition not yet modelled) → module.action.
      keys.add(`${row.documentType}.${action}`)
    }
  }
  return [...keys].sort()
}

/**
 * Flat backend codes → matrix rows. A code is projected onto every page cell
 * that backs it (e.g. `stock.view` onto Products **and** Stock Movements), so
 * shared permissions stay in sync across rows.
 */
export function flatKeysToPermissionRows(keys: readonly string[]): AppRolePermissionRow[] {
  if (keys.includes(SUPER_ADMIN_PERMISSION)) {
    return normalizePermissionRows([fullAccessRow()], true)
  }
  const byType = new Map<string, string[]>()
  for (const key of keys) {
    const matches = pageActionsForPermission(key)
    if (matches.length) {
      for (const { page, action } of matches) {
        byType.set(page.value, [...(byType.get(page.value) || []), action.key])
      }
      continue
    }
    // Unknown code → generic module.action row (kept for forward compatibility).
    const separator = key.indexOf('.')
    if (separator <= 0) continue
    const module = key.slice(0, separator)
    const action = key.slice(separator + 1)
    if (!action) continue
    byType.set(module, [...(byType.get(module) || []), action])
  }
  return normalizePermissionRows([...byType.entries()].map(([documentType, actions]) => ({
    id: `perm_${documentType}`,
    documentType,
    onlyIfCreator: false,
    level: 0,
    actions,
  })), true)
}

/** Sort page actions into the shared column order (extras last, A–Z). */
export function orderedPageActions(page: MatrixPageDefinition): MatrixActionDefinition[] {
  const rank = new Map(ACTION_COLUMN_ORDER.map((key, index) => [key, index]))
  return [...page.actions].sort((left, right) => {
    const leftRank = rank.get(left.key) ?? ACTION_COLUMN_ORDER.length
    const rightRank = rank.get(right.key) ?? ACTION_COLUMN_ORDER.length
    if (leftRank !== rightRank) return leftRank - rightRank
    return left.key.localeCompare(right.key)
  })
}
