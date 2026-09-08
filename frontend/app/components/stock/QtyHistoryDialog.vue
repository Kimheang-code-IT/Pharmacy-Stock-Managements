<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { PaginationState } from '@tanstack/vue-table'
import { h } from 'vue'
import type { AppRecord } from '~/config/admin-seed'
import type { ProductHistoryRow, StockHistoryKind } from '~/repositories/contracts/entities'
import { useStockQueries } from '~/repositories/index'

/**
 * Read-only stock movement history for one product, opened from the Stock
 * list quantity cells (Stock In / Stock Out / Damage only — Current Stock is
 * display-only and never opens this dialog). Rows come from the product-
 * scoped repository contract (GET /stock/products/{id}/history) filtered by
 * movement kind:
 * - stock_in  → 'Stock In' (+ 'Sale Return')
 * - stock_out → 'Sale'
 * - damage    → 'Damage'
 *
 * Width rule (spec): the dialog is wide — about 70% of the viewport on
 * desktop (`wide` on CommonAppDialog); ~95vw on small screens. The body
 * reuses TableAppListTable (search + date range + pagination); search and
 * date filtering stay client-side via AppListTable over the fetched rows.
 */
const props = withDefaults(defineProps<{
  product?: AppRecord | null
  kind?: StockHistoryKind
}>(), {
  product: null,
  kind: 'stock_in' as StockHistoryKind,
})

const open = defineModel<boolean>('open', { default: false })

const stockQueries = useStockQueries()
const { t } = useI18n()

const KIND_TITLE_KEYS: Record<StockHistoryKind, string> = {
  stock_in: 'app.stock.historyTitleStockIn',
  stock_out: 'app.stock.historyTitleStockOut',
  damage: 'app.stock.historyTitleDamage',
}

const search = ref('')
const dateStart = ref('')
const dateEnd = ref('')
const pagination = ref<PaginationState>({ pageIndex: 0, pageSize: 20 })
/** Suppresses AppListTable's default empty hint (this dialog is read-only). */
const noEmptyDescription = ' '
const loading = ref(false)
const loadError = ref<string | null>(null)
const historyRows = ref<ProductHistoryRow[]>([])

async function loadHistory() {
  if (!props.product) return
  loading.value = true
  loadError.value = null
  try {
    // Product-scoped fetch (kind-filtered server-side in HTTP mode) — never
    // a download of the whole stockMovements collection.
    const result = await stockQueries.listProductHistory(String(props.product.id), {
      type: props.kind,
      limit: 500,
    })
    historyRows.value = result.items
  }
  catch (error: unknown) {
    loadError.value = error instanceof Error ? error.message : String(error)
    historyRows.value = []
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
  void loadHistory()
})

/** Table row type: keeps AppListTable's `Record<string, unknown>` constraint. */
type HistoryRow = ProductHistoryRow & Record<string, unknown>

const rows = computed<HistoryRow[]>(() => {
  if (!props.product) return []
  const filtered = (!dateStart.value && !dateEnd.value)
    ? historyRows.value
    : historyRows.value.filter((row) => {
        if (dateStart.value && row.date < dateStart.value) return false
        if (dateEnd.value && row.date > dateEnd.value) return false
        return true
      })
  return filtered.map(row => ({ ...row, quantity: Number(row.quantity || 0) }))
})

const columns = computed<TableColumn<HistoryRow>[]>(() => [
  {
    accessorKey: 'date',
    header: t('app.fields.date'),
    enableSorting: false,
    meta: { class: { td: 'whitespace-nowrap text-muted', th: '' } },
  },
  {
    accessorKey: 'type',
    header: t('app.fields.type'),
    enableSorting: false,
  },
  {
    accessorKey: 'quantity',
    header: t('app.fields.quantity'),
    enableSorting: false,
    meta: { class: { td: 'text-end tabular-nums whitespace-nowrap', th: 'text-end' } },
    cell: ({ row }) => {
      const qty = row.original.quantity
      return h('span', { class: `font-medium ${qty < 0 ? 'text-error' : 'text-success'}` }, String(qty))
    },
  },
  {
    accessorKey: 'reference',
    header: t('app.debt.reference'),
    enableSorting: false,
    cell: ({ row }) => h('span', { class: 'font-medium' }, String(row.original.reference ?? '')),
  },
  {
    accessorKey: 'user',
    header: t('app.fields.user'),
    enableSorting: false,
    cell: ({ row }) => h('span', { class: 'whitespace-nowrap text-muted' }, String(row.original.user ?? '')),
  },
  {
    accessorKey: 'note',
    header: t('app.fields.note'),
    enableSorting: false,
    cell: ({ row }) => {
      const note = String(row.original.note || '')
      return h('span', { class: 'block max-w-48 truncate text-muted', title: note }, note || '—')
    },
  },
])

const title = computed(() => {
  const label = t(KIND_TITLE_KEYS[props.kind])
  return props.product ? `${props.product.name} · ${label}` : label
})
</script>

<template>
  <CommonAppDialog
    v-model:open="open"
    :title="title"
    icon="i-lucide-arrow-left-right"
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
        :empty-title="t('app.stock.noHistory')"
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
