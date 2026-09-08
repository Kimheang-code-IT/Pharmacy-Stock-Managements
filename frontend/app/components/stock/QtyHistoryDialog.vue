<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { PaginationState } from '@tanstack/vue-table'
import { h } from 'vue'
import type { AppRecord } from '~/config/admin-seed'
import { STOCK_OPERATION_META } from '~/config/pos-options'
import type { ProductHistoryRow, StockHistoryKind } from '~/repositories/contracts/entities'
import { usePosCommands, useStockQueries } from '~/repositories/index'
import { conversionForUom, convertToBase, multiplyDecimalSafe } from '~/utils/stock/uom-conversions'

/**
 * Stock movement history for one product, opened from the Stock list
 * quantity cells (Stock In / Stock Out / Damage only — Current Stock is
 * display-only and never opens this dialog).
 *
 * Stock In / Damage toolbars open a nested Add dialog stacked on top of this
 * history dialog (same pattern as Sale Price → Add Sale Price).
 */
const props = withDefaults(defineProps<{
  product?: AppRecord | null
  kind?: StockHistoryKind
  /** When true, show Add on Stock In / Damage toolbars (products.operate/edit). */
  canAdd?: boolean
  /** Bump after an external stock op so the open dialog reloads rows. */
  reloadKey?: number
}>(), {
  product: null,
  kind: 'stock_in' as StockHistoryKind,
  canAdd: false,
  reloadKey: 0,
})

const emit = defineEmits<{
  /** Parent refreshes products / movements after a successful nested add. */
  saved: []
}>()

const open = defineModel<boolean>('open', { default: false })

const store = useAppDataStore()
const stockQueries = useStockQueries()
const posCommands = usePosCommands()
const toast = useToast()
const { t } = useI18n()

const KIND_TITLE_KEYS: Record<StockHistoryKind, string> = {
  stock_in: 'app.stock.historyTitleStockIn',
  stock_out: 'app.stock.historyTitleStockOut',
  damage: 'app.stock.historyTitleDamage',
}

const ADD_LABEL_KEYS: Record<'stock_in' | 'damage', string> = {
  stock_in: 'app.stock.addStockIn',
  damage: 'app.stock.addDamage',
}

type AddKind = 'stock_in' | 'damage'

const canShowAdd = computed(() =>
  props.canAdd && (props.kind === 'stock_in' || props.kind === 'damage'))

const addKind = computed<AddKind | null>(() =>
  (props.kind === 'stock_in' || props.kind === 'damage') ? props.kind : null)

const addMeta = computed(() => addKind.value ? STOCK_OPERATION_META[addKind.value] : null)

const addLabel = computed(() => addKind.value ? t(ADD_LABEL_KEYS[addKind.value]) : '')

const search = ref('')
const dateStart = ref('')
const dateEnd = ref('')
const pagination = ref<PaginationState>({ pageIndex: 0, pageSize: 20 })
/** Suppresses AppListTable's default empty hint. */
const noEmptyDescription = ' '
const loading = ref(false)
const loadError = ref<string | null>(null)
const historyRows = ref<ProductHistoryRow[]>([])

const addOpen = ref(false)
const addBusy = ref(false)
const addQuantity = ref<number | undefined>()
const addNote = ref('')
const addUomId = ref('')
const addUnitCost = ref<number | undefined>()

/** Live product row (UOM / cost) — prefer store cache, fall back to prop. */
const productRecord = computed(() => {
  const id = String(props.product?.id || '')
  if (!id) return props.product
  return store.list('products').find(row => String(row.id) === id) || props.product
})

const uomOptions = computed(() => {
  const product = productRecord.value
  if (!product) return []
  const conversions = Array.isArray(product.uomConversions)
    ? product.uomConversions as Array<Record<string, unknown>>
    : []
  if (conversions.length) {
    return conversions
      .filter(row => row.uomId)
      .map(row => ({ label: String(row.uomSymbol || row.uomId || ''), value: String(row.uomId) }))
  }
  return [{ label: String(product.uomSymbol || product.uom || ''), value: String(product.uomId || '') }]
})

const addConversion = computed(() => conversionForUom(productRecord.value, addUomId.value))

const addFactor = computed(() =>
  addKind.value === 'stock_in' ? (addConversion.value?.factorToBase ?? 1) : 1)

const addUomSymbol = computed(() =>
  addConversion.value?.uomSymbol
  || String(productRecord.value?.uomSymbol || productRecord.value?.uom || ''))

const baseUomSymbol = computed(() =>
  String(productRecord.value?.uomSymbol || productRecord.value?.uom || ''))

const stockInConvertHint = computed(() => {
  if (addKind.value !== 'stock_in' || !addQuantity.value) return ''
  const baseQty = convertToBase(addQuantity.value, addFactor.value)
  return `${addQuantity.value} ${addUomSymbol.value} = ${baseQty} ${baseUomSymbol.value}`
})

async function loadHistory() {
  if (!props.product) return
  loading.value = true
  loadError.value = null
  try {
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
  if (!value) {
    addOpen.value = false
    return
  }
  search.value = ''
  dateStart.value = ''
  dateEnd.value = ''
  pagination.value = { pageIndex: 0, pageSize: pagination.value.pageSize }
  void loadHistory()
})

watch(() => props.reloadKey, (value, previous) => {
  if (!open.value || value === previous) return
  void loadHistory()
})

function openAdd() {
  if (!canShowAdd.value || !productRecord.value || !addKind.value) return
  addQuantity.value = undefined
  addNote.value = ''
  addUomId.value = String(productRecord.value.uomId || '')
  addUnitCost.value = undefined
  addOpen.value = true
}

watch(addUomId, (uomId) => {
  const product = productRecord.value
  if (!product || addKind.value !== 'stock_in') return
  const conversion = conversionForUom(product, uomId)
  const suggested = conversion?.costPrice != null
    ? conversion.costPrice
    : multiplyDecimalSafe(Number(product.costPrice || 0), conversion?.factorToBase ?? 1)
  addUnitCost.value = suggested > 0 ? suggested : undefined
})

async function submitAdd() {
  if (!productRecord.value || !addKind.value || !addQuantity.value) return
  addBusy.value = true
  try {
    const record = await posCommands.createStockOperation({
      type: addKind.value,
      productId: String(productRecord.value.id),
      quantity: Number(addQuantity.value),
      note: addNote.value || null,
      ...(addKind.value === 'stock_in'
        ? {
            uomId: addUomId.value || undefined,
            uomSymbol: addUomSymbol.value || undefined,
            factorToBase: addFactor.value,
            ...(addUnitCost.value != null ? { unitCost: Number(addUnitCost.value) } : {}),
          }
        : {}),
    })
    addOpen.value = false
    await loadHistory()
    emit('saved')
    toast.add({
      title: `${addMeta.value?.label}: ${record.reference}`,
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
    addBusy.value = false
  }
}

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

const productLabel = computed(() => {
  const product = productRecord.value
  if (!product) return ''
  return `${product.code || ''} · ${product.name || ''}`.replace(/^\s*·\s*/, '')
})

/** Nested add must sit above the wide history dialog. */
const nestedDialogUi = {
  overlay: 'z-[200]',
  content: 'z-[200]',
}
</script>

<template>
  <CommonAppDialog
    v-model:open="open"
    :title="title"
    icon="i-lucide-arrow-left-right"
    wide
  >
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
      >
        <template
          v-if="canShowAdd"
          #actions
        >
          <UButton
            size="sm"
            :icon="addMeta?.icon"
            class="shrink-0"
            :label="addLabel"
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

  <!-- Nested on top of history (Sale Price Add pattern + elevated z-index). -->
  <CommonAppDialog
    v-model:open="addOpen"
    :title="addLabel"
    :icon="addMeta?.icon"
    :color="addMeta?.color"
    size="sm"
    :loading="addBusy"
    :ui="nestedDialogUi"
  >
    <div class="w-full space-y-3">
      <CommonAppTextField
        :model-value="productLabel"
        :label="t('app.pos.product')"
        :disabled="true"
        class="w-full"
      />
      <CommonAppSelectMenuField
        v-if="addKind === 'stock_in'"
        v-model="addUomId"
        :items="uomOptions"
        :label="t('app.pos.uom')"
        class="w-full"
      />
      <CommonAppNumberField
        v-model="addQuantity"
        :label="addKind === 'damage' ? `${t('app.fields.quantity')} (−)` : t('app.fields.quantity')"
        :required="true"
        :min="0"
        :step="1"
        class="w-full"
      />
      <p
        v-if="addKind === 'stock_in' && stockInConvertHint"
        class="text-xs text-muted"
      >
        {{ stockInConvertHint }}
      </p>
      <CommonAppMoneyField
        v-if="addKind === 'stock_in'"
        v-model="addUnitCost"
        :label="t('app.stock.convCost')"
        :min="0"
        :step="0.01"
        :help="t('app.stock.convCostHint')"
        class="w-full"
      />
      <CommonAppTextareaField
        v-model="addNote"
        :label="t('app.fields.note')"
        :rows="2"
        class="w-full"
      />
      <p
        v-if="addKind === 'damage'"
        class="text-xs text-muted"
      >
        {{ t('app.stock.negativeHint') }}
      </p>
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
          :color="addMeta?.color"
          :icon="addMeta?.icon"
          :loading="addBusy"
          :disabled="!addQuantity"
          :label="addLabel"
          @click="submitAdd"
        />
      </div>
    </template>
  </CommonAppDialog>
</template>
