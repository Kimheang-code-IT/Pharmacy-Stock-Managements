<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { PaginationState } from '@tanstack/vue-table'
import { UBadge, UButton } from '#components'
import { h } from 'vue'
import type { AppRecord } from '~/config/admin-seed'
import type { ProductBatchRow } from '~/repositories/contracts/entities'
import { usePosCommands, useStockQueries } from '~/repositories/index'
import { useConfirm } from '~/composables/common/useConfirm'
import { apiErrorMessage, isApiErrorHandled, isRequestAborted } from '~/utils/api/errors'
import { formatDate, formatMoney } from '~/utils/format/format-service'
import { moduleDocumentRecordKey } from '~/utils/module/document-tabs'
import { stockBreakdownLabel } from '~/utils/stock/uom-conversions'

/**
 * Product document **Batches** tab — read-only stock lots created by Stock In.
 * Each lot offers an Expire action that stocks out its remaining quantity as
 * an expiry loss (POST /stock/expire).
 */
const props = withDefaults(defineProps<{
  product?: AppRecord | null
  disabled?: boolean
}>(), {
  product: null,
  disabled: false,
})

const stockQueries = useStockQueries()
const posCommands = usePosCommands()
const auth = useAuthStore()
const { confirm } = useConfirm()
const { t } = useI18n()
const toast = useToast()
const store = useAppDataStore()
const recordAccess = inject(moduleDocumentRecordKey, null)

const search = ref('')
const loading = ref(false)
const busyId = ref('')
const loadError = ref<string | null>(null)
const rows = ref<ProductBatchRow[]>([])
const pagination = ref<PaginationState>({ pageIndex: 0, pageSize: 50 })

const canExpire = computed(() => auth.canAccessPage('stock.expire'))

/** A lot is disabled (never sold) once its expiry date has passed. UI-only. */
function localToday() {
  const now = new Date()
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}
const today = localToday()
function isExpired(row: ProductBatchRow) {
  if (row.status === 'Expired') return true
  return Boolean(row.expiryDate) && String(row.expiryDate) < today
}

const productRecord = computed(() => {
  const id = String(props.product?.id || '')
  if (!id) return props.product
  return store.list('products').find(row => String(row.id) === id) || props.product
})

async function loadBatches() {
  if (!props.product?.id) {
    rows.value = []
    return
  }
  loading.value = true
  loadError.value = null
  try {
    const result = await stockQueries.listProductBatches(String(props.product.id), {
      status: 'All',
      limit: 500,
      requestScope: 'manage',
    })
    rows.value = result.items
  }
  catch (error: unknown) {
    if (isRequestAborted(error)) return
    loadError.value = apiErrorMessage(error, t('api.somethingWentWrong'))
    rows.value = []
  }
  finally {
    loading.value = false
  }
}

watch(() => props.product?.id, () => {
  search.value = ''
  pagination.value = { pageIndex: 0, pageSize: pagination.value.pageSize }
  void loadBatches()
}, { immediate: true })

const filteredRows = computed(() => {
  const needle = search.value.trim().toLowerCase()
  if (!needle) return rows.value
  return rows.value.filter(row =>
    [row.batchNo, row.purchaseNo]
      .map(value => String(value ?? '').toLowerCase())
      .some(value => value.includes(needle)))
})

function bumpPricingRail() {
  recordAccess?.set?.('__batchPricingEpoch', Date.now())
}

async function expireBatch(row: ProductBatchRow) {
  if (!props.product?.id || props.disabled || busyId.value) return
  const remaining = Number(row.remainingQty || 0)
  if (!(remaining > 0)) {
    toast.add({ title: t('app.stock.expireBatchEmpty'), color: 'warning' })
    return
  }
  const ok = await confirm({
    title: t('app.stock.expireBatchTitle'),
    description: t('app.stock.expireBatchConfirm', {
      qty: remaining,
      batch: row.batchNo,
      uom: String(productRecord.value?.uomSymbol || productRecord.value?.uom || ''),
    }),
    confirmLabel: t('app.stock.expireBatchAction'),
    confirmColor: 'error',
  })
  if (!ok) return

  busyId.value = row.id
  try {
    const record = await posCommands.createStockOperation({
      type: 'expiry',
      productId: String(props.product.id),
      quantity: remaining,
      note: t('app.stock.expireNote'),
      batchNo: row.batchNo,
      expiryDate: row.expiryDate || null,
    })
    toast.add({
      title: t('app.stock.expireBatchDone', { batch: row.batchNo }),
      description: `${record.reference} \u00b7 ${t('app.fields.quantity')} ${record.quantity}`,
      color: 'success',
    })
    await loadBatches()
    void store.fetchList('products')
    void store.fetchList('stockMovements')
    bumpPricingRail()
  }
  catch (error: unknown) {
    if (!isApiErrorHandled(error)) {
      toast.add({
        title: t('app.stock.expireBatchFailed'),
        description: apiErrorMessage(error, t('app.stock.expireBatchFailed')),
        color: 'error',
      })
    }
  }
  finally {
    busyId.value = ''
  }
}

const dim = (row: ProductBatchRow, base: string) =>
  `${base}${isExpired(row) ? ' opacity-60' : ''}`

const columns = computed<TableColumn<ProductBatchRow & Record<string, unknown>>[]>(() => [
  {
    accessorKey: '__no',
    header: t('app.stock.pricingNo'),
    enableSorting: false,
    meta: { class: { td: 'w-10 text-muted tabular-nums', th: 'w-10' } },
    cell: ({ row }) => h('span', { class: 'text-muted tabular-nums' }, String(row.index + 1)),
  },
  {
    accessorKey: 'batchNo',
    header: t('app.stock.batchNo'),
    enableSorting: false,
    cell: ({ row }) => h('span', {
      class: dim(row.original, 'inline-flex items-center gap-1.5 whitespace-nowrap'),
    }, [
      h('span', { class: 'font-medium text-highlighted' }, row.original.batchNo),
      ...(isExpired(row.original)
        ? [h(UBadge, { size: 'sm', color: 'warning', variant: 'subtle' }, () => t('app.stock.batchExpired'))]
        : []),
    ]),
  },
  {
    accessorKey: 'purchaseDate',
    header: t('app.stock.purchaseDate'),
    enableSorting: false,
    cell: ({ row }) => h('span', { class: dim(row.original, 'whitespace-nowrap tabular-nums text-muted') },
      row.original.purchaseDate ? formatDate(row.original.purchaseDate) : '—'),
  },
  {
    accessorKey: 'unitCost',
    header: t('app.stock.costPrice'),
    enableSorting: false,
    meta: { class: { td: 'text-end tabular-nums whitespace-nowrap', th: 'text-end' } },
    cell: ({ row }) => h('span', { class: dim(row.original, 'text-end tabular-nums') }, formatMoney(row.original.unitCost)),
  },
  {
    accessorKey: 'salePrice',
    header: t('app.stock.salePrice'),
    enableSorting: false,
    meta: { class: { td: 'text-end tabular-nums whitespace-nowrap', th: 'text-end' } },
    cell: ({ row }) => h('span', { class: dim(row.original, 'text-end tabular-nums font-medium') },
      formatMoney(Number(row.original.salePrice ?? productRecord.value?.salePrice ?? 0))),
  },
  {
    accessorKey: 'remainingQty',
    header: t('app.stock.currentStock'),
    enableSorting: false,
    meta: { class: { td: 'text-end tabular-nums whitespace-nowrap', th: 'text-end' } },
    cell: ({ row }) => h('span', {
      class: `${dim(row.original, 'text-end tabular-nums font-medium')} ${row.original.remainingQty <= 0 ? 'text-muted' : ''}`,
    }, stockBreakdownLabel(row.original.remainingQty, productRecord.value)),
  },
  {
    accessorKey: 'expiryDate',
    header: t('app.stock.expiryDateCol'),
    enableSorting: false,
    cell: ({ row }) => h('span', { class: dim(row.original, 'whitespace-nowrap tabular-nums text-muted') },
      row.original.expiryDate ? formatDate(row.original.expiryDate) : '—'),
  },
  {
    id: 'actions',
    header: '',
    enableSorting: false,
    meta: { class: { td: 'w-24 text-end whitespace-nowrap', th: 'w-24' } },
    cell: ({ row }) => canExpire.value
      ? h(UButton, {
          size: 'xs',
          color: 'error',
          variant: 'subtle',
          icon: 'i-lucide-calendar-x',
          label: t('app.stock.expireBatchAction'),
          loading: busyId.value === row.original.id,
          disabled: props.disabled || busyId.value === row.original.id || Number(row.original.remainingQty) <= 0,
          onClick: () => { void expireBatch(row.original) },
        })
      : h('span'),
  },
])
</script>

<template>
  <div class="flex min-h-112 min-w-0 flex-1 flex-col gap-2">
    <p v-if="loadError" class="text-sm text-error">{{ loadError }}</p>
    <TableAppListTable
      v-model:search="search"
      v-model:pagination="pagination"
      class="min-h-0 flex-1"
      :data="filteredRows"
      :columns="columns"
      :loading="loading"
      :get-row-id="row => String(row.id)"
      :search-placeholder="t('app.stock.batchSearch')"
      :empty-title="t('app.stock.batchEmpty')"
      :empty-description="t('app.stock.batchEmptyHint')"
    />
  </div>
</template>
