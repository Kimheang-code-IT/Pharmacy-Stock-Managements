<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { PaginationState } from '@tanstack/vue-table'
import { UButton, UInputNumber, USelect } from '#components'
import { h } from 'vue'
import { moduleDocumentRecordKey } from '~/utils/module/document-tabs'
import type { UomConversion } from '~/utils/stock/uom-conversions'

/**
 * Pricing editor on the product form (spec §2.1.3 / §5.9 Pricing tab). A
 * compact editable table bound to the record's `uomConversions` array and
 * saved with the same Save as the General tab.
 *
 * Columns (exact UI — only these): **No** (1-based, display only),
 * **Original UOM** (active Setup UOM; unique per product; the POS sell
 * unit), **Convert UOM** (read-only, defaults to the product base UOM from
 * General — shown `symbol — name`), **Conversion qty** (`factor_to_base` > 0;
 * the base=base row is locked at 1), **Sale price** (per Original UOM,
 * > 0), **Delete** (pack rows only; the base row stays so the product
 * always keeps one sellable row). No Default-sale column or field — the POS
 * pre-select unit is always the product's base UOM (save-time
 * normalization stores exactly one `isDefaultSale` on the base row). No
 * Cost column, no Sell-on-POS column, no separate Convert UOM tab.
 */
const props = withDefaults(defineProps<{
  modelValue?: unknown
  disabled?: boolean
}>(), {
  modelValue: () => [],
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [UomConversion[]]
}>()

const { t } = useI18n()
const toast = useToast()
const store = useAppDataStore()
const recordAccess = inject(moduleDocumentRecordKey, null)

const baseUomId = computed(() => String(recordAccess?.get('uomId') ?? ''))
const baseUomSymbol = computed(() => {
  const base = store.list('uoms').find(uom => String(uom.id) === baseUomId.value)
  return String(base?.symbol || base?.name || '')
})
/** `symbol — name` label of the product base UOM (Convert UOM default). */
const baseUomLabel = computed(() => {
  const base = store.list('uoms').find(uom => String(uom.id) === baseUomId.value)
  if (!base) return '—'
  const symbol = String(base.symbol || base.name || '')
  const name = String(base.name || '')
  return name && name !== symbol ? `${symbol} — ${name}` : symbol
})
/** Base-row sale price lives on the product record (`salePrice`), not only in `uomConversions`. */
const baseSalePrice = computed(() => Number(recordAccess?.get('salePrice') ?? 0))

function setBaseSalePrice(value: number | null) {
  recordAccess?.set?.('salePrice', Number(value ?? 0))
}

/** Active Setup UOMs only (spec §2.1.3: inactive UOMs never appear here). */
const activeUoms = computed(() => store.list('uoms')
  .filter(uom => String(uom.status || 'Active') === 'Active')
  .map(uom => ({
    label: `${String(uom.symbol || uom.name)} — ${String(uom.name)}`,
    value: String(uom.id),
    symbol: String(uom.symbol || uom.name || ''),
  })))

type PricingRow = UomConversion & Record<string, unknown> & { __key: string, __base: boolean }

const search = ref('')
const pagination = ref<PaginationState>({ pageIndex: 0, pageSize: 50 })

function toRow(raw: Record<string, unknown>, index: number): PricingRow {
  const uomId = String(raw.uomId ?? '')
  return {
    uomId,
    uomSymbol: String(raw.uomSymbol ?? ''),
    convertUomId: String(raw.convertUomId ?? '') || baseUomId.value,
    convertUomSymbol: String(raw.convertUomSymbol ?? ''),
    factorToBase: Number(raw.factorToBase ?? 1),
    salePrice: Number(raw.salePrice ?? 0),
    costPrice: raw.costPrice == null || raw.costPrice === '' ? null : Number(raw.costPrice),
    __key: `row:${index}:${uomId}`,
    __base: uomId === baseUomId.value,
  }
}

const savedRows = computed<PricingRow[]>(() => {
  const list = Array.isArray(props.modelValue) ? props.modelValue as Array<Record<string, unknown>> : []
  return list.map((row, index) => toRow(row, index))
})

/**
 * Displayed rows. When nothing is saved yet (new product / legacy record),
 * the base=base row is shown as a draft (factor 1, the record's sale price)
 * — it is materialized into `uomConversions` on the first edit, and the
 * save-time normalization keeps it even when untouched.
 */
const draftBaseRow = computed<PricingRow>(() => ({
  uomId: baseUomId.value,
  uomSymbol: baseUomSymbol.value,
  convertUomId: baseUomId.value,
  convertUomSymbol: baseUomSymbol.value,
  factorToBase: 1,
  salePrice: baseSalePrice.value,
  costPrice: null,
  __key: 'draft-base',
  __base: true,
}))

const rows = computed<PricingRow[]>(() =>
  savedRows.value.length ? savedRows.value : [draftBaseRow.value])

function emitRows(next: PricingRow[]) {
  emit('update:modelValue', next.map(({ __key, __base, ...row }) => ({ ...row })))
}

function updateRow(key: string, patch: Partial<UomConversion>) {
  emitRows(rows.value.map(row => row.__key === key ? { ...row, ...patch } : row))
}

function removeRow(key: string) {
  // Spec: keep at least one sellable row — the base row can never be deleted.
  emitRows(rows.value.filter(row => row.__key !== key))
}

/** UOM options for a row: active UOMs not already used by another row. */
function uomOptionsFor(row: PricingRow) {
  const used = new Set(rows.value.filter(item => item.__key !== row.__key).map(item => item.uomId))
  return activeUoms.value.filter(option => !used.has(option.value))
}

function addRow() {
  // Never offer the base UOM (it already has its own row) or a used UOM.
  const free = activeUoms.value.find(option =>
    option.value !== baseUomId.value && !rows.value.some(row => row.uomId === option.value))
  if (!free) {
    toast.add({ title: t('app.stock.convNoUomLeft'), color: 'warning' })
    return
  }
  const conversion: UomConversion = {
    uomId: free.value,
    uomSymbol: free.symbol,
    convertUomId: baseUomId.value,
    convertUomSymbol: baseUomSymbol.value,
    factorToBase: 1,
    salePrice: 0,
    costPrice: null,
  }
  emitRows([...rows.value, { ...conversion, __key: `new:${Date.now()}`, __base: false }])
}

function onUomChange(key: string, uomId: string) {
  if (rows.value.some(row => row.__key !== key && row.uomId === uomId)) {
    toast.add({ title: t('app.stock.convDuplicate'), color: 'error' })
    return
  }
  const option = activeUoms.value.find(item => item.value === uomId)
  updateRow(key, { uomId, uomSymbol: option?.symbol || '' })
}

/** Conversion helper label: `1 box = 12 pcs`. */
function factorLabel(row: PricingRow) {
  return t('app.stock.convFactorLabel', {
    from: row.uomSymbol || '…',
    n: row.factorToBase,
    base: baseUomSymbol.value || '…',
  })
}

const columns = computed<TableColumn<PricingRow>[]>(() => [
  {
    accessorKey: '__no',
    header: t('app.stock.pricingNo'),
    enableSorting: false,
    meta: { class: { td: 'w-10 text-muted tabular-nums', th: 'w-10' } },
    cell: ({ row }) => h('span', String(row.index + 1)),
  },
  {
    accessorKey: 'uomId',
    header: t('app.stock.pricingOriginalUom'),
    enableSorting: false,
    cell: ({ row }) => row.original.__base
      ? h('span', { class: 'text-sm text-highlighted whitespace-nowrap' }, baseUomLabel.value)
      : h(USelect, {
          modelValue: row.original.uomId || undefined,
          items: uomOptionsFor(row.original),
          placeholder: t('app.stock.pricingOriginalUom'),
          size: 'xs',
          class: 'w-40',
          disabled: props.disabled,
          'onUpdate:modelValue': (value: string) => onUomChange(row.original.__key, String(value)),
        }),
  },
  {
    accessorKey: 'convertUomId',
    header: t('app.stock.pricingConvertUom'),
    enableSorting: false,
    // Read-only: Convert UOM defaults to the product base UOM (General).
    cell: () => h('span', { class: 'text-sm text-muted whitespace-nowrap' }, baseUomLabel.value),
  },
  {
    accessorKey: 'factorToBase',
    header: t('app.stock.pricingQty'),
    enableSorting: false,
    meta: { class: { td: 'whitespace-nowrap', th: 'whitespace-nowrap' } },
    cell: ({ row }) => h('div', { class: 'flex flex-col gap-0.5' }, [
      h(UInputNumber, {
        modelValue: row.original.__base ? 1 : row.original.factorToBase,
        min: 0,
        step: 0.5,
        size: 'xs',
        class: 'w-24 tabular-nums',
        disabled: props.disabled || row.original.__base,
        'onUpdate:modelValue': (value: number | null) => updateRow(row.original.__key, { factorToBase: Number(value ?? 0) }),
      }),
      row.original.__base
        ? null
        : h('span', { class: 'text-[10px] text-muted' }, factorLabel(row.original)),
    ]),
  },
  {
    accessorKey: 'salePrice',
    header: t('app.stock.convSale'),
    enableSorting: false,
    meta: { class: { td: 'whitespace-nowrap', th: '' } },
    cell: ({ row }) => h(UInputNumber, {
      modelValue: row.original.salePrice || undefined,
      min: 0,
      step: 0.01,
      size: 'xs',
      class: 'w-28 tabular-nums',
      disabled: props.disabled,
      'onUpdate:modelValue': (value: number | null) => {
        // The base row's price stays in sync with the product sale price.
        if (row.original.__base) setBaseSalePrice(value)
        updateRow(row.original.__key, { salePrice: Number(value ?? 0) })
      },
    }),
  },
  {
    accessorKey: '__actions',
    header: '',
    enableSorting: false,
    meta: { class: { td: 'w-10', th: 'w-10' } },
    cell: ({ row }) => h(UButton, {
      size: 'xs',
      color: 'error',
      variant: 'ghost',
      icon: 'i-lucide-trash-2',
      // The base UOM row is never deletable: the product must keep at least
      // one sellable Pricing row (spec §2.1.3).
      disabled: props.disabled || row.original.__base,
      ariaLabel: row.original.__base ? undefined : t('app.ui.delete'),
      onClick: () => removeRow(row.original.__key),
    }),
  },
])
</script>

<template>
  <div class="flex h-[420px] max-h-[60vh] min-h-0 min-w-0 flex-col">
    <TableAppListTable
      v-model:search="search"
      v-model:pagination="pagination"
      :data="rows"
      :columns="columns"
      :get-row-id="row => String(row.__key)"
      :search-placeholder="t('app.stock.convSearch')"
      :empty-title="t('app.stock.convEmpty')"
      :empty-description="t('app.stock.convEmptyHint')"
      :empty-actions="disabled ? [] : [{ icon: 'i-lucide-plus', label: t('app.stock.convAddRow'), onClick: addRow }]"
    >
      <template #actions>
        <UButton
          v-if="!disabled"
          size="sm"
          icon="i-lucide-plus"
          class="shrink-0"
          :label="t('app.stock.convAddRow')"
          @click="addRow"
        />
      </template>
    </TableAppListTable>
  </div>
</template>
