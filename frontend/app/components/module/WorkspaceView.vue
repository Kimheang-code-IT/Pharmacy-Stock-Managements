<script setup lang="ts">
import type { DropdownMenuItem, TableColumn, TableRow } from '@nuxt/ui'
import type { PaginationState } from '@tanstack/vue-table'
import { h } from 'vue'
import { TableAppTableCellImage, UBadge, ULink } from '#components'
import { useAppHeader } from '~/composables/layout/useAppHeader'
import { useConfirm } from '~/composables/common/useConfirm'
import { usePageSeo } from '~/composables/usePageSeo'
import {
  formatModuleCell,
  moduleStatusBadge,
  useModuleLabel,
  useModuleRoute,
} from '~/composables/module/useModule'
import { useAppLocalization } from '~/composables/settings/useAppLocalization'
import type { AppRecord } from '~/config/admin-seed'
import { appModules, type ModuleSelectOption } from '~/config/modules'
import { isDateFieldKey, isDateTimeFieldKey, isMoneyKey, isNumericKey } from '~/utils/module/field-keys'
import { limitFilterSelects, parseFilterQuery } from '~/utils/filter/values'
import { documentDetailHrefFor, documentLinkTargetFor } from '~/utils/module/document-links'
import { isFilterValueActive } from '~/utils/filter/select-ui'
import { listTableRowMetaColumn, listTableSelectColumn } from '~/utils/table/list-columns'
import { listTablePageSummary, listTableSelectedIds } from '~/utils/table/list-table'
import { documentSequenceTypeLabel } from '~/utils/document-sequences'
import { normalizeAuditLog, resolveAuditEntityPath } from '~/utils/module/audit-logs'
import {
  canHardDeleteRecord,
  isRecordInactive,
  statusValueFor,
  supportsStatusToggle,
} from '~/utils/module/row-actions'
import { openDebts, selectedDebtsShareScope } from '~/utils/reports/debts'
import { apiErrorMessage, isApiErrorHandled } from '~/utils/api/errors'
import { deliveryStatusOf } from '~/utils/delivery/notes'
import { downloadTableExport } from '~/utils/export/table'
import { fetchAllListRows } from '~/utils/export/fetch-all'
import type { ExportFieldOption, ExportRequest } from '~/types/stock-pos/export'
import { useDeliveryCommands, useEntityRepository, usePosCommands } from '~/repositories/index'
import { productImageUrl } from '~/utils/pos/cart'
import { STOCK_OPERATION_META, STOCK_OPERATION_PERMISSIONS, STOCK_OPERATION_TYPES, type StockHistoryKind, type StockOperationType } from '~/config/pos-options'
import type { DebtPaymentKind } from '~/components/reports/DebtPaymentDialog.vue'

const { module, route } = useModuleRoute()
const store = useAppDataStore()
const auth = useAuthStore()
const { t } = useI18n()
const { fieldLabel, moduleTitle, moduleSingular } = useModuleLabel()
const { setTitle, setBreadcrumbs, clear } = useAppHeader()
const { confirm } = useConfirm()
const toast = useToast()
const posCommands = usePosCommands()
const deliveryCommands = useDeliveryCommands()
const entityRepository = useEntityRepository()
const { localization } = useAppLocalization()

const q = ref('')
/** Debounced copy of the search box: the list filters instantly (in-memory)
 *  but the server refetch waits so typing does not fire one request per key. */
const debouncedQ = ref('')
const applyDebouncedQ = useDebounceFn((value: string) => { debouncedQ.value = value }, 300)
watch(q, (value) => { applyDebouncedQ(value) })
const pagination = ref<PaginationState>({ pageIndex: 0, pageSize: 20 })
const filters = reactive<Record<string, string[]>>({})
const rowSelection = ref<Record<string, boolean>>({})
const busyId = ref('')
const exporting = ref(false)
const preferences = usePreferencesStore()
const stockOperationOpen = ref(false)
const stockOperationType = ref<StockOperationType>('stock_in')
const stockOperationProduct = ref('')
const stockOperationQuantity = ref<number | undefined>()
const stockOperationNote = ref('')
const stockOperationBusy = ref(false)
const dateFrom = ref('')
const dateTo = ref('')
const debtPayOpen = ref(false)
const debtPayKind = ref<DebtPaymentKind>('customer')
const debtPayRow = ref<AppRecord | null>(null)
const debtPayBusy = ref(false)
const debtSelectedOpen = ref(false)
const debtSelectedKind = ref<DebtPaymentKind>('customer')
const debtSelectedRows = ref<AppRecord[]>([])

const current = computed(() => module.value)
const pending = computed(() => Boolean(current.value && store.isLoading(current.value.collection)))
const isTableOnly = computed(() => Boolean(current.value?.tableOnly))
/** Table-only debt reports still support checkbox selection (multi-pay). */
const supportsSelection = computed(() =>
  !isTableOnly.value
  || current.value?.collection === 'customerDebts'
  || current.value?.collection === 'supplierDebts',
)
/** Table-only reports that still need row actions (Edit / Pay). */
const showRowActions = computed(() => {
  if (!isTableOnly.value) return true
  const collection = current.value?.collection
  if (collection === 'sales') return canEditSale.value
  if (collection === 'stockIns') return canEditPurchase.value
  if (collection === 'customerDebts') return true
  if (collection === 'supplierDebts') return true
  return false
})
/** Exact backend permission code for a mutation action (falls back to the
 *  legacy `{module}.{action}` shape when a module has no explicit code). */
function actionPermission(action: 'create' | 'edit' | 'delete' | 'operate'): string {
  const module = current.value
  if (!module) return ''
  const explicit = module.actionPermissions?.[action]
  if (explicit) return explicit
  if (action === 'create' && module.createPermission) return module.createPermission
  const prefix = module.permission.replace(/\.(view|manage|access)$/, '')
  return prefix === module.permission ? '' : `${prefix}.${action}`
}
const canCreate = computed(() => Boolean(
  current.value?.canCreate
  && auth.canAccessPage(actionPermission('create')),
))
const canEdit = computed(() => Boolean(
  current.value
  && !current.value.readOnly
  && auth.canAccessPage(actionPermission('edit')),
))
const canDelete = computed(() => Boolean(
  current.value
  && !current.value.readOnly
  && auth.canAccessPage(actionPermission('delete')),
))
// Product row stock actions (Purchase Stock / Damage) are each gated by their
// own backend permission (`stock.*`), not by `product.update`.
const canOperate = computed(() => Boolean(
  current.value
  && !current.value.readOnly
  && (auth.canAccessPage(STOCK_OPERATION_PERMISSIONS.stock_in)
    || auth.canAccessPage(STOCK_OPERATION_PERMISSIONS.damage)),
))
// Editing a sale reuses the POS screen (PATCH /pos/sales/{id}); editing a
// purchase reuses the purchase entry screen (PATCH /stock/in/{id}).
const canEditSale = computed(() =>
  auth.canAccessPage('pos.access'),
)
const canEditPurchase = computed(() =>
  auth.canAccessPage('stock.in'),
)
const canPayCustomerDebt = computed(() =>
  auth.canAccessPage('customer.debt.pay')
  || auth.canAccessPage('report.customer_debt'),
)
const canPaySupplierDebt = computed(() =>
  auth.canAccessPage('supplier.debt.pay')
  || auth.canAccessPage('report.supplier_debt'),
)
/** Delivery table: mark a Processing note Completed (POST /delivery/{id}/status). */
const canDeliver = computed(() => auth.canAccessPage('delivery.deliver'))
/** Bulk toolbar: deactivate is offered wherever a status toggle is supported. */
const canBulkDeactivate = computed(() => Boolean(
  current.value
  && canEdit.value
  && supportsStatusToggle(current.value.collection),
))
const dateField = computed(() => {
  const fields = current.value?.fields || []
  return fields.find(field => field.type === 'date' || field.type === 'datetime' || field.key === 'date' || /date$/i.test(field.key))?.key
    || current.value?.columns.find(column => /date/i.test(column.key))?.key
})

const result = computed(() => {
  if (!current.value) return { rows: [], total: 0, all: [] }
  const queried = store.query(current.value, {
    q: q.value,
    filters,
    paginate: false,
    dateField: dateField.value,
    dateFrom: dateFrom.value,
    dateTo: dateTo.value,
  })
  if (current.value.collection === 'products') {
    const all = queried.all.map(row => ({
      ...row,
      stockInQty: stockTotalsByProduct.value.get(String(row.id))?.stockIn ?? 0,
      stockOutQty: stockTotalsByProduct.value.get(String(row.id))?.stockOut ?? 0,
      damageQty: stockTotalsByProduct.value.get(String(row.id))?.damage ?? 0,
      uom: String(row.uom || uomLookup.value.get(String(row.uomId))?.name || ''),
      uomSymbol: String(row.uomSymbol || uomLookup.value.get(String(row.uomId))?.symbol || ''),
      brand: String(row.brand || brandLookup.value.get(String(row.brandId))?.name || ''),
    }))
    return { rows: all, total: queried.total, all }
  }
  if (current.value.collection === 'brands') {
    const all = queried.all.map(row => ({
      ...row,
      productCount: brandProductCounts.value.get(String(row.id)) ?? 0,
    }))
    return { rows: all, total: queried.total, all }
  }
  if (current.value.collection === 'uoms') {
    const all = queried.all.map(row => ({
      ...row,
      productCount: uomProductCounts.value.get(String(row.id)) ?? 0,
    }))
    return { rows: all, total: queried.total, all }
  }
  // Debt reports list outstanding balances only: once a debt is paid in full
  // it leaves the table instead of lingering as a settled row.
  if (current.value.collection === 'customerDebts' || current.value.collection === 'supplierDebts') {
    const all = openDebts(queried.all)
    return { rows: all, total: all.length, all }
  }
  return queried
})

/** UOM lookup for product display enrichment (O(1) — was O(n) per row). */
const uomLookup = computed(() =>
  new Map(store.list('uoms').map(uom => [String(uom.id), uom])))

/** Brand lookup for product display enrichment (O(1) — was O(n) per row). */
const brandLookup = computed(() =>
  new Map(store.list('brands').map(brand => [String(brand.id), brand])))

/** Products linked to each brand â€” used to keep the brand list informative. */
const brandProductCounts = computed(() => {
  const counts = new Map<string, number>()
  for (const row of store.list('products')) {
    const brandId = String(row.brandId ?? '')
    if (!brandId) continue
    counts.set(brandId, (counts.get(brandId) || 0) + 1)
  }
  return counts
})

/** Products linked to each UOM â€” used to keep the UOM list informative. */
const uomProductCounts = computed(() => {
  const counts = new Map<string, number>()
  for (const row of store.list('products')) {
    const uomId = String(row.uomId ?? '')
    if (!uomId) continue
    counts.set(uomId, (counts.get(uomId) || 0) + 1)
  }
  return counts
})

/** Movement labels that increase stock (Stock In, returns, positive adjustments). */
const STOCK_IN_LABELS = new Set(['Stock In', 'Sale Return', 'Adjustment Increase'])
/** Movement labels that decrease stock (sales, purchase returns, negative adjustments). */
const STOCK_OUT_LABELS = new Set(['Sale', 'Purchase Return', 'Adjustment Decrease'])
/** Loss labels tracked separately from trading stock-out. */
const DAMAGE_LABELS = new Set(['Damage', 'Expiry'])

/** Per-product movement aggregates for the Stock list quantity columns. */
const stockTotalsByProduct = computed(() => {
  const totals = new Map<string, { stockIn: number, stockOut: number, damage: number }>()
  for (const row of store.list('stockMovements')) {
    const productId = String(row.productId ?? '')
    if (!productId) continue
    const entry = totals.get(productId) || { stockIn: 0, stockOut: 0, damage: 0 }
    const qty = Number(row.quantity || 0)
    const type = String(row.type ?? '')
    if (STOCK_IN_LABELS.has(type)) entry.stockIn += Math.abs(qty)
    else if (STOCK_OUT_LABELS.has(type)) entry.stockOut += Math.abs(qty)
    else if (DAMAGE_LABELS.has(type)) entry.damage += Math.abs(qty)
    totals.set(productId, entry)
  }
  return totals
})

/** Quantity column â†’ history dialog movement-kind filter.
 *  Current Stock (`quantity`) is display-only â€” it never opens the dialog. */
const STOCK_QTY_KIND: Record<string, StockHistoryKind> = {
  stockInQty: 'stock_in',
  stockOutQty: 'stock_out',
  damageQty: 'damage',
}

const stockHistoryOpen = ref(false)
const stockHistoryProduct = ref<AppRecord | null>(null)
const stockHistoryKind = ref<StockHistoryKind>('stock_in')
const stockHistoryReloadKey = ref(0)

function openStockHistory(row: Record<string, unknown>, kind: StockHistoryKind) {
  stockHistoryProduct.value = row as AppRecord
  stockHistoryKind.value = kind
  stockHistoryOpen.value = true
}

function onStockHistorySaved() {
  void store.fetchList('products')
  void store.fetchList('stockMovements')
  stockHistoryReloadKey.value += 1
}

const selectedIds = computed(() => listTableSelectedIds(rowSelection.value))
/** Selected open debt rows on the customer/supplier debt reports. */
const selectedDebtRows = computed<AppRecord[]>(() => {
  const collection = current.value?.collection
  if (collection !== 'customerDebts' && collection !== 'supplierDebts') return []
  const ids = new Set(selectedIds.value)
  return result.value.all.filter(row => ids.has(String(row.id)) && Number(row.remainingAmount || 0) > 0)
})
const canPaySelectedDebts = computed(() => {
  if (!selectedDebtRows.value.length) return false
  return current.value?.collection === 'customerDebts' ? canPayCustomerDebt.value : canPaySupplierDebt.value
})

const hasActiveFilters = computed(() => Boolean(
  Object.values(filters).some(value => isFilterValueActive(value))
  || isFilterValueActive(dateFrom.value)
  || isFilterValueActive(dateTo.value),
))

/** Optional document-currency filter of the debt reports (server-side too). */
const currencyFilter = computed(() => parseFilterQuery(filters.currency)[0] || '')
const isDebtReport = computed(() =>
  current.value?.collection === 'customerDebts' || current.value?.collection === 'supplierDebts',
)

const visibleFilters = computed(() => limitFilterSelects(
  current.value?.filters || [],
  Boolean(dateField.value),
  filter => filter.key === 'status' || filter.key === 'workflowStatus',
))

watch(current, (value) => {
  if (!value) return
  setTitle(moduleTitle(value))
  setBreadcrumbs([{ label: moduleTitle(value) }])
  rowSelection.value = {}
  // Cross-document links land here with ?q=<document no> so the linked
  // document is pre-filtered in the list (e.g. Customer Debt â†’ Sales Report).
  const searchQuery = route.query.q
  q.value = typeof searchQuery === 'string' ? searchQuery : ''
  for (const key of Object.keys(filters)) Reflect.deleteProperty(filters, key)
  for (const filter of value.filters || []) {
    filters[filter.key] = parseFilterQuery(route.query[filter.key])
  }
}, { immediate: true })

onBeforeUnmount(clear)

usePageSeo({
  title: () => current.value ? moduleTitle(current.value) : t('app.pages.dashboard'),
})

watch([q, filters, dateFrom, dateTo], () => {
  rowSelection.value = {}
  pagination.value = { ...pagination.value, pageIndex: 0 }
}, { deep: true })

// Client-only: reload list data after mount and when filters change. Loading
// and error state stays repository-driven.
function reloadModuleData() {
  if (!import.meta.client || !current.value) return
  void store.fetchList(current.value.collection, {
    q: debouncedQ.value || undefined,
    startDate: dateFrom.value || undefined,
    endDate: dateTo.value || undefined,
    currency: isDebtReport.value && currencyFilter.value ? currencyFilter.value : undefined,
  })
  if (current.value.collection === 'products') {
    void store.fetchList('stockMovements')
    void store.fetchList('uoms')
    void store.fetchList('brands')
  }
  if (current.value.collection === 'uoms') void store.fetchList('products')
  if (current.value.collection === 'brands') void store.fetchList('products')
  // Debt reports: the export dialog needs the party/user option lists. These
  // follow the module permission; a missing grant silently yields no options.
  if (current.value.collection === 'customerDebts' && auth.canAccessPage('customer.view')) {
    void store.fetchList('customers')
  }
  if (current.value.collection === 'supplierDebts' && auth.canAccessPage('supplier.view')) {
    void store.fetchList('suppliers')
  }
  if (isDebtReport.value && auth.canAccessPage('user.view')) {
    void store.fetchList('users')
  }
}

onMounted(() => {
  reloadModuleData()
})

watch([current, debouncedQ, dateFrom, dateTo], () => {
  reloadModuleData()
})

// The debt-report currency filter is applied server-side too, so refetch when
// it changes (other toolbar filters stay client-side).
watch(currencyFilter, () => reloadModuleData())

function recordPath(id: unknown) {
  if (!current.value) return '/'
  return `${current.value.path}/${id}`
}

function fieldTypeForKey(key: string) {
  return current.value?.fields.find(field => field.key === key)?.type
}

function cellText(row: Record<string, unknown>, key: string) {
  const source = current.value?.collection === 'auditLogs' ? normalizeAuditLog(row as AppRecord) : row
  if (current.value?.collection === 'documentSequences' && key === 'documentType') {
    const code = String(source[key] || '')
    const label = documentSequenceTypeLabel(code)
    return label === code ? code : `${label} (${code})`
  }
  return formatModuleCell(
    source[key],
    key,
    isMoneyKey(key) ? String(source.currency || preferences.currency) : undefined,
    fieldTypeForKey(key),
  )
}

function auditEntityLinkFor(row: Record<string, unknown>) {
  if (current.value?.collection !== 'auditLogs') return ''
  return resolveAuditEntityPath(
    normalizeAuditLog(row as AppRecord),
    appModules,
    collection => store.list(collection),
    permission => auth.canAccessPage(permission),
  )
}

const pageSummary = computed(() =>
  listTablePageSummary(t, result.value.total, pagination.value),
)

/** Export dialog fields = the module's visible columns (label + key). */
const exportFieldOptions = computed(() =>
  (current.value?.columns || []).map(column => ({ label: fieldLabel(column), value: column.key })))

/** Classify a column so PDF/Excel align and total it correctly. */
function exportColumnType(column: { key: string, type?: string }): 'text' | 'number' | 'money' | 'date' {
  if (
    column.type === 'date' || column.type === 'datetime'
    || isDateFieldKey(column.key) || isDateTimeFieldKey(column.key)
  ) return 'date'
  if (isMoneyKey(column.key)) return 'money'
  if (isNumericKey(column.key)) return 'number'
  return 'text'
}

/** Debt report party side: Customer Debt exports one customer, Supplier one supplier. */
const debtPartyType = computed<'customer' | 'supplier' | null>(() => {
  const collection = current.value?.collection
  if (collection === 'customerDebts') return 'customer'
  if (collection === 'supplierDebts') return 'supplier'
  return null
})

const exportPartyLabel = computed(() => debtPartyType.value === 'supplier'
  ? t('app.modules.supplierDebts.fields.supplier')
  : t('app.modules.customerDebts.fields.customer'))

const exportUserLabel = computed(() => t('app.fields.user'))

/** De-duplicate option lists (id → label), dropping empty values. */
function dedupeExportOptions(options: ExportFieldOption[]): ExportFieldOption[] {
  const seen = new Set<string>()
  const out: ExportFieldOption[] = []
  for (const option of options) {
    const value = option.value.trim()
    const label = option.label.trim()
    if (!value || !label || seen.has(value)) continue
    seen.add(value)
    out.push({ label, value })
  }
  return out.sort((a, b) => a.label.localeCompare(b.label))
}

/** Party options for the debt export dialog (loaded records + rows on screen). */
const exportPartyOptions = computed<ExportFieldOption[]>(() => {
  const type = debtPartyType.value
  if (!type) return []
  const fromStore = type === 'customer'
    ? store.list('customers').map(row => ({ label: String(row.name || ''), value: String(row.id || '') }))
    : store.list('suppliers').map(row => ({ label: String(row.name || ''), value: String(row.id || '') }))
  const fromRows = (result.value.all as unknown as Record<string, unknown>[]).map(row => type === 'customer'
    ? { label: String(row.customer || ''), value: String(row.customerId || '') }
    : { label: String(row.supplier || ''), value: String(row.supplierId || '') })
  return dedupeExportOptions([...fromStore, ...fromRows])
})

/** Staff-user options for the debt export dialog (loaded users + rows on screen). */
const exportUserOptions = computed<ExportFieldOption[]>(() => {
  if (!isDebtReport.value) return []
  const fromStore = store.list('users').map(row => ({
    label: String(row.displayName || row.name || row.username || row.email || ''),
    value: String(row.id || ''),
  }))
  const fromRows = (result.value.all as unknown as Record<string, unknown>[])
    .map(row => ({ label: String(row.user || ''), value: String(row.userId || '') }))
  return dedupeExportOptions([...fromStore, ...fromRows])
})

/**
 * Debt export rows: fetch EVERY document matching the dialog filters (date
 * range + party + user) from the backend, not just the page cached on screen.
 */
async function fetchDebtExportRows(request: ExportRequest): Promise<Record<string, unknown>[]> {
  const collection = current.value?.collection
  if (!collection) return []
  const partyType = debtPartyType.value
  const query = {
    q: debouncedQ.value || undefined,
    startDate: request.startDate || dateFrom.value || undefined,
    endDate: request.endDate || dateTo.value || undefined,
    currency: currencyFilter.value || undefined,
    customerId: partyType === 'customer' ? (request.partyId || undefined) : undefined,
    supplierId: partyType === 'supplier' ? (request.partyId || undefined) : undefined,
    userId: request.userId || undefined,
  }
  return fetchAllListRows<Record<string, unknown>>(async ({ page, limit }) => {
    const pageResult = await entityRepository.list(collection, { ...query, page, limit })
    return {
      items: pageResult.items as unknown as Record<string, unknown>[],
      total: pageResult.meta?.total ?? null,
    }
  })
}

/** Excel/PDF export: the Python backend renders the page's filtered rows. */
async function onExport(request: ExportRequest) {
  const module = current.value
  if (!module || exporting.value) return
  exporting.value = true
  try {
    const codes = request.fieldCodes?.length ? request.fieldCodes : module.columns.map(column => column.key)
    const columns = module.columns
      .filter(column => codes.includes(column.key))
      .map(column => ({ key: column.key, label: fieldLabel(column), type: exportColumnType(column) }))
    if (!columns.length) {
      toast.add({ title: t('core.exportDialog.fieldRequired'), color: 'warning' })
      return
    }

    // Debt reports: the export dialog filters drive a full backend fetch.
    let rows: Record<string, unknown>[]
    if (isDebtReport.value) {
      rows = await fetchDebtExportRows(request)
    }
    else {
      rows = result.value.all as unknown as Record<string, unknown>[]
      if (request.scope === 'selected') {
        const selected = new Set(Object.keys(rowSelection.value).filter(id => rowSelection.value[id]))
        rows = rows.filter(row => selected.has(String(row.id)))
      }
      else if (request.scope === 'current_page') {
        const start = pagination.value.pageIndex * pagination.value.pageSize
        rows = rows.slice(start, start + pagination.value.pageSize)
      }
      // The export dialog's range narrows the already search/date-filtered rows.
      if (dateField.value && (request.startDate || request.endDate)) {
        const key = dateField.value
        rows = rows.filter((row) => {
          const value = String(row[key] ?? '').slice(0, 10)
          if (!value) return false
          if (request.startDate && value < request.startDate) return false
          if (request.endDate && value > request.endDate) return false
          return true
        })
      }
    }

    const exportRows = rows.map((row) => {
      const out: Record<string, unknown> = {}
      for (const column of columns) {
        const value = row[column.key]
        if (column.type === 'date') {
          // Send ISO so Excel writes real dates and PDF formats consistently.
          out[column.key] = String(value ?? '').slice(0, 10)
        }
        else if (column.type === 'money' || column.type === 'number') {
          const numeric = Number(value)
          out[column.key] = Number.isFinite(numeric) ? numeric : cellText(row, column.key)
        }
        else {
          out[column.key] = cellText(row, column.key)
        }
      }
      return out
    })

    await downloadTableExport({
      title: moduleTitle(module),
      format: request.format,
      columns,
      rows: exportRows,
      subtitle: request.startDate || request.endDate
        ? `${request.startDate || '…'} → ${request.endDate || '…'}`
        : null,
    })
    toast.add({ title: t('core.exportDialog.exported', { n: exportRows.length }), color: 'success' })
  }
  catch (error: unknown) {
    if (!isApiErrorHandled(error)) {
      toast.add({
        title: t('core.exportDialog.exportFailed'),
        description: apiErrorMessage(error, t('core.exportDialog.exportFailed')),
        color: 'error',
      })
    }
  }
  finally {
    exporting.value = false
  }
}

function rowMenuItems(row: Record<string, unknown>): DropdownMenuItem[][] {
  const collection = current.value?.collection
  if (collection === 'sales') {
    if (!canEditSale.value) return []
    return [[{
      label: t('app.reports.edit'),
      icon: 'i-lucide-pencil',
      color: 'primary',
      // Edit reuses the POS screen with the invoice loaded (PATCH on save).
      onSelect: () => {
        void navigateTo(`/pos?editSaleId=${encodeURIComponent(String(row.id || ''))}`)
      },
    }, {
      // Customer cancels the invoice: load it into the POS return flow with
      // every line and restock enabled, so all items go back to stock.
      label: t('app.reports.returnAll'),
      icon: 'i-lucide-undo-2',
      color: 'warning',
      onSelect: () => {
        void navigateTo(`/pos?returnSaleId=${encodeURIComponent(String(row.id || ''))}`)
      },
    }]]
  }
  if (collection === 'stockIns') {
    if (!canEditPurchase.value) return []
    const purchaseNo = String(row.purchaseNo || '')
    return [[{
      label: t('app.reports.edit'),
      icon: 'i-lucide-pencil',
      color: 'primary',
      // Edit reuses the Purchase screen with the document loaded (PATCH on save).
      onSelect: () => {
        void navigateTo(`/reports/purchases/new?editPurchaseId=${encodeURIComponent(String(row.id || ''))}&purchaseNo=${encodeURIComponent(purchaseNo)}`)
      },
    }, {
      // Return goods to the supplier: reverses the stock-in (stock decreases).
      label: t('app.reports.returnAll'),
      icon: 'i-lucide-undo-2',
      color: 'warning',
      onSelect: () => {
        void navigateTo(`/reports/purchases/new?returnPurchaseId=${encodeURIComponent(String(row.id || ''))}&purchaseNo=${encodeURIComponent(purchaseNo)}`)
      },
    }]]
  }
  if (collection === 'customerDebts' || collection === 'supplierDebts') {
    const isCustomer = collection === 'customerDebts'
    const kind: DebtPaymentKind = isCustomer ? 'customer' : 'supplier'
    const debtRow = row as AppRecord
    const canPay = isCustomer ? canPayCustomerDebt.value : canPaySupplierDebt.value
    if (!canPay) return []
    // Debt surfaces expose the payment dialog only.
    return [[{
      label: t('app.reports.pay'),
      icon: 'i-lucide-hand-coins',
      color: 'success',
      disabled: Number(debtRow.remainingAmount || 0) <= 0,
      onSelect: () => openDebtPayment(kind, debtRow),
    }]]
  }
  const items: DropdownMenuItem[] = []
  // Master/admin records own a detail page: Open views it.
  if (!isTableOnly.value) {
    items.push({
      label: t('app.ui.open'),
      icon: 'i-lucide-eye',
      onSelect: () => openRow(row),
    })
  }
  // Delivery: one-click Processing → Completed for the whole note.
  if (collection === 'deliveryNotes'
    && canDeliver.value
    && deliveryStatusOf(row as AppRecord) === 'Processing') {
    items.push({
      label: t('app.delivery.markCompleted'),
      icon: 'i-lucide-circle-check',
      color: 'success',
      onSelect: () => { void completeDelivery(row) },
    })
  }
  if (collection === 'products' && canOperate.value) {
    for (const type of STOCK_OPERATION_TYPES) {
      // Adjustment is not offered as a row action on the Stock table; Expiry
      // now runs per-lot from the product Batches tab.
      if (type === 'adjustment' || type === 'expiry') continue
      if (!auth.canAccessPage(STOCK_OPERATION_PERMISSIONS[type])) continue
      const meta = STOCK_OPERATION_META[type]
      items.push({
        label: meta.label,
        icon: meta.icon,
        color: meta.color,
        onSelect: () => openStockOperation(type, String(row.id || '')),
      })
    }
  }
  if (canEdit.value && supportsStatusToggle(collection)) {
    const inactive = isRecordInactive(row.status)
    items.push(inactive
      ? {
          label: t('core.rowActions.activate'),
          icon: 'i-lucide-circle-check',
          color: 'success',
          onSelect: () => { void setRowStatus(row, true) },
        }
      : {
          label: t('core.rowActions.deactivate'),
          icon: 'i-lucide-circle-off',
          color: 'warning',
          onSelect: () => { void setRowStatus(row, false) },
        })
  }
  // Hard delete only for inactive/disabled rows; active records must be
  // deactivated first (backend enforces the same rule).
  if (canDelete.value && canHardDeleteRecord(collection, row.status)) {
    items.push({
      label: t('app.ui.delete'),
      icon: 'i-lucide-trash-2',
      color: 'error',
      onSelect: () => { void deleteIds([String(row.id)]) },
    })
  }
  return items.length ? [items] : []
}

const columns = computed<TableColumn<Record<string, unknown>>[]>(() => {
  if (!current.value) return []
  void localization.value.dateFormat
  void localization.value.timeFormat
  void localization.value.timezone
  const titleKey = current.value.titleField
  const dataColumns = current.value.columns.map((column, index) => ({
    accessorKey: column.key,
    enableSorting: false,
    header: fieldLabel(column),
    meta: isNumericKey(column.key) || isMoneyKey(column.key)
      ? { class: { td: 'text-end tabular-nums whitespace-nowrap', th: 'text-end' } }
      : undefined,
    cell: ({ row }: { row: { original: Record<string, unknown> } }) => {
      if (column.type === 'image') {
        return h(TableAppTableCellImage, {
          src: productImageUrl(row.original),
          alt: String(row.original.name ?? ''),
        })
      }
      const text = cellText(row.original, column.key)
      const isTitle = column.key === titleKey || (index === 0 && !current.value!.columns.some(item => item.key === titleKey))
      const entityTo = column.key === 'entity' ? auditEntityLinkFor(row.original) : ''
      if (entityTo) {
        return h(ULink, {
          to: entityTo,
          class: 'font-medium text-highlighted hover:text-primary hover:underline',
        }, () => text)
      }
      // Sale No → POS checkout (view); Purchase No → purchase detail (view).
      const detailHref = documentDetailHrefFor(current.value!.collection, column.key, row.original)
      if (detailHref) {
        return h(ULink, {
          to: detailHref,
          class: 'font-medium text-highlighted hover:text-primary hover:underline',
        }, () => text)
      }
      // Related document numbers (debt invoice, return sale/purchase, delivery
      // invoice, movement reference) jump to the owning report page with the
      // number prefilled as search.
      const linkTarget = documentLinkTargetFor(current.value!.collection, column.key, row.original)
      if (linkTarget) {
        return h(ULink, {
          to: `${linkTarget.path}?q=${encodeURIComponent(linkTarget.search)}`,
          class: 'font-medium text-highlighted hover:text-primary hover:underline',
        }, () => text)
      }
      const qtyKind = current.value!.collection === 'products' ? STOCK_QTY_KIND[column.key] : undefined
      if (qtyKind) {
        return h('button', {
          type: 'button',
          class: 'font-medium tabular-nums text-primary hover:underline',
          onClick: () => openStockHistory(row.original, qtyKind),
        }, text)
      }
      if (isTitle && !isTableOnly.value) {
        return h(ULink, {
          to: recordPath(row.original.id),
          class: 'font-medium text-highlighted hover:text-primary hover:underline',
        }, () => text)
      }
      if (column.key === 'status' || column.key.toLowerCase().includes('status')) {
        return moduleStatusBadge(
          row.original[column.key] || row.original.workflowStatus || row.original.status,
          column.key,
          text,
        )
      }
      if (column.key === 'type') {
        return h(UBadge, { color: 'info', variant: 'subtle', size: 'sm' }, () => text)
      }
      if (column.key === 'customer' || column.key === 'supplier' || column.key === 'product') {
        return h('span', { class: 'block max-w-48 truncate text-default', title: text }, text)
      }
      return h('span', { class: 'text-sm text-default' }, text)
    },
  }))

  return [
    ...(supportsSelection.value ? [listTableSelectColumn<Record<string, unknown>>(t)] : []),
    ...dataColumns,
    ...(showRowActions.value
      ? [listTableRowMetaColumn<Record<string, unknown>>({
          summary: pageSummary.value,
          items: rowMenuItems,
          loadingId: busyId.value
            || (debtPayBusy.value ? String(debtPayRow.value?.id || '') : ''),
        })]
      : []),
  ]
})

function openDebtPayment(kind: DebtPaymentKind, row: AppRecord) {
  debtPayKind.value = kind
  debtPayRow.value = row
  debtPayOpen.value = true
}

async function submitDebtPayment(payload: {
  kind: DebtPaymentKind
  debtId: string
  partyId: string
  amount: number
  paymentMethod: string
  reference: string | null
}) {
  debtPayBusy.value = true
  busyId.value = payload.debtId
  try {
    if (payload.kind === 'customer') {
      await posCommands.payCustomerDebt({
        customerId: payload.partyId,
        debtId: payload.debtId,
        amount: payload.amount,
        paymentMethod: payload.paymentMethod,
        reference: payload.reference,
      })
      await store.fetchList('customerDebts')
      await store.fetchList('customers')
    }
    else {
      await posCommands.paySupplierDebt({
        supplierId: payload.partyId,
        debtId: payload.debtId,
        amount: payload.amount,
        paymentMethod: payload.paymentMethod,
        reference: payload.reference,
      })
      await store.fetchList('supplierDebts')
      await store.fetchList('suppliers')
    }
    debtPayOpen.value = false
    toast.add({ title: t('app.reports.paymentSaved'), color: 'success' })
  }
  catch (error: unknown) {
    if (!isApiErrorHandled(error)) {
      toast.add({
        title: t('app.reports.paymentFailed'),
        description: apiErrorMessage(error, t('app.reports.paymentFailed')),
        color: 'error',
      })
    }
  }
  finally {
    debtPayBusy.value = false
    busyId.value = ''
  }
}

/** Multi-select payment: settle several open debt documents (one party+currency). */
function openSelectedDebtPayment() {
  const collection = current.value?.collection
  if (collection !== 'customerDebts' && collection !== 'supplierDebts') return
  const rows = selectedDebtRows.value
  if (!rows.length) return
  const kind = collection === 'customerDebts' ? 'customer' : 'supplier'
  if (!selectedDebtsShareScope(rows, kind)) {
    toast.add({ title: t('app.reports.paySelectedMixed'), color: 'warning' })
    return
  }
  debtSelectedKind.value = kind
  debtSelectedRows.value = rows
  debtSelectedOpen.value = true
}

async function submitSelectedDebtPayment(payload: {
  amount: number
  paymentMethod: string
  reference: string | null
}) {
  const collection = current.value?.collection
  const rows = debtSelectedRows.value
  if (!collection || !rows.length) return
  const partyId = String(collection === 'customerDebts' ? rows[0]!.customerId : rows[0]!.supplierId)
  debtPayBusy.value = true
  try {
    if (collection === 'customerDebts') {
      await posCommands.payCustomerDebt({
        customerId: partyId,
        amount: payload.amount,
        paymentMethod: payload.paymentMethod,
        reference: payload.reference,
      })
      await store.fetchList('customerDebts')
      await store.fetchList('customers')
    }
    else {
      await posCommands.paySupplierDebt({
        supplierId: partyId,
        amount: payload.amount,
        paymentMethod: payload.paymentMethod,
        reference: payload.reference,
      })
      await store.fetchList('supplierDebts')
      await store.fetchList('suppliers')
    }
    debtSelectedOpen.value = false
    rowSelection.value = {}
    toast.add({ title: t('app.reports.paymentSaved'), color: 'success' })
  }
  catch (error: unknown) {
    if (!isApiErrorHandled(error)) {
      toast.add({
        title: t('app.reports.paymentFailed'),
        description: apiErrorMessage(error, t('app.reports.paymentFailed')),
        color: 'error',
      })
    }
  }
  finally {
    debtPayBusy.value = false
  }
}

function openCreate() {
  if (!current.value) return
  navigateTo(`${current.value.path}/new`)
}
function openRow(row: Record<string, unknown>) {
  if (!current.value || !row.id) return
  navigateTo(recordPath(row.id))
}

function onRowSelect(event: Event, row: TableRow<Record<string, unknown>>) {
  if (isTableOnly.value) return
  const target = event.target as HTMLElement | null
  if (target?.closest('a, button, input, [role="checkbox"], [role="menuitem"], [data-slot="dropdown-menu"]')) return
  openRow(row.original)
}

async function deleteIds(ids: string[]) {
  if (!current.value || !canDelete.value || !ids.length || busyId.value) return
  const collection = current.value.collection
  const deletable = ids.filter((id) => {
    const row = result.value.all.find(item => String(item.id) === id) as Record<string, unknown> | undefined
    return row ? canHardDeleteRecord(collection, row.status) : false
  })
  if (!deletable.length) {
    toast.add({ title: t('core.rowActions.deactivateBeforeDelete'), color: 'warning' })
    return
  }
  const found = result.value.all.find(row => String(row.id) === deletable[0])
  const name = deletable.length === 1 && found
    ? String((found as unknown as Record<string, unknown>)[current.value.titleField] ?? '')
    : ''
  const ok = await confirm(name
    ? {
        kind: 'delete',
        titleKey: 'core.confirm.deleteTitle',
        description: t('core.actions.deleteConfirmNamed', { name }),
        confirmLabelKey: 'core.rowActions.delete',
        confirmColor: 'error',
      }
    : { kind: 'delete', count: deletable.length })
  if (!ok) return
  busyId.value = deletable[0] || ''
  try {
    await store.deleteRemote(collection, deletable)
    rowSelection.value = {}
    toast.add({ title: t('core.actions.deletedItems', { n: deletable.length }), color: 'success' })
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
    busyId.value = ''
  }
}

async function deactivateIds(ids: string[]) {
  if (!current.value || !canEdit.value || !ids.length || busyId.value) return
  const ok = await confirm({
    kind: 'deactivate',
    descriptionKey: 'core.confirm.deactivateSelected',
    descriptionParams: { n: ids.length },
  })
  if (!ok) return
  busyId.value = ids[0] || ''
  try {
    const status = statusValueFor(current.value.collection, false)
    for (const id of ids) {
      await store.updateRemote(current.value.collection, id, { status })
    }
    rowSelection.value = {}
    toast.add({ title: t('app.ui.deactivated'), color: 'success' })
  }
  finally {
    busyId.value = ''
  }
}

async function setRowStatus(row: Record<string, unknown>, active: boolean) {
  const module = current.value
  if (!module || !row.id || busyId.value) return
  const ok = await confirm({ kind: active ? 'activate' : 'deactivate' })
  if (!ok) return
  const id = String(row.id)
  busyId.value = id
  try {
    await store.updateRemote(module.collection, id, { status: statusValueFor(module.collection, active) })
    toast.add({
      title: t(active ? 'core.common.activated' : 'core.common.deactivated'),
      color: 'success',
    })
  }
  catch (error: unknown) {
    if (!isApiErrorHandled(error)) {
      toast.add({
        title: t('app.ui.operationFailed'),
        description: apiErrorMessage(error, t('app.ui.operationFailed')),
        color: 'error',
      })
    }
  }
  finally {
    busyId.value = ''
  }
}

/** Delivery row action: move a Processing note to Completed (audited server-side). */
async function completeDelivery(row: Record<string, unknown>) {
  if (!row.id || busyId.value) return
  const ok = await confirm({
    kind: 'generic',
    titleKey: 'app.delivery.confirmCompleteTitle',
    descriptionKey: 'app.delivery.confirmCompleteDescription',
    confirmLabelKey: 'app.delivery.markCompleted',
    confirmColor: 'primary',
  })
  if (!ok) return
  const id = String(row.id)
  busyId.value = id
  try {
    await deliveryCommands.setDeliveryStatus(id, 'Completed')
    toast.add({ title: t('app.delivery.markedCompleted'), color: 'success' })
    void store.reloadCollection('deliveryNotes')
  }
  catch (error: unknown) {
    if (!isApiErrorHandled(error)) {
      toast.add({
        title: t('app.ui.operationFailed'),
        description: apiErrorMessage(error, t('app.ui.operationFailed')),
        color: 'error',
      })
    }
  }
  finally {
    busyId.value = ''
  }
}

function refresh() {
  // Always reload through the repository.
  if (current.value) {
    void store.reloadCollection(current.value.collection)
    return
  }
  store.reload()
}

/* ------------------------- Stock operations ------------------------- */

const productOptions = computed(() => store.list('products').map(product => ({
  label: `${product.code} Â· ${product.name}`,
  value: String(product.id),
})))

function openStockOperation(type: StockOperationType, productId = '') {
  // Stock In = the full-page New Purchase flow: many product lines, supplier
  // and payment stored on ONE stock-in document (POST /stock/in, items[]);
  // the product row preselects its product via the productId query.
  if (type === 'stock_in') {
    void navigateTo(productId
      ? { path: '/reports/purchases/new', query: { productId } }
      : '/reports/purchases/new')
    return
  }
  stockOperationType.value = type
  stockOperationProduct.value = productId
  stockOperationQuantity.value = undefined
  stockOperationNote.value = ''
  stockOperationOpen.value = true
}

const stockOperationMeta = computed(() => STOCK_OPERATION_META[stockOperationType.value])

const stockOperationCanSubmit = computed(() => Boolean(
  stockOperationProduct.value
  && stockOperationQuantity.value))

async function submitStockOperation() {
  if (!stockOperationProduct.value || !stockOperationQuantity.value) return
  stockOperationBusy.value = true
  try {
    const record = await posCommands.createStockOperation({
      type: stockOperationType.value,
      productId: stockOperationProduct.value,
      quantity: Number(stockOperationQuantity.value),
      note: stockOperationNote.value || null,
    })
    stockOperationOpen.value = false
    void store.fetchList('products')
    void store.fetchList('stockMovements')
    if (stockHistoryOpen.value) stockHistoryReloadKey.value += 1
    toast.add({
      title: `${stockOperationMeta.value.label}: ${record.reference}`,
      description: `${record.product} \u00b7 Qty ${record.quantity}`,
      color: 'success',
    })
  }
  catch (error: unknown) {
    if (!isApiErrorHandled(error)) {
      toast.add({
        title: t('app.ui.operationFailed'),
        description: apiErrorMessage(error, t('app.ui.operationFailed')),
        color: 'error',
      })
    }
  }
  finally {
    stockOperationBusy.value = false
  }
}

function optionValue(option: ModuleSelectOption) {
  return typeof option === 'string' ? option : option.value
}

function filterItems(filter: { options?: readonly ModuleSelectOption[] | ModuleSelectOption[], key: string, optionsOnly?: boolean }) {
  const fromOptions = (filter.options || []).map(optionValue)
  const sourceRows = !filter.optionsOnly && current.value
    ? store.list(current.value.collection).map(row => current.value?.collection === 'auditLogs' ? normalizeAuditLog(row) : row)
    : []
  const fromData = [...new Set(sourceRows.map(row => String(row[filter.key] ?? '').trim()).filter(Boolean))]
  return [...new Set([...fromOptions, ...fromData])]
    .map(value => String(value).trim())
    .filter(Boolean)
    .map((value) => {
      const label = filter.key === 'documentType'
        ? documentSequenceTypeLabel(value)
        : filter.key === 'workflowStatus'
          ? value.replaceAll('_', ' ')
          : value
      return { label, value }
    })
}
</script>

<template>
  <div v-if="current" class="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-muted/20">
    <LayoutAppHeaderPageActions
      :can-create="canCreate"
      :can-export="true"
      :export-fields="exportFieldOptions"
      :export-party-options="exportPartyOptions"
      :export-party-label="exportPartyLabel"
      :export-user-options="exportUserOptions"
      :export-user-label="exportUserLabel"
      :exporting="exporting"
      :create-label="t('app.ui.newEntity', { entity: moduleSingular(current) })"
      :refreshing="pending"
      @create="openCreate"
      @refresh="refresh"
      @export="onExport"
    />

    <TableAppListTable
      v-model:search="q"
      v-model:date-start="dateFrom"
      v-model:date-end="dateTo"
      v-model:row-selection="rowSelection"
      v-model:pagination="pagination"
      :data="result.all"
      :columns="columns"
      :loading="pending"
      :show-date-range="Boolean(dateField)"
      :filters-active="hasActiveFilters"
      :empty-actions="canCreate ? [{ icon: 'i-lucide-plus', label: t('app.ui.newEntity', { entity: moduleSingular(current) }), onClick: openCreate }] : []"
      @select="onRowSelect"
    >
      <template #filters="{ compact }">
        <CommonAppFilterSelect
          v-for="filter in visibleFilters"
          :key="filter.key"
          :model-value="filters[filter.key] ?? []"
          :items="filterItems(filter)"
          :placeholder="fieldLabel(filter)"
          :class="compact ? 'w-full' : 'w-40'"
          @update:model-value="filters[filter.key] = parseFilterQuery($event)"
        />
      </template>
      <template #actions>
        <template v-if="selectedDebtRows.length && canPaySelectedDebts">
          <UButton
            color="success"
            variant="soft"
            size="sm"
            icon="i-lucide-hand-coins"
            class="shrink-0"
            :label="`${t('app.reports.paySelected')} (${selectedDebtRows.length})`"
            @click="openSelectedDebtPayment()"
          />
          <UButton
            color="neutral"
            variant="ghost"
            size="sm"
            class="shrink-0"
            :label="t('app.ui.clear')"
            @click="rowSelection = {}"
          />
        </template>
        <template v-if="selectedIds.length && canBulkDeactivate">
          <UButton
            color="warning"
            variant="soft"
            size="sm"
            icon="i-lucide-circle-off"
            class="shrink-0"
            :label="`${t('app.ui.deactivate')} (${selectedIds.length})`"
            @click="deactivateIds(selectedIds)"
          />
          <UButton
            color="neutral"
            variant="ghost"
            size="sm"
            class="shrink-0"
            :label="t('app.ui.clear')"
            @click="rowSelection = {}"
          />
        </template>
      </template>
    </TableAppListTable>

    <CommonAppDialog
      v-model:open="stockOperationOpen"
      :title="stockOperationMeta.label"
      :icon="stockOperationMeta.icon"
      :color="stockOperationMeta.color"
      size="sm"
      :loading="stockOperationBusy"
    >
      <div class="w-full space-y-3">
        <CommonAppSelectMenuField
          v-model="stockOperationProduct"
          :items="productOptions"
          :label="t('app.pos.product')"
          :required="true"
          class="w-full"
        />
        <CommonAppNumberField
          v-model="stockOperationQuantity"
          :label="`${t('app.fields.quantity')} (${stockOperationType === 'adjustment' ? '+/âˆ’' : 'âˆ’'})`"
          :required="true"
          :min="stockOperationType === 'adjustment' ? undefined : 0"
          :step="1"
          class="w-full"
        />
        <CommonAppTextareaField
          v-model="stockOperationNote"
          :label="t('app.fields.note')"
          :rows="2"
          class="w-full"
        />
        <p v-if="stockOperationType === 'damage'" class="text-xs text-muted">
          {{ t('app.stock.negativeHint') }}
        </p>
      </div>

      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton
            color="neutral"
            variant="ghost"
            :label="t('common.cancel')"
            @click="stockOperationOpen = false"
          />
          <UButton
            :color="stockOperationMeta.color"
            :icon="stockOperationMeta.icon"
            :loading="stockOperationBusy"
            :disabled="!stockOperationCanSubmit"
            :label="stockOperationMeta.label"
            @click="submitStockOperation"
          />
        </div>
      </template>
    </CommonAppDialog>

    <StockQtyHistoryDialog
      v-model:open="stockHistoryOpen"
      :product="stockHistoryProduct"
      :kind="stockHistoryKind"
      :can-add="canOperate"
      :reload-key="stockHistoryReloadKey"
      @saved="onStockHistorySaved"
    />

    <ReportsDebtPaymentDialog
      v-model:open="debtPayOpen"
      :kind="debtPayKind"
      :debt="debtPayRow"
      :currency="String(debtPayRow?.currency || preferences.currency)"
      @submit="submitDebtPayment"
    />

    <ReportsDebtPaySelectedDialog
      v-model:open="debtSelectedOpen"
      :kind="debtSelectedKind"
      :debts="debtSelectedRows"
      :currency="String(debtSelectedRows[0]?.currency || preferences.currency)"
      @submit="submitSelectedDebtPayment"
    />

  </div>
  <div v-else class="grid h-full min-h-0 flex-1 place-items-center p-8">
    <UEmpty
      variant="naked"
      icon="i-lucide-unplug"
      :title="t('app.ui.pageNotWired')"
      :description="t('app.ui.pageNotWiredHint')"
    />
  </div>
</template>

