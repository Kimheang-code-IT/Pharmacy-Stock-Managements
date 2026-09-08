<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { PaginationState } from '@tanstack/vue-table'
import { h } from 'vue'
import type { AppRecord } from '~/config/admin-seed'
import type { ProductCostHistoryRow } from '~/repositories/contracts/entities'
import { useStockQueries } from '~/repositories/index'
import { formatMoney } from '~/composables/module/useModule'

/**
 * Read-only Cost Price history for one product, opened from the Stock list
 * **Cost** cell (spec: Cost Price cell). Not a page; not editable here —
 * costs are created by Stock In.
 *
 * Source: the product-scoped repository contract (GET
 * /stock/products/{id}/cost-history). Lots are versioned oldest → newest
 * (1, 2, 3…) and displayed newest first.
 *
 * Width rule (spec): wide dialog (~70vw desktop, ~95vw small screens) with a
 * `TableAppListTable` body — search + date range + pagination.
 */
const props = withDefaults(defineProps<{
  product?: AppRecord | null
}>(), {
  product: null,
})

const open = defineModel<boolean>('open', { default: false })

const stockQueries = useStockQueries()
const preferences = usePreferencesStore()
const { t } = useI18n()
const money = (value: unknown) => formatMoney(value, preferences.currency)

const search = ref('')
const dateStart = ref('')
const dateEnd = ref('')
const pagination = ref<PaginationState>({ pageIndex: 0, pageSize: 20 })
/** Suppresses AppListTable's default empty hint (this dialog is read-only). */
const noEmptyDescription = ' '
const loading = ref(false)
const loadError = ref<string | null>(null)
const costRows = ref<ProductCostHistoryRow[]>([])

async function loadCostHistory() {
  if (!props.product) return
  loading.value = true
  loadError.value = null
  try {
    // Product-scoped fetch — never a download of the whole stockIns collection.
    const result = await stockQueries.listProductCostHistory(String(props.product.id), { limit: 500 })
    costRows.value = result.items
  }
  catch (error: unknown) {
    loadError.value = error instanceof Error ? error.message : String(error)
    costRows.value = []
  }
  finally {
    loading.value = false
  }
}

watch(open, (value) => {
  if (!value) return
  search.value = ''
  dateStart.value = ''
  dateEnd.value = ''
  pagination.value = { pageIndex: 0, pageSize: pagination.value.pageSize }
  void loadCostHistory()
})

/** Table row type: keeps AppListTable's `Record<string, unknown>` constraint. */
type CostRow = ProductCostHistoryRow & Record<string, unknown>

const rows = computed<CostRow[]>(() => {
  if (!props.product) return []
  const filtered = (!dateStart.value && !dateEnd.value)
    ? costRows.value
    : costRows.value.filter((row) => {
        if (dateStart.value && row.date < dateStart.value) return false
        if (dateEnd.value && row.date > dateEnd.value) return false
        return true
      })
  return filtered.map(row => ({ ...row, amount: Number(row.amount || 0) }))
})

const columns = computed<TableColumn<CostRow>[]>(() => [
  {
    accessorKey: 'date',
    header: t('app.fields.date'),
    enableSorting: false,
    meta: { class: { td: 'whitespace-nowrap text-muted', th: '' } },
  },
  {
    accessorKey: 'product',
    header: t('app.fields.name'),
    enableSorting: false,
  },
  {
    accessorKey: 'unitCost',
    header: t('app.stock.costPrice'),
    enableSorting: false,
    meta: { class: { td: 'text-end tabular-nums whitespace-nowrap', th: 'text-end' } },
    cell: ({ row }) => h('span', { class: 'font-medium' }, money(row.original.unitCost)),
  },
  {
    accessorKey: 'quantity',
    header: t('app.fields.quantity'),
    enableSorting: false,
    meta: { class: { td: 'text-end tabular-nums whitespace-nowrap', th: 'text-end' } },
  },
  {
    accessorKey: 'amount',
    header: t('app.fields.amount'),
    enableSorting: false,
    meta: { class: { td: 'text-end tabular-nums whitespace-nowrap', th: 'text-end' } },
    cell: ({ row }) => h('span', { class: 'font-medium' }, money(row.original.amount)),
  },
  {
    accessorKey: 'version',
    header: t('app.stock.version'),
    enableSorting: false,
    meta: { class: { td: 'text-end tabular-nums whitespace-nowrap text-muted', th: 'text-end' } },
  },
])

const title = computed(() => props.product
  ? `${props.product.name} · ${t('app.stock.costPriceHistory')}`
  : t('app.stock.costPriceHistory'))
</script>

<template>
  <CommonAppDialog
    v-model:open="open"
    :title="title"
    icon="i-lucide-tags"
    wide
  >
    <!-- Real height so the flex-fill AppListTable renders at full size. -->
    <div class="flex h-[60vh] max-h-[70vh] min-h-[55vh] min-w-0 flex-col overflow-hidden">
      <p v-if="loadError" class="px-3 pt-2 text-sm text-error">{{ loadError }}</p>
      <TableAppListTable
        v-model:search="search"
        v-model:date-start="dateStart"
        v-model:date-end="dateEnd"
        v-model:pagination="pagination"
        :data="rows"
        :columns="columns"
        :loading="loading"
        :show-date-range="true"
        :date-label="t('app.ui.date')"
        :empty-title="t('app.stock.emptyCostHistory')"
        :empty-description="noEmptyDescription"
      />
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
</template>
