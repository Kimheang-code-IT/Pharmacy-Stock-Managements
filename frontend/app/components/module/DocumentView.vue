<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'
import { useAppHeader } from '~/composables/layout/useAppHeader'
import { useConfirm } from '~/composables/common/useConfirm'
import { usePageSeo } from '~/composables/usePageSeo'
import {
  emptyModuleRecord,
  statusColor,
  useModuleLabel,
  useModuleRoute,
} from '~/composables/module/useModule'
import type { AppRecord } from '~/config/admin-seed'
import { useModuleRecordChrome } from '~/composables/module/useModuleRecordChrome'
import { normalizePermissionRows, permissionRowsToFlatKeys } from '~/utils/role/permissions'
import { normalizeUomConversions } from '~/utils/stock/uom-conversions'
import type { AppRolePermissionRow } from '~/types/stock-pos/entities'
import { documentSequencePreview, documentSequenceTypeLabel, documentSequenceTypeOptions, normalizeDocumentSequenceType } from '~/utils/document-sequences'
import {
  moduleDocumentLineActionKey,
  moduleDocumentTabs,
  RELATED_FIELD_KEY,
} from '~/utils/module/document-tabs'

const { module, isCreate, recordId, route } = useModuleRoute()
const store = useAppDataStore()
const auth = useAuthStore()
const { t } = useI18n()
const toast = useToast()
const { moduleTitle, moduleSingular, fieldLabel } = useModuleLabel()
const { setBreadcrumbs, setBadges, clear } = useAppHeader()
const { confirm } = useConfirm()

const saving = ref(false)
const loadingRecord = ref(false)
const activeTab = ref('general')
const model = ref<AppRecord>({ id: '' } as AppRecord)
const originalModel = ref<AppRecord | null>(null)
const notFound = ref(false)
let loadGeneration = 0

const {
  currentUser,
  listTo,
  canNavigatePrevious,
  canNavigateNext,
  navigatePrevious,
  navigateNext,
  attachments,
  tags,
  metaOwner,
  metaAssignee,
  setChromeField,
} = useModuleRecordChrome({ module, isCreate, recordId, model })

function applyRoleMatrix() {
  if (module.value?.collection !== 'roles') return
  const rows = normalizePermissionRows(model.value.permissionRows as AppRolePermissionRow[] | undefined)
  model.value = {
    ...model.value,
    permissionRows: rows,
    permissionCount: permissionRowsToFlatKeys(rows).length,
  }
}

function applyLoadedRecord(record: AppRecord) {
  model.value = { ...record } as AppRecord
  originalModel.value = { ...record } as AppRecord
  notFound.value = false
  applyRoleMatrix()
}

async function load() {
  const generation = ++loadGeneration
  if (!module.value) return
  if (isCreate.value) {
    loadingRecord.value = false
    model.value = emptyModuleRecord(module.value) as AppRecord
    if (module.value.collection === 'documentSequences') {
      model.value.nextNumberPreview = documentSequencePreview(model.value)
    }
    originalModel.value = null
    notFound.value = false
    const query = route.query
    for (const [key, value] of Object.entries(query)) {
      if (key === 'status') continue
      if (typeof value === 'string' && value) model.value[key] = value
    }
    applyRoleMatrix()
    return
  }
  const found = store.get(module.value.collection, recordId.value)
  if (found) {
    loadingRecord.value = false
    applyLoadedRecord(found)
    return
  }
  // Not in cache: fetch through the repository. Works in mock mode too — the
  // mock repository reads the in-memory seed directly.
  if (!import.meta.client) {
    loadingRecord.value = true
    return
  }
  loadingRecord.value = true
  notFound.value = false
  const record = await store.fetchOne(module.value.collection, recordId.value)
  if (generation !== loadGeneration) return
  loadingRecord.value = false
  if (record) {
    applyLoadedRecord(record)
    return
  }
  notFound.value = true
  model.value = emptyModuleRecord(module.value) as AppRecord
  originalModel.value = null
  applyRoleMatrix()
}

watch(
  [() => module.value?.path, recordId, isCreate, () => Boolean(module.value && store.get(module.value.collection, recordId.value))],
  () => { void load() },
  { immediate: true },
)

const title = computed(() => {
  if (!module.value) return ''
  if (isCreate.value) return t('app.ui.newEntity', { entity: moduleSingular(module.value) })
  const value = model.value[module.value.titleField]
  return module.value.collection === 'documentSequences'
    ? documentSequenceTypeLabel(value || moduleSingular(module.value))
    : String(value || moduleSingular(module.value))
})

watch([title, () => module.value, () => model.value.status], () => {
  if (!module.value) return
  setBreadcrumbs([
    { label: moduleTitle(module.value), to: module.value.path },
    { label: title.value },
  ])
  setBadges(model.value.status ? [{ label: String(model.value.status), color: statusColor(String(model.value.status)) }] : [])
}, { immediate: true })

onBeforeUnmount(clear)
usePageSeo({ title: () => title.value })

const related = computed(() => module.value && !isCreate.value ? store.related(module.value, model.value) : [])
const readOnly = computed(() => {
  if (!module.value) return true
  if (module.value.readOnly) return true
  if (module.value.collection === 'roles' && model.value.name === 'SuperAdmin') return true
  const prefix = module.value.permission.replace(/\.view$/, '')
  return !auth.canAccessPage(`${prefix}.${isCreate.value ? 'create' : 'edit'}`)
})
const canMutateRecord = computed(() => Boolean(module.value) && !readOnly.value && !isCreate.value && Boolean(model.value.id))
const canDeleteRecord = computed(() => {
  if (!module.value || isCreate.value || !model.value.id) return false
  if (module.value.collection === 'roles' && (model.value.isSystem || Number(model.value.userCount || 0) > 0)) return false
  return auth.canAccessPage(`${module.value.permission.replace(/\.view$/, '')}.delete`)
})
const deactivationOnly = computed(() => module.value?.group === 'master' || module.value?.collection === 'documentSequences')

const tabs = computed(() => {
  if (!module.value) return []
  const base = moduleDocumentTabs(module.value, {
    isCreate: isCreate.value,
    includeRelated: related.value.length > 0,
    readOnlyKeys: module.value.collection === 'documentSequences' && !isCreate.value
      ? ['documentType']
      : [],
  })
  if (module.value.collection !== 'documentSequences') return base
  const typeOptions = documentSequenceTypeOptions(store.list('documentSequences'))
  return base.map(tab => ({
    ...tab,
    sections: tab.sections.map(section => ({
      ...section,
      fields: section.fields.map((field) => {
        if (field.key !== 'documentType' || field.readOnly) return field
        return {
          ...field,
          type: 'select' as const,
          options: typeOptions,
          meta: { ...field.meta, creatable: true },
        }
      }),
    })),
  }))
})

watch(tabs, (value) => {
  if (!value.some(tab => tab.id === activeTab.value)) activeTab.value = value[0]?.id || 'general'
}, { immediate: true })

provide(moduleDocumentLineActionKey, () => {})

const moreItems = computed<DropdownMenuItem[][]>(() => {
  if (module.value?.collection === 'documentSequences') {
    if (!canMutateRecord.value) return []
    const active = String(model.value.status || '').toUpperCase() === 'ACTIVE'
    return [[{
      label: t(active ? 'core.rowActions.deactivate' : 'core.rowActions.activate'),
      icon: active ? 'i-lucide-circle-off' : 'i-lucide-circle-check',
      color: active ? 'warning' as const : 'success' as const,
      onSelect: () => { void setDocumentSequenceStatus(active ? 'INACTIVE' : 'ACTIVE') },
    }]]
  }

  if (module.value?.collection === 'users') {
    const items: DropdownMenuItem[] = []
    const active = String(model.value.status || '') === 'Active'
    if (canMutateRecord.value) {
      items.push({
        label: t(active ? 'core.rowActions.deactivate' : 'core.rowActions.activate'),
        icon: active ? 'i-lucide-circle-off' : 'i-lucide-circle-check',
        color: active ? 'warning' as const : 'success' as const,
        onSelect: () => { void setUserStatus(active ? 'Inactive' : 'Active') },
      })
    }
    if (canDeleteRecord.value) {
      items.push({
        label: t('app.ui.delete'),
        icon: 'i-lucide-trash-2',
        color: 'error' as const,
        onSelect: () => { void deleteRecord() },
      })
    }
    return items.length ? [items] : []
  }

  if (canDeleteRecord.value) {
    return [[{
      label: t(deactivationOnly.value ? 'app.ui.deactivate' : 'app.ui.delete'),
      icon: deactivationOnly.value ? 'i-lucide-circle-off' : 'i-lucide-trash-2',
      color: deactivationOnly.value ? 'warning' as const : 'error' as const,
      onSelect: () => { void deleteRecord() },
    }]]
  }
  return []
})

function setRolePermissions(rows: AppRolePermissionRow[]) {
  const normalized = normalizePermissionRows(rows)
  if (JSON.stringify(model.value.permissionRows || []) === JSON.stringify(normalized)) return
  model.value = {
    ...model.value,
    permissionRows: normalized,
    permissionCount: permissionRowsToFlatKeys(normalized).length,
  }
}

function setField(key: string, value: unknown) {
  const current = model.value[key]
  if (Object.is(current, value)) return
  if (key === 'roleId' && String(current ?? '') === String(value ?? '')) return
  model.value = { ...model.value, [key]: value } as AppRecord
  recalculate()
}

function fieldValue(key: string) {
  if (key === RELATED_FIELD_KEY) return related.value
  if (module.value?.tables?.some(table => table.key === key)) {
    return Array.isArray(model.value[key]) ? model.value[key] : []
  }
  return model.value[key]
}

function setFieldValue(key: string, value: unknown) {
  if (key === RELATED_FIELD_KEY) return
  if (key === 'permissionRows') {
    setRolePermissions(value as AppRolePermissionRow[])
    return
  }
  if (key === 'tags' || key === 'assignee' || key === 'attachments' || key === 'favorite') {
    setChromeField(key, value)
    return
  }
  if (module.value?.tables?.some(table => table.key === key) && Array.isArray(value)) {
    model.value = { ...model.value, [key]: value }
    return
  }
  setField(key, value)
}

function recalculate() {
  if (!module.value) return
  if (module.value.collection === 'documentSequences') {
    model.value = {
      ...model.value,
      prefix: String(model.value.prefix || '').trimStart(),
      nextNumberPreview: documentSequencePreview(model.value),
    }
  }
}

async function save() {
  if (!module.value || readOnly.value) return
  saving.value = true
  try {
    recalculate()
    const payload = { ...model.value }
    if (module.value.collection === 'documentSequences') {
      payload.documentType = normalizeDocumentSequenceType(payload.documentType)
      payload.prefix = String(payload.prefix || '').trim()
      const sequenceYear = Number(payload.year)
      const paddingLength = Number(payload.paddingLength)
      payload.year = Number.isInteger(sequenceYear) && sequenceYear >= 1000 && sequenceYear <= 9999 ? sequenceYear : null
      payload.paddingLength = paddingLength
      payload.status = String(payload.status || 'ACTIVE').toUpperCase()
      payload.nextNumberPreview = documentSequencePreview(payload)

      if (!payload.documentType) {
        toast.add({ title: 'Document type is required.', color: 'error' })
        return
      }
      if (!payload.prefix) {
        toast.add({ title: 'Prefix is required.', color: 'error' })
        return
      }
      if (!Number.isInteger(paddingLength) || paddingLength <= 0) {
        toast.add({ title: 'Padding Length must be a whole number greater than 0.', color: 'error' })
        return
      }
      if (!['ACTIVE', 'INACTIVE'].includes(String(payload.status))) {
        toast.add({ title: 'Status must be ACTIVE or INACTIVE.', color: 'error' })
        return
      }
      const duplicate = store.list('documentSequences').find(row =>
        String(row.id) !== String(payload.id || '')
        && normalizeDocumentSequenceType(row.documentType) === payload.documentType,
      )
      if (duplicate) {
        toast.add({
          title: 'A document sequence already exists for this document type.',
          description: documentSequenceTypeLabel(payload.documentType),
          color: 'error',
        })
        return
      }
    }
    const missing = module.value.fields.filter((field) => {
      if (isCreate.value && field.hideOnCreate) return false
      if (!isCreate.value && field.createOnly) return false
      return field.required && !field.computed && !String(payload[field.key] ?? '').trim()
    })
    if (missing.length) {
      toast.add({ title: t('app.ui.missingRequired'), description: missing.map(fieldLabel).join(', '), color: 'error' })
      return
    }
    if (module.value.collection === 'products') {
      // Spec §5.9 Pricing: the base UOM row's sale price is required > 0.
      // (It lives on the product record, edited from the Pricing tab.)
      if (!(Number(payload.salePrice ?? 0) > 0)) {
        toast.add({ title: t('app.stock.pricePositive'), color: 'error' })
        return
      }
      // Spec §2.1.3: unique Original UOMs (base row allowed, factor locked
      // at 1), factor > 0, sale price > 0, exactly one Default sale row; a
      // missing base row materializes so the product always keeps one
      // sellable UOM. Empty cost prices are derived (base cost × factor).
      const baseUom = store.list('uoms').find(uom => String(uom.id) === String(payload.uomId || ''))
      try {
        payload.uomConversions = normalizeUomConversions(
          payload.uomConversions,
          String(payload.uomId || ''),
          {
            baseCostPrice: payload.costPrice as number | undefined,
            baseSalePrice: payload.salePrice as number | undefined,
            baseUomSymbol: String(baseUom?.symbol || baseUom?.name || ''),
          },
        )
      }
      catch (error: unknown) {
        toast.add({
          title: t('app.stock.convInvalid'),
          description: error instanceof Error ? error.message : String(error),
          color: 'error',
        })
        return
      }
    }
    if (isCreate.value || !payload.id) {
      payload.createdAt ||= new Date().toISOString()
      payload.createdBy ||= String(currentUser.value?.name || 'Current User')
      payload.status ||= 'Active'
      payload.currency ||= 'USD'
    }
    await (isCreate.value || !payload.id
      ? store.createRemote(module.value.collection, payload)
      : store.updateRemote(module.value.collection, String(payload.id), payload))
    toast.add({ title: t('core.common.saved'), color: 'success' })
    await navigateTo(module.value.path)
  }
  catch {
    // useApi already surfaced the API error
  }
  finally {
    saving.value = false
  }
}

async function setDocumentSequenceStatus(status: 'ACTIVE' | 'INACTIVE') {
  if (module.value?.collection !== 'documentSequences' || !canMutateRecord.value) return
  saving.value = true
  try {
    model.value = await store.updateRemote(module.value.collection, String(model.value.id), { status }) as AppRecord
    originalModel.value = { ...model.value }
    toast.add({ title: t(status === 'ACTIVE' ? 'core.common.activated' : 'core.common.deactivated'), color: 'success' })
  }
  finally {
    saving.value = false
  }
}

async function setUserStatus(status: 'Active' | 'Inactive') {
  if (module.value?.collection !== 'users' || !canMutateRecord.value) return
  saving.value = true
  try {
    model.value = await store.updateRemote(module.value.collection, String(model.value.id), { status }) as AppRecord
    originalModel.value = { ...model.value }
    toast.add({ title: t(status === 'Active' ? 'core.common.activated' : 'core.common.deactivated'), color: 'success' })
  }
  finally {
    saving.value = false
  }
}

async function deleteRecord() {
  if (!module.value || !canDeleteRecord.value) return
  if (deactivationOnly.value) {
    saving.value = true
    try {
      const status = module.value.collection === 'documentSequences' ? 'INACTIVE' : 'Inactive'
      model.value = await store.updateRemote(module.value.collection, String(model.value.id), { status }) as AppRecord
      toast.add({ title: t('app.ui.recordDeactivated'), color: 'success' })
    }
    finally {
      saving.value = false
    }
    return
  }
  const ok = await confirm({ kind: 'delete', count: 1 })
  if (!ok) return
  await store.deleteRemote(module.value.collection, [String(model.value.id)])
  toast.add({ title: t('core.actions.deletedItems', { n: 1 }), color: 'success' })
  await navigateTo(module.value.path)
}
</script>

<template>
  <template v-if="module">
    <DocumentAppDocumentPage
      :tabs="tabs"
      :active-tab="activeTab"
      :field-value="fieldValue"
      :set-field-value="setFieldValue"
      :pending="loadingRecord"
      :not-found="notFound"
      :saving="saving"
      :read-only="readOnly"
      :can-save="!readOnly && !notFound && !loadingRecord"
      :is-create="isCreate"
      :confirm-save="true"
      :show-cancel="false"
      :show-tabs="tabs.length > 1"
      show-list-nav
      content-wide
      :can-navigate-previous="canNavigatePrevious"
      :can-navigate-next="canNavigateNext"
      :list-to="listTo"
      :attachments="attachments"
      :current-user="currentUser"
      :meta-title="title"
      :meta-subtitle="moduleSingular(module)"
      :meta-icon="module.icon"
      :meta-status="String(model.status || '')"
      :meta-owner="metaOwner"
      :meta-assignee="metaAssignee"
      :meta-tags="tags"
      :meta-created-at="String(model.createdAt || '')"
      :meta-updated-at="String(model.updatedAt || '')"
      :more-items="moreItems"
      :can-export="false"
      @update:active-tab="activeTab = $event"
      @update:attachments="setChromeField('attachments', $event)"
      @save="save()"
      @refresh="() => { void load() }"
      @navigate-previous="navigatePrevious"
      @navigate-next="navigateNext"
    />
  </template>
  <div v-else class="p-6 text-sm text-muted">{{ t('core.states.notFound') }}</div>
</template>
