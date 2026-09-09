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
import { isMoneyKey, isNumericKey } from '~/utils/module/field-keys'
import { limitFilterSelects, parseFilterQuery } from '~/utils/filter/values'
import { isFilterValueActive } from '~/utils/filter/select-ui'
import { listTableRowMetaColumn, listTableSelectColumn } from '~/utils/table/list-columns'
import { listTablePageSummary, listTableSelectedIds } from '~/utils/table/list-table'
import { documentSequenceTypeLabel } from '~/utils/document-sequences'
import { conversionForUom, convertToBase, multiplyDecimalSafe } from '~/utils/stock/uom-conversions'
import { normalizeAuditLog, resolveAuditEntityPath } from '~/utils/module/audit-logs'
import { usePosCommands } from '~/repositories/index'
import { productImageUrl } from '~/utils/pos/cart'
import { STOCK_OPERATION_META, STOCK_OPERATION_TYPES, type StockHistoryKind, type StockOperationType } from '~/config/pos-options'
import { documentHasReturnableLines, type ReturnDocumentKind } from '~/utils/reports/returns'
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
const { localization } = useAppLocalization()

const q = ref('')
const pagination = ref<PaginationState>({ pageIndex: 0, pageSize: 20 })
const filters = reactive<Record<string, string[]>>({})
const rowSelection = ref<Record<string, boolean>>({})
const busyId = ref('')
const preferences = usePreferencesStore()
const stockOperationOpen = ref(false)
const stockOperationType = ref<StockOperationType>('stock_in')
const stockOperationProduct = ref('')
const stockOperationQuantity = ref<number | undefined>()
const stockOperationNote = ref('')
const stockOperationBusy = ref(false)
const stockOperationUomId = ref('')
const stockOperationUnitCost = ref<number | undefined>()
// Stock In = purchase: supplier + payment (unpaid balance → supplier debt).
const stockOperationSupplier = ref('')
const stockOperationPaidInput = ref<number | undefined>()
const stockOperationPaymentMethod = ref<'Cash' | 'BANK_QR'>('Cash')
const dateFrom = ref('')
const dateTo = ref('')
const returnOpen = ref(false)
const returnKind = ref<ReturnDocumentKind>('sale')
const returnDocument = ref<AppRecord | null>(null)
const returnBusy = ref(false)
const debtPayOpen = ref(false)
const debtPayKind = ref<DebtPaymentKind>('customer')
const debtPayRow = ref<AppRecord | null>(null)
const debtPayBusy = ref(false)

const current = computed(() => module.value)
const pending = computed(() => Boolean(current.value && store.isLoading(current.value.collection)))
const isTableOnly = computed(() => Boolean(current.value?.tableOnly))
/** Table-only reports that still need row actions (Return / Pay). */
const showRowActions = computed(() => {
  if (!isTableOnly.value) return true
  const collection = current.value?.collection
  if (collection === 'sales') return canReturnSale.value
  if (collection === 'stockIns') return canReturnPurchase.value
  if (collection === 'customerDebts') return canPayCustomerDebt.value
  if (collection === 'supplierDebts') return canPaySupplierDebt.value
  return false
})
const permissionPrefix = computed(() => current.value?.permission.replace(/\.view$/, '') || '')
const canCreate = computed(() => Boolean(
  current.value?.canCreate
  && !current.value.readOnly
  && auth.canAccessPage(`${permissionPrefix.value}.create`),
))
const canEdit = computed(() => Boolean(
  current.value
  && !current.value.readOnly
  && auth.canAccessPage(`${permissionPrefix.value}.edit`),
))
const canDelete = computed(() => Boolean(
  current.value
  && !current.value.readOnly
  && auth.canAccessPage(`${permissionPrefix.value}.delete`),
))
const canOperate = computed(() => Boolean(
  current.value
  && !current.value.readOnly
  && (auth.canAccessPage(`${permissionPrefix.value}.operate`) || auth.canAccessPage(`${permissionPrefix.value}.edit`)),
))
// Backend returns require pos.access (PosService.return_sale) — the UI
// check only hides the action.
const canReturnSale = computed(() =>
  auth.canAccessPage('pos.access'),
)
const canReturnPurchase = computed(() =>
  auth.canAccessPage('stock.in'),
)
const canPayCustomerDebt = computed(() =>
  auth.canAccessPage('customers.edit')
  || auth.canAccessPage('customers.operate')
  || auth.canAccessPage('reports.view')
  || auth.canAccessPage('ALL_PAGES'),
)
const canPaySupplierDebt = computed(() =>
  auth.canAccessPage('suppliers.edit')
  || auth.canAccessPage('suppliers.operate')
  || auth.canAccessPage('reports.view')
  || auth.canAccessPage('ALL_PAGES'),
)
const deactivationOnly = computed(() => current.value?.group === 'master' || current.value?.collection === 'documentSequences')
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
      uom: String(row.uom || uomById(String(row.uomId))?.name || ''),
      uomSymbol: String(row.uomSymbol || uomById(String(row.uomId))?.symbol || ''),
      brand: String(row.brand || brandById(String(row.brandId))?.name || ''),
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
  return queried
})

/** UOM lookup for product display enrichment. */
const uomById = (id: string) => store.list('uoms').find(uom => String(uom.id) === id)

/** Brand lookup for product display enrichment. */
const brandById = (id: string) => store.list('brands').find(brand => String(brand.id) === id)

/** Products linked to each brand — used to keep the brand list informative. */
const brandProductCounts = computed(() => {
  const counts = new Map<string, number>()
  for (const row of store.list('products')) {
    const brandId = String(row.brandId ?? '')
    if (!brandId) continue
    counts.set(brandId, (counts.get(brandId) || 0) + 1)
  }
  return counts
})

/** Products linked to each UOM — used to keep the UOM list informative. */
const uomProductCounts = computed(() => {
  const counts = new Map<string, number>()
  for (const row of store.list('products')) {
    const uomId = String(row.uomId ?? '')
    if (!uomId) continue
    counts.set(uomId, (counts.get(uomId) || 0) + 1)
  }
  return counts
})

/** Per-product movement aggregates for the Stock list quantity columns. */
const stockTotalsByProduct = computed(() => {
  const totals = new Map<string, { stockIn: number, stockOut: number, damage: number }>()
  for (const row of store.list('stockMovements')) {
    const productId = String(row.productId ?? '')
    if (!productId) continue
    const entry = totals.get(productId) || { stockIn: 0, stockOut: 0, damage: 0 }
    const qty = Number(row.quantity || 0)
    const type = String(row.type ?? '')
    if (type === 'Stock In' || type === 'Sale Return') entry.stockIn += qty
    else if (type === 'Sale') entry.stockOut += Math.abs(qty)
    else if (type === 'Damage') entry.damage += Math.abs(qty)
    totals.set(productId, entry)
  }
  return totals
})

/** Quantity column → history dialog movement-kind filter.
 *  Current Stock (`quantity`) is display-only — it never opens the dialog. */
const STOCK_QTY_KIND: Record<string, StockHistoryKind> = {
  stockInQty: 'stock_in',
  stockOutQty: 'stock_out',
  damageQty: 'damage',
}

/** Price column → price dialog (spec: Cost Price / Sale Price cells). */
const STOCK_PRICE_KIND = {
  costPrice: 'cost',
  salePrice: 'sale',
} as const

type StockPriceKind = (typeof STOCK_PRICE_KIND)[keyof typeof STOCK_PRICE_KIND]

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

const costPriceOpen = ref(false)
const salePriceOpen = ref(false)
const priceProduct = ref<AppRecord | null>(null)

function openPriceDialog(row: Record<string, unknown>, kind: StockPriceKind) {
  priceProduct.value = row as AppRecord
  if (kind === 'cost') costPriceOpen.value = true
  else salePriceOpen.value = true
}
const selectedIds = computed(() => listTableSelectedIds(rowSelection.value))

const hasActiveFilters = computed(() => Boolean(
  Object.values(filters).some(value => isFilterValueActive(value))
  || isFilterValueActive(dateFrom.value)
  || isFilterValueActive(dateTo.value),
))

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

// Client-only: reload list data after mount and when filters change. Mock
// mode fetches too — the mock repository serves the in-memory seed cheaply,
// so loading/error stays repository-driven in every mode.
function reloadModuleData() {
  if (!import.meta.client || !current.value) return
  void store.fetchList(current.value.collection, {
    q: q.value || undefined,
    startDate: dateFrom.value || undefined,
    endDate: dateTo.value || undefined,
  })
  if (current.value.collection === 'products') {
    void store.fetchList('stockMovements')
    void store.fetchList('uoms')
    void store.fetchList('brands')
  }
  if (current.value.collection === 'uoms') void store.fetchList('products')
  if (current.value.collection === 'brands') void store.fetchList('products')
}

onMounted(() => {
  reloadModuleData()
})

watch([current, q, dateFrom, dateTo], () => {
  reloadModuleData()
})

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

function rowMenuItems(row: Record<string, unknown>): DropdownMenuItem[][] {
  const collection = current.value?.collection
  if (collection === 'sales') {
    if (!canReturnSale.value) return []
    return [[{
      label: t('app.reports.return'),
      icon: 'i-lucide-undo-2',
      color: 'warning',
      disabled: !documentHasReturnableLines(row as AppRecord),
      onSelect: () => openReturn('sale', row as AppRecord),
    }]]
  }
  if (collection === 'stockIns') {
    if (!canReturnPurchase.value) return []
    return [[{
      label: t('app.reports.return'),
      icon: 'i-lucide-undo-2',
      color: 'warning',
      disabled: !documentHasReturnableLines(row as AppRecord),
      onSelect: () => openReturn('purchase', row as AppRecord),
    }]]
  }
  if (collection === 'customerDebts') {
    if (!canPayCustomerDebt.value) return []
    return [[{
      label: t('app.reports.pay'),
      icon: 'i-lucide-hand-coins',
      color: 'success',
      disabled: Number(row.remainingAmount || 0) <= 0,
      onSelect: () => openDebtPayment('customer', row as AppRecord),
    }]]
  }
  if (collection === 'supplierDebts') {
    if (!canPaySupplierDebt.value) return []
    return [[{
      label: t('app.reports.pay'),
      icon: 'i-lucide-hand-coins',
      color: 'success',
      disabled: Number(row.remainingAmount || 0) <= 0,
      onSelect: () => openDebtPayment('supplier', row as AppRecord),
    }]]
  }
  const items: DropdownMenuItem[] = [
    {
      label: t('app.ui.open'),
      icon: 'i-lucide-eye',
      onSelect: () => openRow(row),
    },
  ]
  if (collection === 'documentSequences') {
    if (canEdit.value) {
      const active = String(row.status || '').toUpperCase() === 'ACTIVE'
      items.push({
        label: active ? t('core.rowActions.deactivate') : t('core.rowActions.activate'),
        icon: active ? 'i-lucide-circle-off' : 'i-lucide-circle-check',
        color: active ? 'warning' : 'success',
        onSelect: () => setDocumentSequenceStatus(row, active ? 'INACTIVE' : 'ACTIVE'),
      })
    }
    return [items]
  }
  if (collection === 'products' && canOperate.value) {
    for (const type of STOCK_OPERATION_TYPES) {
      const meta = STOCK_OPERATION_META[type]
      items.push({
        label: meta.label,
        icon: meta.icon,
        color: meta.color,
        onSelect: () => openStockOperation(type, String(row.id || '')),
      })
    }
  }
  if (collection === 'users') {
    const status = String(row.status || 'Active')
    if (canEdit.value && status === 'Active') {
      items.push({
        label: t('core.rowActions.deactivate'),
        icon: 'i-lucide-circle-off',
        color: 'warning',
        onSelect: () => { void setUserStatus(row, 'Inactive') },
      })
    }
    if (canEdit.value && status === 'Inactive') {
      items.push({
        label: t('core.rowActions.activate'),
        icon: 'i-lucide-circle-check',
        color: 'success',
        onSelect: () => { void setUserStatus(row, 'Active') },
      })
    }
  }
  if (canDelete.value && !deactivationOnly.value) {
    items.push({
      label: t('app.ui.delete'),
      icon: 'i-lucide-trash-2',
      color: 'error',
      onSelect: () => { void deleteIds([String(row.id)]) },
    })
  }
  if (canEdit.value && deactivationOnly.value) {
    items.push({
      label: t('app.ui.deactivate'),
      icon: 'i-lucide-circle-off',
      color: 'warning',
      onSelect: () => { void deactivateIds([String(row.id)]) },
    })
  }
  return [items]
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
      const qtyKind = current.value!.collection === 'products' ? STOCK_QTY_KIND[column.key] : undefined
      if (qtyKind) {
        return h('button', {
          type: 'button',
          class: 'font-medium tabular-nums text-primary hover:underline',
          onClick: () => openStockHistory(row.original, qtyKind),
        }, text)
      }
      const priceKind = current.value!.collection === 'products' ? STOCK_PRICE_KIND[column.key as keyof typeof STOCK_PRICE_KIND] : undefined
      if (priceKind) {
        return h('button', {
          type: 'button',
          class: 'font-medium tabular-nums text-primary hover:underline',
          onClick: () => openPriceDialog(row.original, priceKind),
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
    ...(!isTableOnly.value ? [listTableSelectColumn<Record<string, unknown>>(t)] : []),
    ...dataColumns,
    ...(showRowActions.value
      ? [listTableRowMetaColumn<Record<string, unknown>>({
          summary: pageSummary.value,
          items: rowMenuItems,
          loadingId: busyId.value
            || (returnBusy.value ? String(returnDocument.value?.id || '') : '')
            || (debtPayBusy.value ? String(debtPayRow.value?.id || '') : ''),
        })]
      : []),
  ]
})

function openReturn(kind: ReturnDocumentKind, row: AppRecord) {
  returnKind.value = kind
  returnDocument.value = row
  returnOpen.value = true
}

function openDebtPayment(kind: DebtPaymentKind, row: AppRecord) {
  debtPayKind.value = kind
  debtPayRow.value = row
  debtPayOpen.value = true
}

async function submitReturn(payload: {
  kind: ReturnDocumentKind
  documentId: string
  reason: string
  lines: Array<{ lineId: string, quantity: number, restock: boolean }>
}) {
  returnBusy.value = true
  busyId.value = payload.documentId
  try {
    if (payload.kind === 'sale') {
      await posCommands.returnSale({
        saleId: payload.documentId,
        reason: payload.reason,
        lines: payload.lines,
      })
    }
    else {
      await posCommands.returnPurchase({
        stockInId: payload.documentId,
        reason: payload.reason,
        lines: payload.lines.map(line => ({ lineId: line.lineId, quantity: line.quantity })),
      })
    }
    if (current.value) await store.fetchList(current.value.collection)
    if (payload.kind === 'sale') await store.fetchList('products')
    else {
      await store.fetchList('products')
      await store.fetchList('stockIns')
    }
    returnOpen.value = false
    toast.add({ title: t('app.reports.returnSaved'), color: 'success' })
  }
  catch (error: unknown) {
    toast.add({
      title: t('app.reports.returnFailed'),
      description: error instanceof Error ? error.message : String(error),
      color: 'error',
    })
  }
  finally {
    returnBusy.value = false
    busyId.value = ''
  }
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
    toast.add({
      title: t('app.reports.paymentFailed'),
      description: error instanceof Error ? error.message : String(error),
      color: 'error',
    })
  }
  finally {
    debtPayBusy.value = false
    busyId.value = ''
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
  if (!current.value || !canDelete.value || !ids.length) return
  const ok = await confirm({ kind: 'delete', count: ids.length })
  if (!ok) return
  busyId.value = ids[0] || ''
  try {
    await store.deleteRemote(current.value.collection, ids)
    rowSelection.value = {}
    toast.add({ title: t('core.actions.deletedItems', { n: ids.length }), color: 'success' })
  }
  catch (error: unknown) {
    toast.add({
      title: t('api.errorTitle', { status: (error as { statusCode?: number })?.statusCode || 400 }),
      description: error instanceof Error ? error.message : String(error),
      color: 'error',
    })
  }
  finally {
    busyId.value = ''
  }
}

async function deactivateIds(ids: string[]) {
  if (!current.value || !canEdit.value || !ids.length) return
  busyId.value = ids[0] || ''
  try {
    for (const id of ids) {
      const status = current.value.collection === 'documentSequences' ? 'INACTIVE' : 'Inactive'
      await store.updateRemote(current.value.collection, id, { status })
    }
    rowSelection.value = {}
    toast.add({ title: t('app.ui.deactivated'), color: 'success' })
  }
  finally {
    busyId.value = ''
  }
}

async function setUserStatus(row: Record<string, unknown>, status: 'Active' | 'Inactive') {
  if (!current.value || current.value.collection !== 'users') return
  const id = String(row.id || '')
  busyId.value = id
  try {
    await store.updateRemote('users', id, { status })
    toast.add({
      title: t(status === 'Active' ? 'core.common.activated' : 'core.common.deactivated'),
      color: 'success',
    })
  }
  finally {
    busyId.value = ''
  }
}

async function setDocumentSequenceStatus(row: Record<string, unknown>, status: 'ACTIVE' | 'INACTIVE') {
  if (!current.value || !canEdit.value) return
  busyId.value = String(row.id || '')
  try {
    await store.updateRemote(current.value.collection, String(row.id || ''), { status })
    toast.add({ title: t(status === 'ACTIVE' ? 'core.common.activated' : 'core.common.deactivated'), color: 'success' })
  }
  finally {
    busyId.value = ''
  }
}

function refresh() {
  // Always reload through the repository (mock mode re-reads the in-memory seed).
  if (current.value) {
    void store.reloadCollection(current.value.collection)
    return
  }
  store.reload()
}

/* ------------------------- Stock operations ------------------------- */

const productOptions = computed(() => store.list('products').map(product => ({
  label: `${product.code} · ${product.name}`,
  value: String(product.id),
})))

function openStockOperation(type: StockOperationType, productId = '') {
  stockOperationType.value = type
  stockOperationProduct.value = productId
  stockOperationQuantity.value = undefined
  stockOperationNote.value = ''
  const product = store.list('products').find(row => String(row.id) === String(productId))
  stockOperationUomId.value = String(product?.uomId || '')
  stockOperationUnitCost.value = undefined
  stockOperationSupplier.value = ''
  stockOperationPaidInput.value = undefined
  stockOperationPaymentMethod.value = 'Cash'
  stockOperationOpen.value = true
}

const stockOperationMeta = computed(() => STOCK_OPERATION_META[stockOperationType.value])

/** Product record for the selected operation product. */
const stockOperationProductRecord = computed(() =>
  store.list('products').find(row => String(row.id) === String(stockOperationProduct.value)) || null)

/** Stock In line UOM options: every Pricing row's Original UOM (spec §2.1.3); legacy products without Pricing rows fall back to their base UOM. */
const stockOperationUomOptions = computed(() => {
  const product = stockOperationProductRecord.value
  if (!product) return []
  const conversions = Array.isArray(product.uomConversions) ? product.uomConversions as Array<Record<string, unknown>> : []
  if (conversions.length) {
    return conversions
      .filter(row => row.uomId)
      .map(row => ({ label: String(row.uomSymbol || row.uomId || ''), value: String(row.uomId) }))
  }
  return [{ label: String(product.uomSymbol || product.uom || ''), value: String(product.uomId || '') }]
})

const stockOperationConversion = computed(() =>
  conversionForUom(stockOperationProductRecord.value, stockOperationUomId.value))

const stockOperationFactor = computed(() =>
  stockOperationType.value === 'stock_in' ? (stockOperationConversion.value?.factorToBase ?? 1) : 1)

const stockOperationUomSymbol = computed(() =>
  stockOperationConversion.value?.uomSymbol
  || String(stockOperationProductRecord.value?.uomSymbol || stockOperationProductRecord.value?.uom || ''))

const baseUomSymbol = computed(() =>
  String(stockOperationProductRecord.value?.uomSymbol || stockOperationProductRecord.value?.uom || ''))

/** `2 box = 24 pcs` helper: received qty converted to the base UOM. */
const stockOperationConvertedHint = computed(() => {
  if (stockOperationType.value !== 'stock_in' || !stockOperationQuantity.value) return ''
  const baseQty = convertToBase(stockOperationQuantity.value, stockOperationFactor.value)
  return t('app.stock.uomConvertHint', {
    qty: stockOperationQuantity.value,
    from: stockOperationUomSymbol.value,
    base: baseQty,
    baseUom: baseUomSymbol.value,
  })
})

/** Prefill the editable unit cost from the conversion row (or base × factor). */
watch(stockOperationUomId, (uomId) => {
  const product = stockOperationProductRecord.value
  if (!product || stockOperationType.value !== 'stock_in') return
  const conversion = conversionForUom(product, uomId)
  const suggested = conversion?.costPrice != null
    ? conversion.costPrice
    : multiplyDecimalSafe(Number(product.costPrice || 0), conversion?.factorToBase ?? 1)
  stockOperationUnitCost.value = suggested > 0 ? suggested : undefined
})

/** Supplier options for the Stock In purchase dialog. */
const stockOperationSupplierOptions = computed(() =>
  store.list('suppliers')
    .filter(row => String(row.status || 'Active') !== 'Inactive')
    .map(row => ({ label: String(row.name || ''), value: String(row.id) })))

/** Stock In line total (received qty × unit cost per the selected UOM). */
const stockOperationLineTotal = computed(() =>
  Math.round((Number(stockOperationQuantity.value || 0) * Number(stockOperationUnitCost.value || 0)) * 100) / 100)

/** Paid now defaults to the full line total (0…total; balance → supplier debt). */
const stockOperationPaidAmount = computed(() =>
  Math.min(Number(stockOperationPaidInput.value ?? stockOperationLineTotal.value), stockOperationLineTotal.value))

const stockOperationOutstanding = computed(() =>
  Math.round((stockOperationLineTotal.value - stockOperationPaidAmount.value) * 100) / 100)

const stockOperationCanSubmit = computed(() => Boolean(
  stockOperationProduct.value
  && stockOperationQuantity.value
  && (stockOperationType.value !== 'stock_in'
    || stockOperationOutstanding.value <= 0
    || stockOperationSupplier.value)))

async function submitStockOperation() {
  if (!stockOperationProduct.value || !stockOperationQuantity.value) return
  stockOperationBusy.value = true
  try {
    const record = await posCommands.createStockOperation({
      type: stockOperationType.value,
      productId: stockOperationProduct.value,
      quantity: Number(stockOperationQuantity.value),
      note: stockOperationNote.value || null,
      ...(stockOperationType.value === 'stock_in'
        ? {
            uomId: stockOperationUomId.value || undefined,
            uomSymbol: stockOperationUomSymbol.value || undefined,
            factorToBase: stockOperationFactor.value,
            ...(stockOperationUnitCost.value != null ? { unitCost: Number(stockOperationUnitCost.value) } : {}),
            supplierId: stockOperationSupplier.value || null,
            paidAmount: stockOperationPaidAmount.value,
            paymentMethod: stockOperationPaymentMethod.value,
          }
        : {}),
    })
    stockOperationOpen.value = false
    void store.fetchList('products')
    void store.fetchList('stockMovements')
    if (stockHistoryOpen.value) stockHistoryReloadKey.value += 1
    toast.add({
      title: `${stockOperationMeta.value.label}: ${record.reference}`,
      description: `${record.product} · Qty ${record.quantity}`,
      color: 'success',
    })
  }
  catch (error: unknown) {
    toast.add({
      title: t('app.ui.operationFailed'),
      description: error instanceof Error ? error.message : String(error),
      color: 'error',
    })
  }
  finally {
    stockOperationBusy.value = false
  }
}

function optionValue(option: ModuleSelectOption) {
  return typeof option === 'string' ? option : option.value
}

function filterItems(filter: { options?: readonly ModuleSelectOption[] | ModuleSelectOption[], key: string }) {
  const fromOptions = (filter.options || []).map(optionValue)
  const sourceRows = current.value
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
      :can-export="false"
      :export-fields="[]"
      :exporting="false"
      :create-label="t('app.ui.newEntity', { entity: moduleSingular(current) })"
      :refreshing="pending"
      @create="openCreate"
      @refresh="refresh"
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
        <template v-if="selectedIds.length && (canEdit || canDelete)">
          <UButton
            :color="deactivationOnly ? 'warning' : 'error'"
            variant="soft"
            size="sm"
            :icon="deactivationOnly ? 'i-lucide-circle-off' : 'i-lucide-trash-2'"
            class="shrink-0"
            :label="`${deactivationOnly ? t('app.ui.deactivate') : t('app.ui.delete')} (${selectedIds.length})`"
            @click="deactivationOnly ? deactivateIds(selectedIds) : deleteIds(selectedIds)"
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
        <CommonAppSelectMenuField
          v-if="stockOperationType === 'stock_in'"
          v-model="stockOperationUomId"
          :items="stockOperationUomOptions"
          :label="t('app.pos.uom')"
          class="w-full"
        />
        <CommonAppNumberField
          v-model="stockOperationQuantity"
          :label="stockOperationType === 'stock_in' ? t('app.fields.quantity') : `${t('app.fields.quantity')} (${stockOperationType === 'adjustment' ? '+/−' : '−'})`"
          :required="true"
          :min="stockOperationType === 'adjustment' ? undefined : 0"
          :step="1"
          class="w-full"
        />
        <p
          v-if="stockOperationType === 'stock_in' && stockOperationConvertedHint"
          class="text-xs text-muted"
        >
          {{ stockOperationConvertedHint }}
        </p>
        <CommonAppMoneyField
          v-if="stockOperationType === 'stock_in'"
          v-model="stockOperationUnitCost"
          :label="t('app.stock.convCost')"
          :min="0"
          :step="0.01"
          :help="t('app.stock.convCostHint')"
          class="w-full"
        />
        <template v-if="stockOperationType === 'stock_in'">
          <CommonAppSelectMenuField
            v-model="stockOperationSupplier"
            :items="stockOperationSupplierOptions"
            :label="t('app.fields.supplier')"
            :help="t('app.stock.supplierHint')"
            class="w-full"
          />
          <CommonAppSelectMenuField
            v-model="stockOperationPaymentMethod"
            :items="[
              { label: t('app.pos.paymentMethodCash'), value: 'Cash' },
              { label: t('app.pos.paymentMethodBank'), value: 'BANK_QR' },
            ]"
            :label="t('app.reports.paymentMethod')"
            class="w-full"
          />
          <CommonAppMoneyField
            v-model="stockOperationPaidInput"
            :label="t('app.pos.paidNow')"
            :min="0"
            :max="stockOperationLineTotal"
            :step="0.01"
            :help="t('app.stock.paidHint', { total: stockOperationLineTotal })"
            class="w-full"
          />
          <p v-if="stockOperationOutstanding > 0 && !stockOperationSupplier" class="text-xs text-warning">
            {{ t('app.stock.outstandingNeedsSupplier') }}
          </p>
        </template>
        <CommonAppTextareaField
          v-model="stockOperationNote"
          :label="t('app.fields.note')"
          :rows="2"
          class="w-full"
        />
        <p v-if="stockOperationType === 'damage' || stockOperationType === 'expiry'" class="text-xs text-muted">
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

    <StockCostHistoryDialog
      v-model:open="costPriceOpen"
      :product="priceProduct"
    />

    <StockSalePriceDialog
      v-model:open="salePriceOpen"
      :product="priceProduct"
    />

    <ReportsDocumentReturnDialog
      v-model:open="returnOpen"
      :kind="returnKind"
      :document="returnDocument"
      :currency="preferences.currency"
      @submit="submitReturn"
    />

    <ReportsDebtPaymentDialog
      v-model:open="debtPayOpen"
      :kind="debtPayKind"
      :debt="debtPayRow"
      :currency="preferences.currency"
      @submit="submitDebtPayment"
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

