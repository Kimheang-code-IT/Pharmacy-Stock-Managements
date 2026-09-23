<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { PaginationState } from '@tanstack/vue-table'
import { CommonAppMoneyField, UButton, UCheckbox, UInputNumber, USelect } from '#components'
import { h } from 'vue'
import { moduleDocumentRecordKey } from '~/utils/module/document-tabs'
import { useCurrencyRateDialog } from '~/composables/common/useCurrencyRateDialog'
import type { AppRecord } from '~/config/admin-seed'
import type { SalePriceVersionSelection, UomConversion } from '~/utils/stock/uom-conversions'
import { cleanConversionFactor, factorForDirection, factorFromDirection } from '~/utils/stock/uom-conversions'

/**
 * Pricing editor on the product form (spec §2.1.3 / §5.9 Pricing tab).
 *
 * Left: UOM × sale-price table. Right: Batch rail (General + stock lots).
 * Selecting General edits live `uomConversions` (saved with the product).
 * Selecting a batch loads an editable draft; Save on the rail posts a
 * batch-scoped sale-price version for POS checkout merge.
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
const batchRail = ref<{ saveBatchPrice: () => Promise<void>, busy: boolean } | null>(null)

/** Whole loaded product record for the batch rail (id + saved Pricing rows). */
const productRecord = computed(() => (recordAccess?.get('__record') as AppRecord | null) ?? null)

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

function setBaseSalePrice(value: number | null | undefined) {
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

/**
 * UI-only entry direction per row (`__key` → reverse). The stored
 * `factorToBase` never changes — reverse only flips the input/display to
 * "1 Convert = N Original". Kept outside the row so it survives the parent
 * re-emitting the model (which never carries this field).
 */
const reverseDirections = ref<Record<string, boolean>>({})

function isReverse(row: PricingRow): boolean {
  const override = reverseDirections.value[row.__key]
  if (override !== undefined) return override
  // Auto-pick the friendlier side: a sub-1 factor (e.g. 0.083333) displays as
  // its reciprocal (1 unit = 12 pcs) unless the user toggles it.
  return row.factorToBase > 0 && row.factorToBase < 1
}

function toggleDirection(row: PricingRow) {
  if (row.__base || effectiveDisabled.value) return
  reverseDirections.value = { ...reverseDirections.value, [row.__key]: !isReverse(row) }
}

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
    isActive: raw.isActive !== false && raw.is_active !== false,
    __key: `row:${index}:${uomId}`,
    __base: uomId === baseUomId.value,
  }
}

const savedRows = computed<PricingRow[]>(() => {
  const list = Array.isArray(props.modelValue) ? props.modelValue as Array<Record<string, unknown>> : []
  return list.map((row, index) => {
    const mapped = toRow(row, index)
    if (mapped.__base) mapped.salePrice = baseSalePrice.value
    return mapped
  })
})

const draftBaseRow = computed<PricingRow>(() => ({
  uomId: baseUomId.value,
  uomSymbol: baseUomSymbol.value,
  convertUomId: baseUomId.value,
  convertUomSymbol: baseUomSymbol.value,
  factorToBase: 1,
  salePrice: baseSalePrice.value,
  costPrice: null,
  isActive: true,
  __key: 'draft-base',
  __base: true,
}))

const versionSelection = computed<SalePriceVersionSelection | null>(() => {
  const raw = recordAccess?.get('__salePriceSelection')
  return raw && typeof raw === 'object' ? raw as SalePriceVersionSelection : null
})

/** Batch scope selected in the rail — table shows that lot's draft prices. */
const isBatchScope = computed(() => versionSelection.value?.scope === 'batch')
const batchEditable = computed(() => isBatchScope.value && versionSelection.value?.editable !== false)
/** Legacy read-only history preview (non-editable selection). */
const isReadOnlyPreview = computed(() =>
  Boolean(versionSelection.value) && !batchEditable.value && versionSelection.value?.scope !== 'general')
const effectiveDisabled = computed(() => props.disabled || isReadOnlyPreview.value)

const currencyOptions = [
  { value: 'USD' as const, symbol: '$', labelKey: 'app.pos.currencyUsd' },
  { value: 'KHR' as const, symbol: '៛', labelKey: 'app.pos.currencyKhr' },
]
const displayCurrency = ref<'USD' | 'KHR'>('USD')
const exchangeRate = ref<number | undefined>()
const {
  dialogOpen: currencyRateDialogOpen,
  toggle: toggleDisplayCurrency,
  confirm: confirmDisplayCurrency,
} = useCurrencyRateDialog({ currency: displayCurrency, rate: exchangeRate })

const conversionRate = computed(() => Number(exchangeRate.value || 0))

function toDisplayPrice(usd: number) {
  const value = Number(usd) || 0
  if (displayCurrency.value !== 'KHR') return value
  return conversionRate.value > 0 ? Math.round(value * conversionRate.value * 100) / 100 : value
}

function toUsdPrice(amount: number | undefined) {
  const value = Number(amount) || 0
  if (displayCurrency.value !== 'KHR') return value
  return conversionRate.value > 0 ? Math.round((value / conversionRate.value) * 100) / 100 : value
}

const selectionRows = ref<PricingRow[]>([])

watch(versionSelection, (selected) => {
  if (!selected || selected.scope !== 'batch') {
    selectionRows.value = []
    return
  }
  const uomRows = selected.uomPrices.length
    ? selected.uomPrices
    : [{
        uomId: baseUomId.value,
        uomSymbol: baseUomSymbol.value,
        factorToBase: 1,
        salePrice: selected.salePrice,
        isDefaultSale: true,
      }]
  selectionRows.value = uomRows.map((uom, index) => ({
    uomId: String(uom.uomId),
    uomSymbol: String(uom.uomSymbol || ''),
    convertUomId: baseUomId.value,
    convertUomSymbol: baseUomSymbol.value,
    factorToBase: Number(uom.factorToBase) || 1,
    salePrice: Number(uom.salePrice) || 0,
    costPrice: null,
    isDefaultSale: uom.isDefaultSale === true,
    isActive: uom.isActive !== false,
    __key: `batch:${selected.batchNo || 'x'}:${index}:${String(uom.uomId)}`,
    __base: String(uom.uomId) === baseUomId.value,
  }))
}, { immediate: true })

const rows = computed<PricingRow[]>(() =>
  isBatchScope.value
    ? selectionRows.value
    : (savedRows.value.length ? savedRows.value : [draftBaseRow.value]))

function clearVersionSelection() {
  recordAccess?.set?.('__salePriceSelection', null)
}

function emitRows(next: PricingRow[]) {
  emit('update:modelValue', next.map(({ __key, __base, ...row }) => ({ ...row })))
}

/** Persist batch draft edits back into `__salePriceSelection`. */
function emitBatchDraft(next: PricingRow[]) {
  selectionRows.value = next
  const selected = versionSelection.value
  if (!selected || !recordAccess?.set) return
  const uomPrices = next.map(row => ({
    uomId: row.uomId,
    uomSymbol: row.uomSymbol,
    factorToBase: Number(row.factorToBase) || 1,
    salePrice: Number(row.salePrice) || 0,
    isDefaultSale: row.__base || row.isDefaultSale === true,
    isActive: row.isActive !== false,
  }))
  const defaultPrice = uomPrices.find(row => row.isDefaultSale)?.salePrice ?? uomPrices[0]?.salePrice ?? 0
  recordAccess.set('__salePriceSelection', {
    ...selected,
    salePrice: Number(defaultPrice) || 0,
    uomPrices,
  })
}

function updateRow(key: string, patch: Partial<UomConversion>) {
  if (effectiveDisabled.value) return
  const next = rows.value.map(row => row.__key === key ? { ...row, ...patch } : row)
  if (batchEditable.value) {
    emitBatchDraft(next)
    return
  }
  emitRows(next)
}

function removeRow(key: string) {
  if (isReadOnlyPreview.value) return
  const next = rows.value.filter(row => row.__key !== key)
  if (batchEditable.value) {
    emitBatchDraft(next)
    return
  }
  emitRows(next)
}

function uomOptionsFor(row: PricingRow) {
  const used = new Set(rows.value.filter(item => item.__key !== row.__key).map(item => item.uomId))
  return activeUoms.value.filter(option => !used.has(option.value))
}

function addRow() {
  if (isReadOnlyPreview.value) return
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
  const next = [...rows.value, { ...conversion, __key: `new:${Date.now()}`, __base: false }]
  if (batchEditable.value) {
    emitBatchDraft(next)
    return
  }
  emitRows(next)
}

function onUomChange(key: string, uomId: string) {
  if (rows.value.some(row => row.__key !== key && row.uomId === uomId)) {
    toast.add({ title: t('app.stock.convDuplicate'), color: 'error' })
    return
  }
  const option = activeUoms.value.find(item => item.value === uomId)
  updateRow(key, { uomId, uomSymbol: option?.symbol || '' })
}

function factorLabel(row: PricingRow) {
  // Direction flips which side is "1" — the stored factor stays the same.
  const reverse = isReverse(row)
  const from = reverse ? (baseUomSymbol.value || '…') : (row.uomSymbol || '…')
  const to = reverse ? (row.uomSymbol || '…') : (baseUomSymbol.value || '…')
  return t('app.stock.convFactorLabel', {
    from,
    n: cleanConversionFactor(factorForDirection(row.factorToBase, reverse)),
    base: to,
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
    cell: ({ row }) => {
      if (isReadOnlyPreview.value) {
        return h('span', { class: 'text-sm text-highlighted whitespace-nowrap' },
          row.original.uomSymbol || row.original.uomId || baseUomLabel.value)
      }
      return row.original.__base
        ? h('span', { class: 'text-sm text-highlighted whitespace-nowrap' }, baseUomLabel.value)
        : h(USelect, {
            modelValue: row.original.uomId || undefined,
            items: uomOptionsFor(row.original),
            placeholder: t('app.stock.pricingOriginalUom'),
            size: 'xs',
            class: 'w-40',
            disabled: props.disabled,
            'onUpdate:modelValue': (value: string) => onUomChange(row.original.__key, String(value)),
          })
    },
  },
  {
    accessorKey: 'convertUomId',
    header: t('app.stock.pricingConvertUom'),
    enableSorting: false,
    cell: () => h('span', { class: 'text-sm text-muted whitespace-nowrap' }, baseUomLabel.value),
  },
  {
    accessorKey: 'factorToBase',
    header: t('app.stock.pricingQty'),
    enableSorting: false,
    meta: { class: { td: 'whitespace-nowrap', th: 'whitespace-nowrap' } },
    cell: ({ row }) => h('div', { class: 'flex flex-col gap-0.5' }, [
      h('div', { class: 'flex items-center gap-1' }, [
        h(UInputNumber, {
          modelValue: row.original.__base
            ? 1
            : cleanConversionFactor(factorForDirection(row.original.factorToBase, isReverse(row.original))),
          min: 0,
          step: isReverse(row.original) ? 0.01 : 0.5,
          size: 'xs',
          class: 'w-24 tabular-nums',
          disabled: effectiveDisabled.value || row.original.__base,
          'onUpdate:modelValue': (value: number | null) =>
            updateRow(row.original.__key, {
              factorToBase: factorFromDirection(value, isReverse(row.original)),
            }),
        }),
        row.original.__base
          ? null
          : h(UButton, {
              size: 'xs',
              variant: 'ghost',
              color: 'neutral',
              icon: 'i-lucide-arrow-left-right',
              title: t('app.stock.convDirectionToggle'),
              'aria-label': t('app.stock.convDirectionToggle'),
              disabled: effectiveDisabled.value,
              onClick: () => toggleDirection(row.original),
            }),
      ]),
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
    cell: ({ row }) => h(CommonAppMoneyField, {
      modelValue: toDisplayPrice(row.original.salePrice) || undefined,
      currency: displayCurrency.value,
      inline: true,
      min: 0,
      step: 0.01,
      size: 'xs',
      class: 'w-28 tabular-nums',
      align: 'right',
      disabled: effectiveDisabled.value,
      'onUpdate:modelValue': (value: number | undefined) => {
        const usd = toUsdPrice(value)
        if (row.original.__base && !isBatchScope.value) setBaseSalePrice(usd)
        updateRow(row.original.__key, { salePrice: usd })
      },
    }),
  },
  {
    accessorKey: '__active',
    header: t('app.stock.convActiveForPos'),
    enableSorting: false,
    meta: { class: { td: 'w-16 text-center', th: 'w-16 text-center' } },
    cell: ({ row }) => h(UCheckbox, {
      modelValue: row.original.isActive !== false,
      size: 'xs',
      disabled: effectiveDisabled.value,
      'aria-label': t('app.stock.convActiveForPos'),
      'onUpdate:modelValue': (value: unknown) =>
        updateRow(row.original.__key, { isActive: value === true }),
    }),
  },
  {
    accessorKey: '__actions',
    header: '',
    enableSorting: false,
    meta: { class: { td: 'w-10', th: 'w-10' } },
    cell: ({ row }) => isReadOnlyPreview.value
      ? null
      : h(UButton, {
          size: 'xs',
          color: 'error',
          variant: 'ghost',
          icon: 'i-lucide-trash-2',
          disabled: props.disabled || row.original.__base,
          ariaLabel: row.original.__base ? undefined : t('app.ui.delete'),
          onClick: () => removeRow(row.original.__key),
        }),
  },
])
</script>

<template>
  <div class="flex min-h-112 min-w-0 flex-1 flex-col gap-4 xl:flex-row xl:items-stretch">
    <div class="flex min-h-0 min-w-0 flex-1 flex-col gap-2">
      <div
        v-if="isBatchScope && versionSelection"
        class="flex items-center justify-between gap-2 rounded-sm border border-primary/20 bg-primary/5 px-3 py-1.5 text-xs text-highlighted"
      >
        <span class="flex min-w-0 items-center gap-1.5 font-medium">
          <UIcon name="i-lucide-package" class="size-3.5 shrink-0 text-primary" />
          <span class="truncate">
            {{ t('app.stock.batchPricingEditing', { batch: versionSelection.batchNo || '—' }) }}
          </span>
        </span>
        <div class="flex shrink-0 items-center gap-1">
          <UButton
            v-if="!disabled"
            size="xs"
            color="primary"
            variant="soft"
            icon="i-lucide-save"
            :label="t('app.stock.batchPricingSave')"
            :loading="Boolean(batchRail?.busy)"
            @click="batchRail?.saveBatchPrice()"
          />
          <UButton
            size="xs"
            variant="ghost"
            color="neutral"
            icon="i-lucide-x"
            :label="t('app.stock.priceHistoryPreviewClear')"
            @click="clearVersionSelection"
          />
        </div>
      </div>

      <TableAppListTable
        v-model:search="search"
        v-model:pagination="pagination"
        class="min-h-0 flex-1"
        :data="rows"
        :columns="columns"
        :get-row-id="row => String(row.__key)"
        :search-placeholder="t('app.stock.convSearch')"
        :empty-title="t('app.stock.convEmpty')"
        :empty-description="t('app.stock.convEmptyHint')"
        :empty-actions="(disabled || isReadOnlyPreview) ? [] : [{ icon: 'i-lucide-plus', label: t('app.stock.convAddRow'), onClick: addRow }]"
      >
        <template #actions>
          <UFieldGroup size="sm">
            <UButton
              v-for="option in currencyOptions"
              :key="option.value"
              :label="option.symbol"
              :color="displayCurrency === option.value ? 'primary' : 'neutral'"
              :variant="displayCurrency === option.value ? 'soft' : 'outline'"
              :title="t(option.labelKey)"
              :aria-label="t(option.labelKey)"
              :aria-pressed="displayCurrency === option.value"
              @click="toggleDisplayCurrency(option.value)"
            />
          </UFieldGroup>
          <UButton
            v-if="!disabled && !isReadOnlyPreview"
            size="sm"
            icon="i-lucide-plus"
            class="shrink-0"
            :label="t('app.stock.convAddRow')"
            @click="addRow"
          />
        </template>
      </TableAppListTable>
    </div>

    <CommonAppExchangeRateDialog
      v-model:open="currencyRateDialogOpen"
      :initial-rate="exchangeRate"
      @confirm="confirmDisplayCurrency"
    />

    <StockBatchPricingRail
      ref="batchRail"
      class="min-h-112 xl:min-h-0"
      :product="productRecord"
      :disabled="disabled"
    />
  </div>
</template>
