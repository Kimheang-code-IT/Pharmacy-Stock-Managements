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
import { apiErrorMessage, isApiErrorHandled } from '~/utils/api/errors'
import { clearPublishedFieldErrors } from '~/composables/useFormErrors'
import {
  canHardDeleteRecord,
  isRecordInactive,
  statusValueFor,
  supportsStatusToggle,
} from '~/utils/module/row-actions'
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
  metaOwner,
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
  // Not in cache: fetch through the repository.
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

/**
 * The product document renders store-backed reference lists (Pricing UOM
 * picker, base UOM label). The list page loads them; a direct detail URL must
 * too, otherwise those selects fall back to raw ids.
 */
watch(
  () => module.value?.collection,
  (collection) => {
    if (!import.meta.client || collection !== 'products') return
    void store.fetchList('uoms')
    void store.fetchList('categories')
  },
  { immediate: true },
)

const related = computed(() => module.value && !isCreate.value ? store.related(module.value, model.value) : [])
/** Exact backend code for a document action (falls back to `{module}.{action}`). */
function moduleActionPermission(action: 'create' | 'edit' | 'delete'): string {
  const moduleConfig = module.value
  if (!moduleConfig) return ''
  const explicit = moduleConfig.actionPermissions?.[action]
  if (explicit) return explicit
  const prefix = moduleConfig.permission.replace(/\.(view|manage|access)$/, '')
  return prefix === moduleConfig.permission ? '' : `${prefix}.${action}`
}
const readOnly = computed(() => {
  if (!module.value) return true
  if (module.value.readOnly) return true
  // System Administrator keeps full access locked in the matrix, but the
  // signed-in super-admin can still edit description / other non-permission fields.
  return !auth.canAccessPage(moduleActionPermission(isCreate.value ? 'create' : 'edit'))
})
const canMutateRecord = computed(() => Boolean(module.value) && !readOnly.value && !isCreate.value && Boolean(model.value.id))
const canDeleteRecord = computed(() => {
  if (!module.value || isCreate.value || !model.value.id) return false
  if (!canHardDeleteRecord(module.value.collection, model.value.status)) return false
  if (module.value.collection === 'roles' && (model.value.isSystem || Number(model.value.userCount || 0) > 0)) return false
  return auth.canAccessPage(moduleActionPermission('delete'))
})

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
  const collection = module.value?.collection
  const items: DropdownMenuItem[] = []
  if (canMutateRecord.value && supportsStatusToggle(collection)) {
    const inactive = isRecordInactive(model.value.status)
    items.push(inactive
      ? {
          label: t('core.rowActions.activate'),
          icon: 'i-lucide-circle-check',
          color: 'success' as const,
          onSelect: () => { void setRecordStatus(true) },
        }
      : {
          label: t('core.rowActions.deactivate'),
          icon: 'i-lucide-circle-off',
          color: 'warning' as const,
          onSelect: () => { void setRecordStatus(false) },
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
  // Batches tab: the panel needs the whole record (product id, UOM, barcode).
  if (key === '__record') return model.value
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
  // Fresh attempt: drop errors from the previous submit.
  clearPublishedFieldErrors()
  saving.value = true
  try {
    recalculate()
    let payload = { ...model.value }
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
      // Batch tracking, expiry tracking and FIFO are always on system-wide
      // (the Stock Costing toggles are not shown), so stamp them on save.
      payload = { ...payload, trackBatch: true, trackExpiry: true, expiryTracking: true, fifo: true }
      // The Pricing tab (base-UOM sale price > 0 + UOM conversions) is hidden on
      // create and appears once the product is opened, so only validate and
      // normalize pricing when editing an existing product.
      if (!isCreate.value) {
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
          if (!isApiErrorHandled(error)) {
            toast.add({
              title: t('app.stock.convInvalid'),
              description: apiErrorMessage(error, t('app.stock.convInvalid')),
              color: 'error',
            })
          }
          return
        }
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
    clearPublishedFieldErrors()
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

async function setRecordStatus(active: boolean) {
  if (!module.value || !canMutateRecord.value || saving.value) return
  const ok = await confirm({ kind: active ? 'activate' : 'deactivate' })
  if (!ok) return
  saving.value = true
  try {
    const status = statusValueFor(module.value.collection, active)
    model.value = await store.updateRemote(module.value.collection, String(model.value.id), { status }) as AppRecord
    originalModel.value = { ...model.value }
    toast.add({ title: t(active ? 'core.common.activated' : 'core.common.deactivated'), color: 'success' })
  }
  finally {
    saving.value = false
  }
}

async function deleteRecord() {
  if (!module.value || !canDeleteRecord.value || saving.value) return
  if (!canHardDeleteRecord(module.value.collection, model.value.status)) {
    toast.add({ title: t('core.rowActions.deactivateBeforeDelete'), color: 'warning' })
    return
  }
  const ok = await confirm({
    kind: 'delete',
    titleKey: 'core.confirm.deleteTitle',
    description: t('core.actions.deleteConfirmNamed', { name: title.value }),
    confirmLabelKey: 'core.rowActions.delete',
    confirmColor: 'error',
  })
  if (!ok) return
  saving.value = true
  try {
    await store.deleteRemote(module.value.collection, [String(model.value.id)])
    toast.add({ title: t('core.actions.deletedItems', { n: 1 }), color: 'success' })
    await navigateTo(module.value.path)
  }
  catch (error: unknown) {
    if (!isApiErrorHandled(error)) {
      toast.add({
        title: apiErrorMessage(error, t('app.ui.deleteFailed')),
        color: 'error',
      })
    }
  }
  finally {
    saving.value = false
  }
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
      :meta-title="title"
      :meta-subtitle="moduleSingular(module)"
      :meta-icon="module.icon"
      :meta-owner="metaOwner"
      :meta-created-at="String(model.createdAt || '')"
      :meta-updated-at="String(model.updatedAt || '')"
      :more-items="moreItems"
      :can-export="false"
      @update:active-tab="activeTab = $event"
      @save="save()"
      @refresh="() => { void load() }"
      @navigate-previous="navigatePrevious"
      @navigate-next="navigateNext"
    />
  </template>
  <div v-else class="p-6 text-sm text-muted">{{ t('core.states.notFound') }}</div>
</template>
