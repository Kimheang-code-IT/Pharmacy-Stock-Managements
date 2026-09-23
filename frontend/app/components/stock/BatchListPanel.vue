<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { PaginationState } from '@tanstack/vue-table'
import { UBadge, UButton } from '#components'
import { h } from 'vue'
import type { AppRecord } from '~/config/admin-seed'
import type { ProductBatchRow } from '~/repositories/contracts/entities'
import { useStockQueries } from '~/repositories/index'
import { batchStatusColor } from '~/utils/stock/batch-lots'
import { apiErrorMessage } from '~/utils/api/errors'
import { formatMoney } from '~/utils/format/format-service'
import { multiplyDecimalSafe, stockBreakdownLabel } from '~/utils/stock/uom-conversions'

/**
 * Read-only batch lots of one product (product detail Batches tab).
 * Rows derive from the immutable movement ledger through the stock-queries
 * repository — loaded only when this tab is open (no global batch fetch).
 * Clicking a row opens the read-only batch detail drawer.
 */
const props = withDefaults(defineProps<{
  product?: AppRecord | null
}>(), {
  product: null,
})

const open = defineModel<boolean>('open', { default: false })

const stockQueries = useStockQueries()
const { t } = useI18n()

const BATCH_FILTERS = ['Active', 'Expired', 'Depleted', 'All'] as const
type BatchFilter = typeof BATCH_FILTERS[number]

const statusFilter = ref<BatchFilter>('Active')
const search = ref('')
const loading = ref(false)
const loadError = ref<string | null>(null)
const rows = ref<ProductBatchRow[]>([])
const pagination = ref<PaginationState>({ pageIndex: 0, pageSize: 20 })

const detailOpen = ref(false)
const detailBatch = ref<ProductBatchRow | null>(null)

const productRecord = computed(() => {
  const id = String(props.product?.id || '')
  if (!id) return props.product
  return useAppDataStore().list('products').find(row => String(row.id) === id) || props.product
})

const title = computed(() =>
  props.product ? `${props.product.name} · ${t('app.stock.batchesTab')}` : t('app.stock.batchesTab'))

async function loadBatches() {
  if (!props.product) return
  loading.value = true
  loadError.value = null
  try {
    const result = await stockQueries.listProductBatches(String(props.product.id), {
      status: statusFilter.value,
      limit: 500,
    })
    rows.value = result.items
  }
  catch (error: unknown) {
    loadError.value = apiErrorMessage(error, t('api.somethingWentWrong'))
    rows.value = []
  }
  finally {
    loading.value = false
  }
}

watch(open, (value) => {
  if (!value) {
    detailOpen.value = false
    return
  }
  search.value = ''
  statusFilter.value = 'Active'
  pagination.value = { pageIndex: 0, pageSize: pagination.value.pageSize }
  void loadBatches()
})

watch(statusFilter, () => {
  if (open.value) void loadBatches()
})

const filteredRows = computed(() => {
  const needle = search.value.trim().toLowerCase()
  if (!needle) return rows.value
  return rows.value.filter(row =>
    [row.batchNo, row.purchaseNo, row.supplier]
      .map(value => String(value ?? '').toLowerCase())
      .some(value => value.includes(needle)))
})

const statusItems = computed(() =>
  BATCH_FILTERS.map(value => ({ label: t(`app.stock.batch${value}`), value })))

function openDetail(row: ProductBatchRow) {
  detailBatch.value = row
  detailOpen.value = true
}

const noCell = ({ row }: { row: { index: number } }) =>
  h('span', { class: 'text-muted tabular-nums' }, String(row.index + 1))

const batchCell = ({ row }: { row: { original: ProductBatchRow } }) =>
  h('button', {
    type: 'button',
    class: 'font-medium text-highlighted hover:text-primary hover:underline whitespace-nowrap',
    onClick: () => openDetail(row.original),
  }, row.original.batchNo)

const expiryCell = ({ row }: { row: { original: ProductBatchRow } }) =>
  h('span', { class: 'whitespace-nowrap text-muted tabular-nums' }, row.original.expiryDate || '—')

const qtyCell = (value: number) =>
  h('span', {
    class: `text-end tabular-nums whitespace-nowrap font-medium ${value <= 0 ? 'text-muted' : ''}`,
  }, stockBreakdownLabel(value, productRecord.value))

const costCell = ({ row }: { row: { original: ProductBatchRow } }) =>
  h('span', { class: 'text-end tabular-nums whitespace-nowrap' }, formatMoney(row.original.unitCost))

const createdCell = ({ row }: { row: { original: ProductBatchRow } }) =>
  h('span', { class: 'whitespace-nowrap text-muted' }, row.original.createdDate?.slice(0, 10) || '—')

/** Batch amount = received qty × unit cost (purchase value of the lot). */
const amountCell = ({ row }: { row: { original: ProductBatchRow } }) =>
  h('span', { class: 'text-end tabular-nums whitespace-nowrap' },
    formatMoney(multiplyDecimalSafe(Number(row.original.receivedQty || 0), Number(row.original.unitCost || 0))))

/** Sale price is the Product + UOM price — never a batch cost (spec). */
const salePriceCell = () =>
  h('span', { class: 'text-end tabular-nums whitespace-nowrap font-medium' },
    formatMoney(Number(productRecord.value?.salePrice ?? 0)))

const statusCell = ({ row }: { row: { original: ProductBatchRow } }) =>
  h(UBadge, {
    color: batchStatusColor(row.original.status),
    variant: 'subtle',
    size: 'sm',
  }, () => t(`app.stock.batch${row.original.status}`))

const columns = computed<TableColumn<ProductBatchRow & Record<string, unknown>>[]>(() => [
  {
    accessorKey: '__no',
    header: t('app.stock.pricingNo'),
    enableSorting: false,
    meta: { class: { td: 'w-10 text-muted tabular-nums', th: 'w-10' } },
    cell: noCell as never,
  },
  {
    accessorKey: 'batchNo',
    header: t('app.stock.batchNo'),
    enableSorting: false,
    cell: batchCell as never,
  },
  {
    accessorKey: 'createdDate',
    header: t('app.fields.created'),
    enableSorting: false,
    cell: createdCell as never,
  },
  {
    accessorKey: 'receivedQty',
    header: t('app.stock.receivedQty'),
    enableSorting: false,
    meta: { class: { td: 'text-end tabular-nums whitespace-nowrap', th: 'text-end' } },
    cell: ({ row }) => qtyCell(row.original.receivedQty) as never,
  },
  {
    accessorKey: 'unitCost',
    header: t('app.stock.costPrice'),
    enableSorting: false,
    meta: { class: { td: 'text-end tabular-nums whitespace-nowrap', th: 'text-end' } },
    cell: costCell as never,
  },
  {
    accessorKey: 'amount',
    header: t('app.fields.amount'),
    enableSorting: false,
    meta: { class: { td: 'text-end tabular-nums whitespace-nowrap', th: 'text-end' } },
    cell: amountCell as never,
  },
  {
    accessorKey: 'expiryDate',
    header: t('app.stock.expiryDateCol'),
    enableSorting: false,
    meta: { class: { td: 'whitespace-nowrap', th: 'whitespace-nowrap' } },
    cell: expiryCell as never,
  },
  {
    accessorKey: 'remainingQty',
    header: t('app.stock.inStock'),
    enableSorting: false,
    meta: { class: { td: 'text-end tabular-nums whitespace-nowrap', th: 'text-end' } },
    cell: ({ row }) => qtyCell(row.original.remainingQty) as never,
  },
  {
    accessorKey: 'salePrice',
    header: t('app.stock.salePrice'),
    enableSorting: false,
    meta: { class: { td: 'text-end tabular-nums whitespace-nowrap', th: 'text-end' } },
    cell: salePriceCell as never,
  },
  {
    accessorKey: 'status',
    header: t('app.stock.batchStatus'),
    enableSorting: false,
    cell: statusCell as never,
  },
])

const detailItems = computed(() => {
  const batch = detailBatch.value
  if (!batch) return []
  return [
    { label: t('app.pos.product'), value: String(props.product?.name || '') },
    { label: t('app.pos.barcode'), value: String(props.product?.barcode || '—') },
    { label: t('app.stock.batchNo'), value: batch.batchNo },
    { label: t('app.stock.expiryDateCol'), value: batch.expiryDate || '—' },
    { label: t('app.stock.receivedQty'), value: String(batch.receivedQty) },
    { label: t('app.stock.remainingQty'), value: String(batch.remainingQty) },
    { label: t('app.stock.baseUom'), value: String(productRecord.value?.uomSymbol || productRecord.value?.uom || '—') },
    { label: t('app.stock.unitCost'), value: formatMoney(batch.unitCost) },
    { label: t('app.nav.suppliers'), value: batch.supplier || '—' },
    { label: t('app.reports.purchaseNo'), value: batch.purchaseNo || '—' },
    { label: t('app.fields.created'), value: batch.createdDate?.slice(0, 10) || '—' },
    { label: t('app.stock.batchStatus'), value: t(`app.stock.batch${batch.status}`) },
  ]
})
</script>

<template>
  <CommonAppDialog
    v-model:open="open"
    :title="title"
    icon="i-lucide-boxes"
    wide
  >
    <div class="flex h-[60vh] max-h-[70vh] min-h-[55vh] min-w-0 flex-col overflow-hidden">
      <p v-if="loadError" class="px-3 pt-2 text-sm text-error">{{ loadError }}</p>
      <TableAppListTable
        v-model:search="search"
        v-model:pagination="pagination"
        :data="filteredRows"
        :columns="columns"
        :loading="loading"
        :filters-active="statusFilter !== 'All'"
        :empty-title="t('app.stock.batchEmpty')"
        :empty-description="t('app.stock.batchEmptyHint')"
      >
        <template #filters>
          <USelect
            v-model="statusFilter"
            :items="statusItems"
            value-key="value"
            size="sm"
            class="w-36"
            :aria-label="t('app.stock.batchStatus')"
          />
        </template>
      </TableAppListTable>
      <p class="px-3 pb-2 text-xs text-muted">{{ t('app.stock.batchSalePriceHint') }}</p>
    </div>

    <template #footer>
      <div class="flex w-full justify-end">
        <UButton
          color="neutral"
          variant="ghost"
          :label="t('actions.close')"
          @click="open = false"
        />
      </div>
    </template>
  </CommonAppDialog>

  <!-- Read-only batch detail drawer (no quantity editing — spec). -->
  <CommonAppDialog
    v-model:open="detailOpen"
    :title="`${t('app.stock.batch')} · ${detailBatch?.batchNo ?? ''}`"
    icon="i-lucide-boxes"
    size="md"
  >
    <div class="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-2">
      <div v-for="item in detailItems" :key="item.label">
        <p class="text-[11px] text-muted">{{ item.label }}</p>
        <p class="font-medium">{{ item.value }}</p>
      </div>
    </div>
    <template #footer>
      <div class="flex w-full justify-end">
        <UButton
          color="neutral"
          variant="ghost"
          :label="t('actions.close')"
          @click="detailOpen = false"
        />
      </div>
    </template>
  </CommonAppDialog>
</template>