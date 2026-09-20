<script setup lang="ts">
import type { AppRecord } from '~/config/admin-seed'
import type { ProductBatchRow, ProductSalePriceRow } from '~/repositories/contracts/entities'
import { useStockQueries } from '~/repositories/index'
import { formatDate } from '~/utils/format/format-service'
import { apiErrorMessage, isApiErrorHandled, isRequestAborted } from '~/utils/api/errors'
import { moduleDocumentRecordKey } from '~/utils/module/document-tabs'
import type { BatchPricingCard, SalePriceVersionSelection } from '~/utils/stock/uom-conversions'
import {
  buildBatchPricingCards,
  pricingRowsFor,
  salePriceVersionSelection,
} from '~/utils/stock/uom-conversions'

/**
 * Batch pricing rail (product Pricing tab). Replaces the old sale-price
 * version list with stock-lot cards plus a General card.
 *
 * - General → live product `uomConversions` / `salePrice` (saved with the form)
 * - Batch card → loads that lot's sale prices into the table; Save / Activate
 *   use the existing sale-price APIs with `batchNo` (POS checkout merges them)
 */
const props = withDefaults(defineProps<{
  product?: AppRecord | null
  disabled?: boolean
}>(), {
  product: null,
  disabled: false,
})

const stockQueries = useStockQueries()
const { t } = useI18n()
const toast = useToast()
const recordAccess = inject(moduleDocumentRecordKey, null)

const selection = computed<SalePriceVersionSelection | null>(() => {
  const raw = recordAccess?.get('__salePriceSelection')
  return raw && typeof raw === 'object' ? raw as SalePriceVersionSelection : null
})

const loading = ref(false)
const busy = ref(false)
const loadError = ref<string | null>(null)
const lots = ref<ProductBatchRow[]>([])
const salePrices = ref<ProductSalePriceRow[]>([])

const cards = computed<BatchPricingCard[]>(() => {
  const generalRows = pricingRowsFor(props.product).map(row => ({
    uomId: row.uomId,
    uomSymbol: row.uomSymbol,
    factorToBase: row.factorToBase,
    salePrice: row.salePrice,
    isDefaultSale: row.isDefaultSale,
  }))
  return buildBatchPricingCards({
    lots: lots.value,
    salePrices: salePrices.value,
    generalSalePrice: Number(props.product?.salePrice ?? 0) || null,
    generalUomPrices: generalRows,
    baseUomId: String(props.product?.uomId ?? ''),
  // Only stock-lot cards: the General card is hidden on this rail.
  }).filter(card => card.scope !== 'general')
})

const selectedKey = computed(() => {
  const selected = selection.value
  if (!selected || selected.scope === 'general') return 'general'
  return selected.batchNo ? `batch:${selected.batchNo}` : 'general'
})

async function load() {
  if (!props.product?.id) {
    lots.value = []
    salePrices.value = []
    return
  }
  loading.value = true
  loadError.value = null
  try {
    const productId = String(props.product.id)
    const [batchResult, priceResult] = await Promise.all([
      stockQueries.listProductBatches(productId, { status: 'All', limit: 200, requestScope: 'pricing-rail' }),
      stockQueries.listSalePrices(productId, { limit: 100, requestScope: 'pricing-rail' }),
    ])
    lots.value = batchResult.items
    salePrices.value = priceResult.items
  }
  catch (error: unknown) {
    if (isRequestAborted(error)) return
    loadError.value = apiErrorMessage(error, t('api.somethingWentWrong'))
    lots.value = []
    salePrices.value = []
  }
  finally {
    loading.value = false
  }
}

watch(() => props.product?.id, () => {
  if (recordAccess?.get('__salePriceSelection')) {
    recordAccess?.set?.('__salePriceSelection', null)
  }
  void load()
}, { immediate: true })

watch(() => recordAccess?.get('__batchPricingEpoch'), () => {
  if (props.product?.id) void load()
})

function isSelected(card: BatchPricingCard) {
  return selectedKey.value === card.key
}

function draftUomPrices(card: BatchPricingCard): SalePriceVersionSelection['uomPrices'] {
  if (card.uomPrices.length) return card.uomPrices.map(uom => ({ ...uom }))
  return pricingRowsFor(props.product).map(row => ({
    uomId: row.uomId,
    uomSymbol: row.uomSymbol,
    factorToBase: row.factorToBase,
    salePrice: row.salePrice,
    isDefaultSale: row.isDefaultSale,
    isActive: row.isActive !== false,
  }))
}

function selectCard(card: BatchPricingCard) {
  if (!recordAccess?.set) return
  if (isSelected(card)) {
    recordAccess.set('__salePriceSelection', null)
    return
  }
  const uomPrices = draftUomPrices(card)
  const defaultPrice = uomPrices.find(row => row.isDefaultSale)?.salePrice
    ?? uomPrices[0]?.salePrice
    ?? card.salePrice
    ?? 0
  recordAccess.set('__salePriceSelection', salePriceVersionSelection({
    id: card.priceId || '',
    version: card.priceVersion || 0,
    batchNo: card.batchNo,
    scope: 'batch',
    isActive: card.isPriceActive,
    salePrice: Number(defaultPrice) || 0,
    expiryDate: card.expiryDate,
    editable: true,
    uomPrices,
  }))
}

/** Checkbox: make this lot's price the active one for POS (or deactivate). */
async function toggleActive(card: BatchPricingCard, value: boolean) {
  if (!card.priceId) return
  if (value) await activateCard(card)
  else await deactivateCard(card)
}

async function activateCard(card: BatchPricingCard) {
  if (!props.product?.id || !card.priceId || busy.value) return
  busy.value = true
  try {
    await stockQueries.activateSalePrice(String(props.product.id), card.priceId)
    toast.add({ title: t('app.stock.priceHistoryActivated'), color: 'success' })
    await load()
    const refreshed = cards.value.find(item => item.key === card.key)
    if (refreshed && selectedKey.value === card.key) {
      const uomPrices = draftUomPrices(refreshed)
      recordAccess?.set?.('__salePriceSelection', salePriceVersionSelection({
        id: refreshed.priceId || '',
        version: refreshed.priceVersion || 0,
        batchNo: refreshed.batchNo,
        scope: 'batch',
        isActive: true,
        salePrice: Number(refreshed.salePrice ?? 0),
        expiryDate: refreshed.expiryDate,
        editable: true,
        uomPrices,
      }))
    }
  }
  catch (error: unknown) {
    if (!isApiErrorHandled(error)) {
      toast.add({
        title: t('app.stock.priceHistoryFailed'),
        description: apiErrorMessage(error, t('app.stock.priceHistoryFailed')),
        color: 'error',
      })
    }
  }
  finally {
    busy.value = false
  }
}

async function deactivateCard(card: BatchPricingCard) {
  if (!card.priceId || busy.value) return
  busy.value = true
  try {
    await stockQueries.setSalePriceActive(card.priceId, false)
    toast.add({ title: t('app.stock.batchPricingDeactivated'), color: 'success' })
    await load()
    const refreshed = cards.value.find(item => item.key === card.key)
    if (refreshed && selectedKey.value === card.key) {
      // Keep the lot selected but refresh active flag / prices.
      const uomPrices = draftUomPrices(refreshed)
      recordAccess?.set?.('__salePriceSelection', salePriceVersionSelection({
        id: refreshed.priceId || '',
        version: refreshed.priceVersion || 0,
        batchNo: refreshed.batchNo,
        scope: 'batch',
        isActive: false,
        salePrice: Number(refreshed.salePrice ?? 0),
        expiryDate: refreshed.expiryDate,
        editable: true,
        uomPrices,
      }))
    }
  }
  catch (error: unknown) {
    if (!isApiErrorHandled(error)) {
      toast.add({
        title: t('app.stock.priceHistoryFailed'),
        description: apiErrorMessage(error, t('app.stock.priceHistoryFailed')),
        color: 'error',
      })
    }
  }
  finally {
    busy.value = false
  }
}

/** Persist the Pricing-table draft as a new active batch-scoped sale-price version. */
async function saveBatchPrice() {
  const selected = selection.value
  if (!props.product?.id || !selected || selected.scope !== 'batch' || !selected.batchNo) return
  if (busy.value || props.disabled) return
  const uomPrices = selected.uomPrices || []
  if (!uomPrices.length || uomPrices.some(row => !(Number(row.salePrice) > 0))) {
    toast.add({ title: t('app.stock.batchPricingInvalidPrices'), color: 'warning' })
    return
  }
  busy.value = true
  try {
    const defaultPrice = uomPrices.find(row => row.isDefaultSale) ?? uomPrices[0]!
    const created = await stockQueries.addSalePrice(String(props.product.id), {
      date: new Date().toISOString().slice(0, 10),
      salePrice: Number(defaultPrice.salePrice),
      batchNo: selected.batchNo,
      expiryDate: selected.expiryDate || null,
      uomPrices: uomPrices.map(row => ({
        uomId: row.uomId,
        uomSymbol: row.uomSymbol ?? null,
        factorToBase: Number(row.factorToBase) || 1,
        salePrice: Number(row.salePrice),
        isDefaultSale: row.isDefaultSale === true,
        isActive: row.isActive !== false,
      })),
    })
    toast.add({ title: t('app.stock.batchPricingSaved'), color: 'success' })
    await load()
    recordAccess?.set?.('__salePriceSelection', salePriceVersionSelection({
      ...created,
      scope: 'batch',
      editable: true,
      expiryDate: created.expiryDate ?? selected.expiryDate,
    }))
  }
  catch (error: unknown) {
    if (!isApiErrorHandled(error)) {
      toast.add({
        title: t('app.stock.priceHistoryFailed'),
        description: apiErrorMessage(error, t('app.stock.priceHistoryFailed')),
        color: 'error',
      })
    }
  }
  finally {
    busy.value = false
  }
}

defineExpose({ saveBatchPrice, reload: load, busy })
</script>

<template>
  <aside class="flex h-full min-h-0 w-full shrink-0 flex-col rounded-sm border border-default bg-default xl:w-80">
    <header class="flex items-center justify-between gap-2 border-b border-default px-3 py-2">
      <div class="min-w-0">
        <p class="truncate text-sm font-medium text-highlighted">{{ t('app.stock.batchPricingTitle') }}</p>
      </div>
    </header>

    <div class="min-h-0 flex-1 overflow-y-auto p-2">
      <p v-if="loadError" class="px-1 py-2 text-xs text-error">{{ loadError }}</p>
      <div v-else-if="loading" class="flex justify-center py-4">
        <UIcon name="i-lucide-loader-circle" class="size-4 animate-spin text-muted" />
      </div>
      <div v-else class="space-y-2">
        <div
          v-for="card in cards"
          :key="card.key"
          class="group flex w-full cursor-pointer items-start gap-2 rounded-sm border px-2.5 py-2 text-left transition-colors"
          :class="[
            isSelected(card) ? 'border-primary ring-1 ring-primary/30' : 'border-default',
            card.isPriceActive ? 'bg-primary/10' : 'bg-default hover:bg-elevated',
          ]"
          role="button"
          tabindex="0"
          @click="selectCard(card)"
          @keydown.enter.prevent="selectCard(card)"
          @keydown.space.prevent="selectCard(card)"
        >
          <span
            class="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full text-[10px] font-semibold"
            :class="card.isPriceActive ? 'bg-primary/20 text-primary' : 'bg-elevated text-muted'"
          >
            <UIcon name="i-lucide-package" class="size-3.5" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="flex items-center gap-1.5">
              <span class="truncate text-xs font-semibold text-highlighted">{{ card.label }}</span>
              <UBadge
                size="sm"
                variant="subtle"
                :color="card.isPriceActive ? 'success' : 'neutral'"
                :label="card.isPriceActive ? t('app.stock.priceHistoryActive') : t('app.stock.priceHistoryInactive')"
              />
            </span>
            <span class="mt-0.5 block text-[11px] text-muted">
              {{ t('app.stock.expiryDateCol') }}:
              {{ card.expiryDate ? formatDate(card.expiryDate) : '—' }}
            </span>
          </span>
          <!-- Active-for-POS checkbox (replaces the ⋯ menu). -->
          <UCheckbox
            class="mt-0.5 shrink-0"
            :model-value="card.isPriceActive"
            :disabled="disabled || busy || !card.priceId"
            :aria-label="t('app.stock.priceHistoryActive')"
            @click.stop
            @update:model-value="value => toggleActive(card, value === true)"
          />
        </div>

        <p v-if="lots.length === 0" class="px-1 pt-1 text-[11px] text-muted">
          {{ t('app.stock.batchPricingEmptyLots') }}
        </p>
      </div>
    </div>
  </aside>
</template>
