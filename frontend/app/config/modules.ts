import type { DocumentTabSchema } from '~/types/stock-pos/common'
import { adminModules } from './admin-modules'
import { deliveryModules } from './delivery-modules'
import { stockModules } from './stock-modules'

/**
 * Module registry types + helpers for the Stock & POS management system.
 */

export type ModuleFieldType = 'text' | 'date' | 'datetime' | 'number' | 'select' | 'multiselect' | 'textarea' | 'file' | 'password' | 'checkbox' | 'image'

export type ModuleSelectOption = string | { label: string, value: string }

export type ModuleField = {
  key: string
  label: string
  labelKm?: string
  section?: string
  sectionKm?: string
  type?: ModuleFieldType
  options?: readonly ModuleSelectOption[] | ModuleSelectOption[]
  optionsCollection?: string
  optionsEndpoint?: string
  /** Filter only: use the configured `options` list and never merge values
   *  discovered in the loaded rows. */
  optionsOnly?: boolean
  required?: boolean
  colSpan?: 1 | 2
  computed?: boolean
  createOnly?: boolean
  hideOnCreate?: boolean
  helpKey?: string
  help?: string
  labelKey?: string
}

export type ModuleLineOptionItem = { label: string, value: string }

export type ModuleLineColumn = {
  key: string
  label: string
  labelKm?: string
  type?: 'text' | 'number' | 'select' | 'textarea' | 'checkbox' | 'date' | 'datetime'
  options?: readonly string[] | string[]
  /** Static items, or a per-row resolver (e.g. UOM options of the row's product). */
  optionItems?: ModuleLineOptionItem[] | ((row: Record<string, unknown>) => ModuleLineOptionItem[])
  /** Cell/input width override (e.g. 'w-80 min-w-64'); defaults per key. */
  width?: string
  /** Render select columns with a searchable input menu (e.g. product picker). */
  searchable?: boolean
  /** Maximum for a number cell (static or per-row, e.g. returnable qty). */
  max?: number | ((row: Record<string, unknown>) => number | undefined)
  computed?: boolean
  required?: boolean
  labelKey?: string
  inlineFields?: Array<{ key: string, label: string, labelKm?: string, labelKey?: string }>
}

export type ModuleTable = {
  key: string
  title: string
  titleKm?: string
  columns: ModuleLineColumn[]
  addLabel?: string
  addLabelKey?: string
  presets?: Array<Record<string, unknown>>
  lockedPresets?: boolean
  kind?: 'files'
  /** Fit the enclosing page width (no min-width / horizontal scroll on
   *  desktop) with denser cell padding; narrow screens still scroll. */
  fitWidth?: boolean
}

export const FILE_ATTACHMENT_COLUMNS: ModuleLineColumn[] = [
  { key: 'fileName', label: 'File name', labelKm: 'ឈ្មោះឯកសារ', labelKey: 'app.ui.fileNameCol', computed: true },
  { key: 'uploadedBy', label: 'By', labelKm: 'ដោយ', labelKey: 'app.ui.byCol', computed: true },
  { key: 'uploadedAt', label: 'Created', labelKm: 'បង្កើត', labelKey: 'app.ui.createdCol', type: 'datetime', computed: true },
]

export type ModuleRelated = {
  path: string
  title: string
  titleKm?: string
  foreignKey: string
  localKey: string
}

export type ModuleAction = {
  key: string
  label: string
  labelKm?: string
  icon: string
  color?: 'primary' | 'neutral' | 'success' | 'warning' | 'error'
}

export type ModuleDocumentForm = 'roles' | 'product' | 'party'

/** Explicit backend permission codes for a module's mutation actions. The
 *  backend catalog does not follow a single `{module}.{action}` convention
 *  (e.g. `stock.view` vs `product.update`, `user.update`), so modules declare
 *  the exact codes instead of deriving them. */
export type ModuleActionPermissions = {
  create?: string
  edit?: string
  delete?: string
  operate?: string
}

export type ModuleConfig = {
  path: string
  title: string
  titleKm: string
  singular: string
  singularKm: string
  description: string
  descriptionKm: string
  icon: string
  group: string
  permission: string
  collection: string
  titleField: string
  columns: ModuleField[]
  fields: ModuleField[]
  filters?: ModuleField[]
  tables?: ModuleTable[]
  tabs?: DocumentTabSchema[]
  documentForm?: ModuleDocumentForm
  hideTablesOnCreate?: boolean
  related?: ModuleRelated[]
  actions?: ModuleAction[]
  progress?: readonly string[]
  statuses?: readonly string[] | string[]
  readOnly?: boolean
  tableOnly?: boolean
  canCreate?: boolean
  /** Permission for the Create action when it differs from `{prefix}.create`.
   * Also lets a readOnly report module route Create to a full-page /new flow. */
  createPermission?: string
  /** Exact backend codes for create/edit/delete/operate on this module. */
  actionPermissions?: ModuleActionPermissions
  titleKey?: string
  kind?: 'standard' | 'reports'
}

const f = (
  key: string,
  label: string,
  labelKm: string,
  section = 'General Information',
  sectionKm = 'ព័ត៌មានទូទៅ',
  type: ModuleFieldType = 'text',
  options?: readonly ModuleSelectOption[] | ModuleSelectOption[],
  extra: Partial<ModuleField> = {},
): ModuleField => ({ key, label, labelKm, section, sectionKm, type, options, ...extra })

const col = (key: string, label: string, labelKm?: string, extra: Partial<ModuleField> = {}): ModuleField => ({
  key,
  label,
  labelKm: labelKm || label,
  ...extra,
})

function createModule(partial: Omit<ModuleConfig, 'canCreate'> & { canCreate?: boolean }): ModuleConfig {
  return {
    // readOnly modules are create-less unless Create is explicitly enabled
    // (e.g. the Purchase Report routing Create to the purchase page).
    canCreate: partial.readOnly ? partial.canCreate === true : partial.canCreate !== false,
    kind: partial.kind || 'standard',
    ...partial,
  }
}

export const appModules: ModuleConfig[] = [...adminModules, ...stockModules, ...deliveryModules]

export { f, col, createModule }

export function getModule(path: string) {
  const clean = path.replace(/\/$/, '') || '/'
  const sorted = appModules
    .slice()
    .sort((a, b) => b.path.length - a.path.length)
  const exact = sorted.find(module => clean === module.path || clean.startsWith(`${module.path}/`))
  if (exact) return exact
  const compact = (value: string) => value.replace(/-/g, '')
  const needle = compact(clean)
  return sorted.find(module => {
    const candidate = compact(module.path)
    return needle === candidate || needle.startsWith(`${candidate}/`)
  })
}
