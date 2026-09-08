import { h } from 'vue'
import { UBadge } from '#components'
import type { AppHeaderBadge } from '~/composables/layout/useAppHeader'
import type { ModuleAction, ModuleField, ModuleConfig, ModuleRelated, ModuleTable, ModuleFieldType  } from '~/config/modules'
import { getModule } from '~/config/modules'

import { isMoneyKey, isDateFieldKey, isDateTimeFieldKey } from '~/utils/module/field-keys'
import { documentSequenceTypeLabel } from '~/utils/document-sequences'
import { formatDate, formatDateTime, formatMoney as formatMoneyValue, formatNumber as formatNumberValue } from '~/utils/format/format-service'
import { codeTitle, labeledStatusOptions, shortDay } from '~/utils/module/format'

export { codeTitle, labeledStatusOptions, shortDay }

export function i18nSlug(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'general'
}

export function useModuleLabel() {
  const { t, te, locale } = useI18n()
  const route = useRoute()
  const km = computed(() => locale.value === 'km')

  function tx(key: string, fallback = '') {
    return te(key) ? String(t(key)) : fallback
  }

  function fieldLabel(field: Pick<ModuleField, 'key' | 'label' | 'labelKm' | 'labelKey'>) {
    if (field.labelKey && te(field.labelKey)) return String(t(field.labelKey))
    const collection = getModule(route.path)?.collection
    if (collection) {
      const scoped = `app.modules.${collection}.fields.${field.key}`
      if (te(scoped)) return String(t(scoped))
    }
    const generic = `app.fields.${field.key}`
    if (te(generic)) return String(t(generic))
    return km.value && field.labelKm ? field.labelKm : field.label
  }

  function moduleTitle(module: ModuleConfig) {
    if (module.titleKey && te(module.titleKey)) return String(t(module.titleKey))
    return tx(`app.modules.${module.collection}.title`, module.title)
  }

  function moduleSingular(module: ModuleConfig) {
    return tx(`app.modules.${module.collection}.singular`, module.singular)
  }

  function sectionTitle(field: Pick<ModuleField, 'section'>) {
    const title = field.section || ''
    return tx(`app.sections.${i18nSlug(title)}`, title)
  }

  function groupTitle(title: string) {
    return tx(`app.sections.${i18nSlug(title)}`, title)
  }

  function tableTitle(table: Pick<ModuleTable, 'key' | 'title'>) {
    return tx(`app.tables.${table.key}`, table.title)
  }

  function actionLabel(action: Pick<ModuleAction, 'key' | 'label'>) {
    return tx(`app.moduleActions.${action.key}`, action.label)
  }

  function relatedTitle(group: Pick<ModuleRelated, 'title'>) {
    return tx(`app.related.${i18nSlug(group.title)}`, group.title)
  }

  return {
    km,
    tx,
    fieldLabel,
    moduleTitle,
    moduleSingular,
    sectionTitle,
    groupTitle,
    tableTitle,
    actionLabel,
    relatedTitle,
  }
}

export function useModuleRoute() {
  const route = useRoute()
  const module = computed(() => getModule(route.path))
  const isCreate = computed(() => route.path.endsWith('/new') || route.params.id === 'new')
  const recordId = computed(() => isCreate.value ? '' : String(route.params.id || ''))
  return { module, isCreate, recordId, route }
}

export function emptyModuleRecord(module: ModuleConfig) {
  const record: Record<string, unknown> = { id: '', status: module.statuses?.[0] || 'Active' }
  for (const field of module.fields) {
    if (field.key === 'status') continue
    if (field.type === 'number') record[field.key] = 0
    else if (field.type === 'multiselect') record[field.key] = []
    else if (field.type === 'date') record[field.key] = new Date().toISOString().slice(0, 10)
    else if (field.type === 'checkbox') {
      record[field.key] = field.key === 'status'
        ? (field.options?.[0] ?? 'Active')
        : (field.options?.[1] ?? 'No')
    }
    else record[field.key] = ''
  }
  for (const table of module.tables || []) {
    record[table.key] = table.presets ? table.presets.map(row => ({ ...row })) : []
  }
  if (module.collection === 'roles' || module.collection === 'users') {
    record.permissionRows = []
    record.userCount = 0
    record.permissionCount = 0
  }
  if (module.collection === 'documentSequences') {
    record.year = null
    record.lastValue = 0
    record.paddingLength = 6
    record.status = 'ACTIVE'
  }
  return record
}

export function groupedFields(module: ModuleConfig) {
  const groups: Array<{ title: string, titleKm?: string, fields: ModuleField[] }> = []
  for (const field of module.fields) {
    const title = field.section || 'General'
    const current = groups.find(group => group.title === title)
    if (current) current.fields.push(field)
    else groups.push({ title, titleKm: field.sectionKm, fields: [field] })
  }
  return groups
}

export function statusColor(status: string): AppHeaderBadge['color'] {
  const value = status.toLowerCase()
  if (value === 'inactive') return 'neutral'
  if (value === 'confirmed') return 'success'
  if (value === 'out for delivery') return 'primary'
  if (value === 'rented' || value === 'progressing') return 'primary'
  if (value === 'maintenance') return 'warning'
  if (['active', 'paid', 'cleared', 'delivered', 'approved', 'accepted', 'closed', 'completed', 'pod received', 'posted', 'issued', 'converted', 'available'].some(s => value.includes(s))) return 'success'
  if (['pending', 'processing', 'partial', 'in transit', 'arriving', 'submitted', 'sent', 'in_progress', 'open', 'draft'].some(s => value.includes(s))) return 'warning'
  if (['overdue', 'missing', 'on hold', 'expired', 'unpaid', 'reversed', 'rejected', 'cancelled', 'superseded'].some(s => value.includes(s))) return 'error'
  return 'neutral'
}

export function asNumber(value: unknown) {
  const n = Number(value || 0)
  return Number.isFinite(n) ? n : 0
}

export function formatMoney(value: unknown, currency?: string) {
  return formatMoneyValue(value, currency)
}

export function formatModuleCell(
  value: unknown,
  key: string,
  currency?: string,
  fieldType?: ModuleFieldType,
) {
  if (value == null || value === '') return '—'
  if (key === 'documentType') return documentSequenceTypeLabel(value)
  if (isMoneyKey(key)) return formatMoney(value, currency)

  const resolvedType = fieldType
    || (isDateTimeFieldKey(key) ? 'datetime' : isDateFieldKey(key) ? 'date' : undefined)
  if (resolvedType === 'datetime') return formatDateTime(value)
  if (resolvedType === 'date') return formatDate(value)

  if (typeof value === 'number') return formatNumberValue(value)
  if (Array.isArray(value)) return value.map(item => String(item ?? '').trim()).filter(Boolean).join(', ') || '—'
  const text = String(value).trim()
  if (/^\d{4}-\d{2}-\d{2}T/.test(text)) return formatDateTime(text)
  return text || '—'
}

export function moduleStatusBadge(value: unknown, key = 'status', label?: string) {
  const raw = String(value ?? '')
  return h(UBadge, {
    color: statusColor(raw),
    variant: 'subtle',
    size: 'sm',
  }, () => label ?? formatModuleCell(value, key))
}
