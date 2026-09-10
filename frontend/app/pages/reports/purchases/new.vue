<script setup lang="ts">
import { PAYMENT_METHODS } from '~/config/pos-options'
import type { ModuleTable } from '~/config/modules'
import { useAppHeader } from '~/composables/layout/useAppHeader'
import { usePosCommands } from '~/repositories/index'
import type {
  DocumentFieldSchema,
  DocumentTabSchema,
} from '~/types/stock-pos/common'
import { conversionForUom, multiplyDecimalSafe } from '~/utils/stock/uom-conversions'

/**
 * New Purchase (Stock In = purchase, spec §2.1.x) — built on the same
 * reusable document components as the Stock product document:
 * DocumentAppDocumentPage + schema-driven AppDocumentForm sections + the
 * generic TableAppLineTable (per-line `lines` table with the shared
 * subtotal/discount/tax/total + paid/outstanding footer). Saving posts ONE
 * /stock/in document — line UOM conversion, supplier debt for the unpaid
 * balance, the payment row, stock movements, the document number and the
 * audit entry all happen in that single backend transaction.
 *
 * Entry points: Purchase Report Create action, and the Stock In history
 * dialog Add button (routes here with ?productId= preselected).
 */
definePageMeta({
  titleKey: 'app.pages.purchaseReport',
  permission: 'stock.in',
})

const route = useRoute()
const store = useAppDataStore()
const { t } = useI18n()
const { setTitle, setBreadcrumbs, clear } = useAppHeader()
const posCommands = usePosCommands()
const toast = useToast()

onBeforeUnmount(clear)

setTitle(t('app.purchase.newTitle'))
setBreadcrumbs([
  { label: t('app.pages.purchaseReport'), to: '/reports/purchases' },
  { label: t('app.purchase.newTitle') },
])

function round2(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100
}

// ---------------------------------------------------------------- model

const model = reactive<Record<string, unknown>>({
  supplierId: '',
  transactionDate: '',
  paymentMethod: 'Cash',
  // Document currency: every amount on the purchase is in THIS currency.
  currency: 'USD',
  exchangeRate: undefined,
  note: '',
  discount: undefined,
  tax: undefined,
  paidNow: undefined,
  lines: [] as Array<Record<string, unknown>>,
})

function fieldValue(key: string): unknown {
  // Computed document totals consumed by the line-table footer.
  if (key === 'subtotal') return subtotal.value
  if (key === 'total') return total.value
  if (key === 'remaining') return remaining.value
  return model[key]
}

function setFieldValue(key: string, value: unknown): void {
  model[key] = value
}

// ---------------------------------------------------------------- masters

onMounted(async () => {
  await Promise.all([
    store.fetchList('suppliers'),
    store.fetchList('products'),
  ])
  if (!String(route.query.productId || '') && (model.lines as unknown[]).length === 0) {
    model.lines = [blankLine()]
  }
  if (!model.transactionDate) {
    model.transactionDate = new Date().toISOString().slice(0, 10)
  }
  // Stock In dialog entry: preselect the product to purchase into stock.
  const preselect = String(route.query.productId || '')
  if (preselect) {
    model.lines = [{ ...blankLine(), productId: preselect }]
  }
})

function blankLine(): Record<string, unknown> {
  return { productId: '', uomId: '', quantity: 0, unitAmount: 0, amount: 0 }
}

const supplierOptions = computed(() => store.list('suppliers').map(row => ({
  label: String(row.name || ''),
  value: String(row.id),
})))

function productFor(productId: string) {
  return store.list('products').find(row => String(row.id) === productId) || null
}

/** Products not already on another line (one line per product; the backend
 *  rejects duplicates on the same stock-in document). */
function availableProductOptions(row: Record<string, unknown>) {
  const lines = Array.isArray(model.lines) ? model.lines as Array<Record<string, unknown>> : []
  const excluded = new Set(lines
    .filter(other => other !== row)
    .map(other => String(other.productId || ''))
    .filter(Boolean))
  return store.list('products')
    .filter(row => !excluded.has(String(row.id)))
    .map(row => ({
      label: [String(row.code || row.sku || ''), String(row.name || '')]
        .filter(Boolean).join(' · '),
      value: String(row.id),
    }))
}

/** Pricing Original UOMs of the row's product (base UOM included). */
function rowUomOptions(row: Record<string, unknown>) {
  const product = productFor(String(row.productId || ''))
  if (!product) return []
  const conversions = Array.isArray(product.uomConversions)
    ? product.uomConversions as Array<Record<string, unknown>>
    : []
  const rows = conversions
    .filter(row => row.uomId)
    .map(row => ({ label: String(row.uomSymbol || row.uomId || ''), value: String(row.uomId) }))
  if (!rows.some(row => row.value === String(product.uomId || ''))) {
    rows.unshift({
      label: String(product.uomSymbol || product.uom || ''),
      value: String(product.uomId || ''),
    })
  }
  return rows
}

/** Cost per the selected UOM from the product Pricing rows. */
function suggestedCost(productId: string, uomId: string): number {
  const product = productFor(productId)
  if (!product) return 0
  const conversion = conversionForUom(product, uomId)
  const suggested = conversion?.costPrice != null
    ? conversion.costPrice
    : multiplyDecimalSafe(Number(product.costPrice || 0), conversion?.factorToBase ?? 1)
  return suggested > 0 ? suggested : 0
}

// Keep rows coherent: valid UOM for the row's product + suggested cost when
// empty (the generic line table cannot derive cross-column defaults itself).
watch(() => model.lines, (rows) => {
  if (!Array.isArray(rows)) return
  const next = (rows as Array<Record<string, unknown>>).map((row) => {
    const product = productFor(String(row.productId || ''))
    if (!product) return row
    const uomId = String(row.uomId || '')
    const validUom = uomId && conversionForUom(product, uomId)
    const nextUomId = validUom ? uomId : String(product.uomId || '')
    const unitAmount = Number(row.unitAmount || 0)
    const nextCost = unitAmount > 0 ? unitAmount : suggestedCost(String(row.productId), nextUomId)
    if (nextUomId === uomId && nextCost === unitAmount) return row
    return { ...row, uomId: nextUomId, unitAmount: nextCost }
  })
  if (JSON.stringify(next) !== JSON.stringify(rows)) model.lines = next
}, { deep: true })

// ---------------------------------------------------------------- schema

const linesTable = computed<ModuleTable>(() => ({
  key: 'lines',
  title: t('app.purchase.lines'),
  addLabelKey: 'app.ui.addRow',
  columns: [
    {
      key: 'productId',
      label: t('app.pos.product'),
      type: 'select',
      required: true,
      optionItems: row => availableProductOptions(row),
    },
    {
      key: 'uomId',
      label: t('app.pos.uom'),
      type: 'select',
      optionItems: row => rowUomOptions(row),
    },
    { key: 'quantity', label: t('app.fields.quantity'), type: 'number', required: true },
    { key: 'unitAmount', label: t('app.purchase.unitCost'), type: 'number' },
    { key: 'amount', label: t('app.fields.lineTotal'), type: 'number', computed: true },
  ],
}))

const tabs = computed<DocumentTabSchema[]>(() => [{
  id: 'general',
  labelKey: 'app.stock.tabGeneral',
  label: t('app.stock.tabGeneral'),
  sections: [
    {
      id: 'purchase',
      titleKey: 'app.purchase.infoSection',
      fields: [
        {
          key: 'supplierId',
          labelKey: 'app.nav.suppliers',
          label: t('app.nav.suppliers'),
          type: 'select',
          options: supplierOptions.value,
          placeholderKey: 'app.purchase.selectSupplier',
          helpKey: 'app.purchase.supplierOptionalHint',
        } satisfies DocumentFieldSchema,
        { key: 'transactionDate', labelKey: 'app.fields.date', type: 'date' },
        {
          key: 'paymentMethod',
          labelKey: 'app.pos.paymentMethod',
          type: 'select',
          options: PAYMENT_METHODS.map(method => ({ label: method, value: method })),
        },
        // Document currency is picked with the USD/KHR toggle on the price
        // fields (lines table + totals); the rate is required for KHR buys.
        ...(model.currency === 'KHR'
          ? [{
              key: 'exchangeRate',
              labelKey: 'app.pos.exchangeRate',
              type: 'number',
              helpKey: 'app.pos.exchangeRateRequired',
            } satisfies DocumentFieldSchema]
          : []),
        { key: 'note', labelKey: 'app.fields.note', type: 'textarea', colSpan: 2 },
      ],
    },
    {
      id: 'products',
      titleKey: 'app.purchase.lines',
      fields: [
        {
          key: 'lines',
          labelKey: 'app.purchase.lines',
          type: 'line-table',
          colSpan: 2,
          meta: {
            table: linesTable.value,
            showPricingTotals: true,
            includeTax: true,
            showPaidRemaining: true,
            // Discount / Tax / Paid now are edited inline in the footer.
            editableTotals: true,
            // USD/KHR toggle beside the table title controls the document currency.
            currencyToggle: true,
          },
        },
      ],
    },
  ],
}])

// ---------------------------------------------------------------- totals

type PurchaseRow = Record<string, unknown> & {
  productId: string
  uomId: string
  quantity: number
  unitAmount: number
}

const lines = computed<PurchaseRow[]>(() =>
  (Array.isArray(model.lines) ? model.lines as PurchaseRow[] : []))

/** Lines ready to save: product + quantity + cost are all set. */
const completedLines = computed(() => lines.value.filter(row =>
  row.productId
  && Number(row.quantity) > 0
  && Number(row.unitAmount) >= 0))

const subtotal = computed(() =>
  round2(completedLines.value.reduce(
    (sum, row) => sum + round2(multiplyDecimalSafe(Number(row.quantity || 0), Number(row.unitAmount || 0))),
    0,
  )))

const discount = computed(() => round2(Math.max(0, Number(model.discount ?? 0))))
const tax = computed(() => round2(Math.max(0, Number(model.tax ?? 0))))
const total = computed(() => round2(Math.max(0, subtotal.value - discount.value + tax.value)))
const paidNow = computed(() => round2(Math.min(Math.max(0, Number(model.paidNow ?? 0)), total.value)))
const remaining = computed(() => round2(Math.max(0, total.value - paidNow.value)))

const canSave = computed(() =>
  completedLines.value.length > 0
  && (remaining.value <= 0 || Boolean(model.supplierId))
  && (model.currency !== 'KHR' || Number(model.exchangeRate || 0) > 0))

// ---------------------------------------------------------------- submit

const saving = ref(false)

async function save() {
  if (!canSave.value || saving.value) return
  saving.value = true
  try {
    await posCommands.createPurchase({
      lines: completedLines.value.map((row) => {
        const product = productFor(row.productId)
        const conversion = conversionForUom(product, String(row.uomId || ''))
        return {
          productId: row.productId,
          quantity: Number(row.quantity),
          unitCost: Number(row.unitAmount),
          uomId: String(row.uomId || product?.uomId || '') || undefined,
          uomSymbol: String(conversion?.uomSymbol || product?.uomSymbol || product?.uom || '') || undefined,
          factorToBase: conversion?.factorToBase ?? 1,
        }
      }),
      supplierId: String(model.supplierId || '') || null,
      paidAmount: paidNow.value,
      paymentMethod: String(model.paymentMethod || 'Cash'),
      discountAmount: discount.value,
      taxAmount: tax.value,
      currency: String(model.currency || 'USD') as 'USD' | 'KHR',
      exchangeRate: Number(model.exchangeRate || 1),
      note: String(model.note || '').trim() || null,
    })
    toast.add({ title: t('app.purchase.created'), color: 'success' })
    await navigateTo('/reports/purchases')
  }
  catch (error: unknown) {
    toast.add({
      title: t('app.purchase.saveFailed'),
      description: error instanceof Error ? error.message : String(error),
      color: 'error',
    })
  }
  finally {
    saving.value = false
  }
}
</script>

<template>
  <DocumentAppDocumentPage
    :tabs="tabs"
    active-tab="general"
    :field-value="fieldValue"
    :set-field-value="setFieldValue"
    :saving="saving"
    :can-save="canSave"
    :is-create="true"
    :show-tabs="false"
    content-wide
    :show-cancel="true"
    list-to="/reports/purchases"
    :can-export="false"
    @save="save()"
  />
</template>
