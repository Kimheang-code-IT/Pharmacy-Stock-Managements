<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { PaginationState } from '@tanstack/vue-table'
import { UCheckbox } from '#components'
import { h } from 'vue'
import type { AppRecord } from '~/config/admin-seed'
import type { ProductSalePriceRow } from '~/repositories/contracts/entities'
import { useStockQueries } from '~/repositories/index'
import { formatMoney } from '~/composables/module/useModule'

/**
 * Sale Price versions for one product, opened from the Stock list **Price**
 * cell (spec: Sale Price cell / product_sale_prices). Not a page.
 *
 * - Checkbox column = POS-active version: exactly one checked (radio
 *   behavior, NOT AppListTable bulk row-selection). Activating copies the
 *   price onto `products.salePrice` so the Stock list and POS update
 *   immediately.
 * - **Add Sale Price** opens a small nested form dialog (like Finance Add
 *   Expense) and creates version = MAX(version)+1, POS-active.
 * - Viewing needs `stock.view` (page-level); checkbox + add need
 *   `product.update` (hidden/disabled when denied).
 *
 * Rows come from the product-scoped repository contract
 * (GET/POST /products/{id}/sale-prices, POST …/{price_id}/activate).
 *
 * Width rule (spec): wide dialog (~70vw desktop) with a `TableAppListTable`
 * body — search + date range + pagination.
 */
const props = withDefaults(defineProps<{
  product?: AppRecord | null
}>(), {
  product: null,
})

const open = defineModel<boolean>('open', { default: false })

const store = useAppDataStore()
const stockQueries = useStockQueries()
const auth = useAuthStore()
const preferences = usePreferencesStore()
const toast = useToast()
const { t } = useI18n()
const money = (value: unknown) => formatMoney(value, preferences.currency)

const search = ref('')
const dateStart = ref('')
const dateEnd = ref('')
const pagination = ref<PaginationState>({ pageIndex: 0, pageSize: 20 })
/** Suppresses AppListTable's default empty hint (dialog stays informational). */
const noEmptyDescription = ' '
const activatingId = ref('')
const loading = ref(false)
const loadError = ref<string | null>(null)
const priceRows = ref<ProductSalePriceRow[]>([])
const addOpen = ref(false)
const addBusy = ref(false)
const addForm = reactive({
  date: '',
  price: undefined as number | undefined,
})

/** Spec: checkbox + Add mutate prices → require product.update. */
const canUpdate = computed(() => auth.canAccessPage('product.update'))

async function loadPrices() {
  if (!props.product) return
  loading.value = true
  loadError.value = null
  try {
    // Product-scoped fetch — no global sale-price dump.
    const result = await stockQueries.listSalePrices(String(props.product.id), { limit: 500 })
    priceRows.value = result.items
  }
  catch (error: unknown) {
    loadError.value = error instanceof Error ? error.message : String(error)
    priceRows.value = []
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
  void loadPrices()
})

/** Table row type: keeps AppListTable's `Record<string, unknown>` constraint. */
type SalePriceRow = ProductSalePriceRow & Record<string, unknown>

const versions = computed<SalePriceRow[]>(() => {
  if (!props.product) return []
  const filtered = (!dateStart.value && !dateEnd.value)
    ? priceRows.value
    : priceRows.value.filter((row) => {
        if (dateStart.value && row.date < dateStart.value) return false
        if (dateEnd.value && row.date > dateEnd.value) return false
        return true
      })
  // Newest versions first (highest version / latest date).
  return filtered.map(row => ({ ...row }))
})

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error)
}

/** Refresh the product row in the stock-list cache (salePrice may have changed). */
async function refreshProductRow() {
  if (!props.product) return
  await store.fetchOne('products', String(props.product.id))
}

/** Radio behavior: activating one version deactivates the others (repository rule). */
async function activateVersion(row: SalePriceRow) {
  if (!canUpdate.value || activatingId.value || !props.product) return
  if (row.isActive) return // exactly one stays checked
  activatingId.value = String(row.id)
  try {
    await stockQueries.activateSalePrice(String(props.product.id), String(row.id))
    await loadPrices()
    await refreshProductRow()
    toast.add({ title: t('app.stock.salePriceActivated'), color: 'success' })
  }
  catch (error: unknown) {
    toast.add({
      title: t('app.stock.salePriceSaveFailed'),
      description: errorMessage(error),
      color: 'error',
    })
  }
  finally {
    activatingId.value = ''
  }
}

/* --------------------------- Add Sale Price --------------------------- */

function openAdd() {
  addForm.date = new Date().toISOString().slice(0, 10)
  addForm.price = undefined
  addOpen.value = true
}

const canSubmitPrice = computed(() => Boolean(
  addForm.date
  && Number(addForm.price || 0) > 0,
))

async function submitPrice() {
  if (!canUpdate.value || !canSubmitPrice.value || addBusy.value || !props.product) return
  addBusy.value = true
  try {
    // Spec: exactly one active version per product — the repository retires
    // the current one and copies the new price onto products.salePrice.
    await stockQueries.addSalePrice(String(props.product.id), {
      date: addForm.date,
      salePrice: Number(addForm.price),
    })
    addOpen.value = false
    await loadPrices()
    await refreshProductRow()
    toast.add({ title: t('app.stock.salePriceSaved'), color: 'success' })
  }
  catch (error: unknown) {
    toast.add({
      title: t('app.stock.salePriceSaveFailed'),
      description: errorMessage(error),
      color: 'error',
    })
  }
  finally {
    addBusy.value = false
  }
}

/* ------------------------------ columns -------------------------------- */

const columns = computed<TableColumn<SalePriceRow>[]>(() => [
  {
    accessorKey: 'isActive',
    header: t('app.stock.posActive'),
    enableSorting: false,
    meta: { class: { td: 'w-10', th: 'w-10' } },
    cell: ({ row }) => h(UCheckbox, {
      modelValue: row.original.isActive,
      disabled: !canUpdate.value || activatingId.value === String(row.id),
      size: 'sm',
      // Keep the checkbox click away from the row-select handler.
      onClick: (event: Event) => event.stopPropagation(),
      'onUpdate:modelValue': () => void activateVersion(row.original),
    }),
  },
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
    accessorKey: 'salePrice',
    header: t('app.stock.salePrice'),
    enableSorting: false,
    meta: { class: { td: 'text-end tabular-nums whitespace-nowrap', th: 'text-end' } },
    cell: ({ row }) => h('span', {
      class: row.original.isActive ? 'font-medium text-highlighted' : 'font-medium',
    }, money(row.original.salePrice)),
  },
])

const title = computed(() => props.product
  ? `${props.product.name} · ${t('app.stock.salePriceHistory')}`
  : t('app.stock.salePriceHistory'))
</script>

<template>
  <CommonAppDialog
    v-model:open="open"
    :title="title"
    icon="i-lucide-badge-dollar-sign"
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
        :data="versions"
        :columns="columns"
        :loading="loading"
        :show-date-range="true"
        :date-label="t('app.ui.date')"
        :empty-title="t('app.stock.emptySalePrices')"
        :empty-description="noEmptyDescription"
      >
        <template #actions>
          <UButton
            v-if="canUpdate"
            size="sm"
            icon="i-lucide-plus"
            class="shrink-0"
            :label="t('app.stock.addSalePrice')"
            @click="openAdd"
          />
        </template>
      </TableAppListTable>
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

  <CommonAppDialog
    v-model:open="addOpen"
    :title="t('app.stock.addSalePrice')"
    icon="i-lucide-plus"
    size="sm"
    :loading="addBusy"
  >
    <div class="space-y-3">
      <CommonAppDateField
        v-model="addForm.date"
        :label="t('app.fields.date')"
        :required="true"
        granularity="day"
      />
      <CommonAppMoneyField
        v-model="addForm.price"
        :label="t('app.stock.salePrice')"
        :required="true"
        :min="0"
        :step="0.01"
        :help="Number(addForm.price || 0) <= 0 ? t('app.stock.pricePositive') : ''"
      />
    </div>

    <template #footer>
      <div class="flex w-full justify-end gap-2">
        <UButton
          color="neutral"
          variant="ghost"
          :label="t('common.cancel')"
          @click="addOpen = false"
        />
        <UButton
          icon="i-lucide-check"
          :loading="addBusy"
          :disabled="!canSubmitPrice"
          :label="t('app.stock.addSalePrice')"
          @click="submitPrice"
        />
      </div>
    </template>
  </CommonAppDialog>
</template>
