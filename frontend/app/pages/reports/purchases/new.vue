<script setup lang="ts">
import { PAYMENT_METHODS } from '~/config/pos-options'
import type { ModuleTable } from '~/config/modules'
import type { AppRecord } from '~/config/admin-seed'
import { useAppHeader } from '~/composables/layout/useAppHeader'
import { usePosCommands, useStockQueries } from '~/repositories/index'
import type { ProductBatchRow } from '~/repositories/contracts/entities'
import type {
  DocumentFieldSchema,
  DocumentTabSchema,
} from '~/types/stock-pos/common'
import { conversionForUom, multiplyDecimalSafe } from '~/utils/stock/uom-conversions'
import { checkoutPaidNow } from '~/utils/pos/checkout'
import { buildPurchaseEditLines, buildPurchaseReturnLines } from '~/utils/reports/returns'
import { apiErrorMessage, isApiErrorHandled } from '~/utils/api/errors'

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
 * Entry points: Purchase Report Create action, and the Stock Products row
 * action "Purchase Stock" (routes here with ?productId= preselected).
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
  // Return mode read-only header + reason.
  purchaseNo: '',
  supplierName: '',
  returnReason: '',
  lines: [] as Array<Record<string, unknown>>,
})

/* ------------------------------ return mode ------------------------------ */
/** Purchase Return mode: the original purchase is preloaded and Submit records
 *  an immutable Purchase Return (never a new purchase, never an edit). */
const returnMode = ref(false)
const returnPurchaseId = ref('')
const returnLoading = ref(false)
const returnReason = ref('')

/* ------------------------------- edit mode ------------------------------- */
/** Purchase Edit mode: the original Stock In is preloaded and Submit re-saves
 *  it via PATCH (reverse + reapply on the backend). */
const editMode = ref(false)
const editPurchaseId = ref('')

/** View-only: Purchase Report Purchase No → detail form, no edits. */
const viewMode = ref(false)

function fieldValue(key: string): unknown {
  // Computed document totals consumed by the line-table footer.
  if (key === 'subtotal') return subtotal.value
  if (key === 'total') return total.value
  if (key === 'paidNow') return paidNow.value
  if (key === 'remaining') return remaining.value
  if (key === 'returnReason') return returnReason.value
  return model[key]
}

function setFieldValue(key: string, value: unknown): void {
  if (viewMode.value) return
  if (key === 'returnReason') {
    returnReason.value = String(value ?? '')
    return
  }
  model[key] = value
}

// ---------------------------------------------------------------- masters

onMounted(async () => {
  const returnId = String(route.query.returnPurchaseId || '')
  if (returnId) {
    await loadReturnPurchase(returnId, String(route.query.purchaseNo || ''))
    return
  }
  const viewId = String(route.query.viewPurchaseId || '')
  if (viewId) {
    await loadViewPurchase(viewId, String(route.query.purchaseNo || ''))
    return
  }
  const editId = String(route.query.editPurchaseId || '')
  if (editId) {
    await loadEditPurchase(editId, String(route.query.purchaseNo || ''))
    return
  }
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
    applyDefaultSupplier(productFor(preselect))
  }
})

/** Load an original purchase into the form as a return: preload supplier,
 *  lines, batch/expiry, UOM and unit cost; Submit records a Purchase Return. */
async function loadReturnPurchase(purchaseId: string, purchaseNo: string) {
  returnLoading.value = true
  try {
    await Promise.all([store.fetchList('products'), store.fetchList('suppliers')])
    await store.fetchList('stockIns', { q: purchaseNo || undefined, limit: 500 })
    const docs = store.list('stockIns') as AppRecord[]
    const doc = docs.find(row => String(row.id) === purchaseId)
    if (!doc) {
      toast.add({ title: t('app.purchase.returnLoadFailed'), color: 'error' })
      await navigateTo('/reports/purchases')
      return
    }
    model.supplierId = String(doc.supplierId || '')
    model.supplierName = String(doc.supplier || '')
    model.purchaseNo = String(doc.purchaseNo || purchaseNo || '')
    model.currency = String(doc.currency || 'USD') === 'KHR' ? 'KHR' : 'USD'
    model.exchangeRate = Number(doc.exchangeRate || 1)
    model.transactionDate = String(doc.date || '').slice(0, 10)
    const productById = new Map(store.list('products').map(row => [String(row.id), row]))
    const returnLines = buildPurchaseReturnLines(doc, productById)
    if (!returnLines.length) {
      toast.add({ title: t('app.reports.nothingToReturn'), color: 'warning' })
      await navigateTo('/reports/purchases')
      return
    }
    model.lines = returnLines
    returnMode.value = true
    returnPurchaseId.value = purchaseId
    returnReason.value = ''
    setTitle(t('app.purchase.returnMode'))
  }
  catch (error: unknown) {
    if (!isApiErrorHandled(error)) {
      toast.add({
        title: t('app.purchase.returnLoadFailed'),
        description: apiErrorMessage(error, t('app.purchase.returnLoadFailed')),
        color: 'error',
      })
    }
  }
  finally {
    returnLoading.value = false
  }
}

/** Load an original purchase into the form for editing (all lines, original
 *  quantities/costs); Submit re-saves via PATCH (reverse + reapply). */
async function loadEditPurchase(purchaseId: string, purchaseNo: string) {
  returnLoading.value = true
  try {
    await Promise.all([store.fetchList('products'), store.fetchList('suppliers')])
    await store.fetchList('stockIns', { q: purchaseNo || undefined, limit: 500 })
    const docs = store.list('stockIns') as AppRecord[]
    const doc = docs.find(row => String(row.id) === purchaseId)
    if (!doc) {
      toast.add({ title: t('app.purchase.updateLoadFailed'), color: 'error' })
      await navigateTo('/reports/purchases')
      return
    }
    model.supplierId = String(doc.supplierId || '')
    model.supplierName = String(doc.supplier || '')
    model.purchaseNo = String(doc.purchaseNo || purchaseNo || '')
    model.currency = String(doc.currency || 'USD') === 'KHR' ? 'KHR' : 'USD'
    model.exchangeRate = Number(doc.exchangeRate || 1)
    model.transactionDate = String(doc.date || '').slice(0, 10)
    model.note = String(doc.note || '')
    model.discount = Number(doc.discount ?? doc.discountAmount ?? 0) || undefined
    model.tax = Number(doc.tax ?? doc.taxAmount ?? 0) || undefined
    model.paymentMethod = String(doc.paymentMethodLabel || doc.paymentMethod || 'Cash') || 'Cash'
    model.paidNow = Number(doc.paidAmount ?? 0)
    const productById = new Map(store.list('products').map(row => [String(row.id), row]))
    const editLines = buildPurchaseEditLines(doc, productById)
    if (!editLines.length) {
      toast.add({ title: t('app.purchase.updateLoadFailed'), color: 'warning' })
      await navigateTo('/reports/purchases')
      return
    }
    model.lines = editLines
    editMode.value = true
    editPurchaseId.value = purchaseId
    setTitle(t('app.purchase.editTitle'))
  }
  catch (error: unknown) {
    if (!isApiErrorHandled(error)) {
      toast.add({
        title: t('app.purchase.updateLoadFailed'),
        description: apiErrorMessage(error, t('app.purchase.updateLoadFailed')),
        color: 'error',
      })
    }
  }
  finally {
    returnLoading.value = false
  }
}

/** Load a purchase for view-only detail (Purchase Report Purchase No). */
async function loadViewPurchase(purchaseId: string, purchaseNo: string) {
  await loadEditPurchase(purchaseId, purchaseNo)
  if (!editMode.value) return
  editMode.value = false
  viewMode.value = true
  setTitle(t('app.purchase.viewTitle'))
}

function blankLine(): Record<string, unknown> {
  return { productId: '', uomId: '', quantity: 0, unitAmount: 0, amount: 0, batchNo: '', expiryDate: '' }
}

// ------------------------------------------------------- batch picking

/** Sentinel option in the Batch picker: generates the next batch no (latest
 *  batch + 1, preserving prefix and zero padding). The lot itself is only
 *  created when the purchase is submitted. */
const NEW_BATCH = '__new__'

const stockQueries = useStockQueries()
/** Existing batch lots per product (batch cache; [] while loading). */
const batchCache = ref(new Map<string, ProductBatchRow[]>())

async function ensureBatches(productId: string): Promise<ProductBatchRow[]> {
  const cached = batchCache.value.get(productId)
  if (cached) return cached
  batchCache.value.set(productId, [])
  try {
    const result = await stockQueries.listProductBatches(productId)
    batchCache.value.set(productId, result.items)
    return result.items
  }
  catch {
    return []
  }
}

/** Latest usable lot of the product (newest receipt that is not expired).
 *  This is the Batch No. default after selecting a product. */
function latestBatch(batches: ProductBatchRow[]): ProductBatchRow | null {
  const usable = batches.filter(batch => batch.batchNo && batch.status !== 'Expired')
  if (!usable.length) return null
  return [...usable].sort((a, b) => b.createdDate.localeCompare(a.createdDate))[0] ?? null
}

/** Next batch number: latest batch + 1 — increment the numeric suffix,
 *  preserving the prefix and zero padding (BATCH-001 → BATCH-002), skipping
 *  numbers already taken. No previous batch → BATCH-001. */
function generateBatchNo(batches: ProductBatchRow[]): string {
  const taken = new Set(batches.map(batch => batch.batchNo).filter(Boolean))
  const latest = [...batches]
    .filter(batch => batch.batchNo)
    .sort((a, b) => b.createdDate.localeCompare(a.createdDate))[0]?.batchNo
  if (!latest) return 'BATCH-001'
  const match = latest.match(/^(.*?)(\d+)$/)
  if (!match) return `${latest}-1`
  const prefix = match[1]!
  const width = match[2]!.length
  let candidate = latest
  let seq = Number(match[2])
  do {
    seq += 1
    candidate = `${prefix}${String(seq).padStart(width, '0')}`
  } while (taken.has(candidate))
  return candidate
}

/** Batch picker options of a row: the product's existing lots (stocking into
 *  one preserves its identity/history), the row's generated new batch no
 *  while it is selected, and the "+ New Batch" option. */
function batchOptionsFor(row: Record<string, unknown>): Array<{ label: string, value: string }> {
  const productId = String(row.productId || '')
  const product = productFor(productId)
  if (!product || !tracksBatch(product)) return []
  const items = (batchCache.value.get(productId) || [])
    .filter(batch => batch.batchNo)
    .map(batch => ({ label: batch.batchNo, value: batch.batchNo }))
  const picked = String(row.batchNo || '')
  if (picked && picked !== NEW_BATCH && !items.some(item => item.value === picked)) {
    items.push({ label: picked, value: picked })
  }
  items.push({ label: t('app.purchase.newBatch'), value: NEW_BATCH })
  return items
}

/** Find the live line to mutate after an async batch fetch (row objects are
 *  replaced on each deep-watch pass, so identity alone is not enough). */
function liveLineForBatch(row: Record<string, unknown>, productId: string) {
  const lines = Array.isArray(model.lines) ? model.lines as Array<Record<string, unknown>> : []
  if (lines.includes(row) && String(row.productId || '') === productId) return row
  return lines.find(line =>
    String(line.productId || '') === productId
    && (!String(line.batchNo || '').trim() || String(line.batchNo) === NEW_BATCH))
    || null
}

/** After selecting a product: default the Batch No. to its latest lot
 *  (+ expiry). When the product has no lots yet, invent the next batch no
 *  (BATCH-001…) so Submit is not stuck waiting for a manual batch pick. */
async function autofillLatestBatch(row: Record<string, unknown>, productId: string) {
  const batches = await ensureBatches(productId)
  const live = liveLineForBatch(row, productId)
  if (!live) return
  if (String(live.batchNo || '').trim() && String(live.batchNo) !== NEW_BATCH) return
  const product = productFor(productId)
  if (!product || !tracksBatch(product)) return
  const latest = latestBatch(batches)
  if (latest) {
    live.batchNo = latest.batchNo
    if (latest.expiryDate) live.expiryDate = latest.expiryDate
    return
  }
  live.batchNo = generateBatchNo(batches)
}

/** "+ New Batch" picked: resolve the generated number once the product's
 *  batches are loaded, then show it as the row's selected batch. */
async function applyNewBatch(row: Record<string, unknown>, productId: string) {
  const batches = await ensureBatches(productId)
  const live = liveLineForBatch(row, productId)
  if (!live) return
  if (String(live.batchNo || '') !== NEW_BATCH) return
  live.batchNo = generateBatchNo(batches)
}

const supplierOptions = computed(() => store.list('suppliers').map(row => ({
  label: String(row.name || ''),
  value: String(row.id),
})))

function productFor(productId: string) {
  return store.list('products').find(row => String(row.id) === productId) || null
}

/** Default supplier fast-path: the selected product's own supplier prefills
 *  the purchase header. A manual supplier choice is never overwritten. */
const autoSupplierId = ref('')

function applyDefaultSupplier(product: Record<string, unknown> | null) {
  const productSupplier = String(product?.supplierId || '')
  if (!productSupplier) return
  const current = String(model.supplierId || '')
  if (current && current !== autoSupplierId.value) return
  model.supplierId = productSupplier
  autoSupplierId.value = productSupplier
}

/** Products not already on ANOTHER line (one line per product; the backend
 *  rejects duplicates on the same stock-in document). The picker shows the
 *  product NAME only and searches it (barcode stays out of the dropdown).
 *  The row's own product stays in the list so its name still resolves — the
 *  table passes a copy of the row, so identity checks would drop it. */
function availableProductOptions(row: Record<string, unknown>) {
  const currentId = String(row.productId || '')
  const lines = Array.isArray(model.lines) ? model.lines as Array<Record<string, unknown>> : []
  const usedByOthers = new Set(lines
    .map(other => String(other.productId || ''))
    .filter(id => id && id !== currentId))
  return store.list('products')
    .filter(product => !usedByOthers.has(String(product.id)))
    .map(product => ({ label: String(product.name || ''), value: String(product.id) }))
}

/** Batch tracking is per product toggle (spec §5.9 Stock Costing). */
function tracksBatch(product: Record<string, unknown> | null): boolean {
  if (!product) return false
  return product.trackBatch === true
    || (product.trackBatch == null && (product.expiryTracking === true || product.expiryTracking === 'true'))
}

function tracksExpiry(product: Record<string, unknown> | null): boolean {
  if (!product) return false
  return product.trackExpiry === true || product.expiryTracking === true
    || (product.trackExpiry == null && product.expiryTracking === true)
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

// Keep rows coherent: the row's UOM follows the product's default UOM (no
// visible UOM column, but the conversion still feeds stock-in math) +
// suggested cost when empty + batch/expiry clearing for unbatched products
// (the generic line table cannot derive cross-column defaults itself).
watch(() => model.lines, (rows) => {
  if (viewMode.value || returnMode.value) return
  if (!Array.isArray(rows)) return
  const next = (rows as Array<Record<string, unknown>>).map((row) => {
    const product = productFor(String(row.productId || ''))
    if (!product) return row
    // Internal UOM: the product's default/base UOM (hidden column, conversion
    // logic preserved — ledger math happens server-side from factorToBase).
    const nextUomId = String(product.uomId || '')
    const unitAmount = Number(row.unitAmount || 0)
    const nextCost = unitAmount > 0 ? unitAmount : suggestedCost(String(row.productId), nextUomId)
    const nextRow: Record<string, unknown> = { ...row, uomId: nextUomId, unitAmount: nextCost, name: String(product.name || '') }
    // Base qty display: entered qty × factor (display only — ledger math
    // happens server-side from factorToBase).
    nextRow.baseQuantity = multiplyDecimalSafe(Number(row.quantity || 0), conversionForUom(product, nextUomId)?.factorToBase ?? 1)
    // Batch/expiry columns only when the product tracks them.
    if (!tracksBatch(product)) {
      nextRow.batchNo = ''
    }
    if (!tracksExpiry(product)) nextRow.expiryDate = ''

    // Prefill supplier from the product when the header is still empty / auto.
    applyDefaultSupplier(product)

    const picked = String(nextRow.batchNo || '')
    if (tracksBatch(product) && !picked.trim()) {
      // Deep watch cannot reliably detect productId changes (same-array
      // mutation). Autofill whenever a batch-tracked line has no batch yet.
      void autofillLatestBatch(nextRow, String(nextRow.productId || ''))
    }
    else if (picked === NEW_BATCH) {
      void applyNewBatch(nextRow, String(nextRow.productId || ''))
    }
    else if (picked && picked !== NEW_BATCH) {
      const batches = batchCache.value.get(String(nextRow.productId || '')) || []
      const lot = batches.find(batch => batch.batchNo === picked)
      if (lot) {
        const lotExpiry = String(lot.expiryDate || '').trim()
        const rowExpiry = String(nextRow.expiryDate || '').trim()
        if (tracksExpiry(product) && !rowExpiry && lotExpiry) {
          // Restocking the selected lot: adopt its recorded expiry.
          nextRow.expiryDate = lotExpiry
        }
        else if (tracksExpiry(product) && rowExpiry && rowExpiry !== lotExpiry) {
          // Same batch no with a different expiry is a new lot: auto-assign the
          // next batch number (BATCH-001 → BATCH-002 → …).
          nextRow.batchNo = generateBatchNo(batches)
        }
      }
    }
    if (JSON.stringify(nextRow) !== JSON.stringify(row)) return nextRow
    return row
  })
  if (JSON.stringify(next) !== JSON.stringify(rows)) model.lines = next
}, { deep: true })

// ---------------------------------------------------------------- schema

const linesTable = computed<ModuleTable>(() => {
  // Return / view: lines are fixed (read-only).
  if (returnMode.value || viewMode.value) {
    return {
      key: 'lines',
      title: t('app.purchase.lines'),
      fitWidth: true,
      columns: [
        { key: 'name', label: t('app.pos.product'), type: 'text', computed: true, width: 'min-w-40' },
        { key: 'batchNo', label: t('app.stock.batchNo'), type: 'text', computed: true, width: 'w-40 min-w-32' },
        { key: 'expiryDate', label: t('app.stock.expiryDateCol'), type: 'date', computed: true, width: 'w-32' },
        { key: 'unitAmount', label: t('app.purchase.unitCost'), type: 'number', computed: true },
        {
          key: 'quantity',
          label: returnMode.value ? t('app.reports.returnQty') : t('app.fields.quantity'),
          type: 'number',
          computed: viewMode.value,
          required: returnMode.value,
          // Return is capped at what is still in stock (returnableQuantity is
          // already min(received−returned, available)).
          max: returnMode.value ? (row => Number(row.returnableQuantity || 0)) : undefined,
          width: 'w-28 min-w-24',
        },
        { key: 'amount', label: t('app.fields.lineTotal'), type: 'number', computed: true },
      ],
    }
  }
  return {
    key: 'lines',
    title: t('app.purchase.lines'),
  addLabelKey: 'app.ui.addRow',
  // Stretch to the page width (no horizontal scroll on desktop); the Product
  // column flex-fills the remainder. Narrow screens scroll via the wrapper.
  fitWidth: true,
  columns: [
    {
      key: 'productId',
      label: t('app.pos.product'),
      type: 'select',
      required: true,
      // Searchable by product name; flex-fill = widest column.
      searchable: true,
      width: 'min-w-40',
      optionItems: row => availableProductOptions(row),
    },
    {
      key: 'batchNo',
      label: t('app.stock.batchNo'),
      type: 'select',
      // Select-only: existing lots + "+ New Batch" (auto-generated number).
      searchable: true,
      width: 'w-44 min-w-36',
      optionItems: row => batchOptionsFor(row),
    },
    { key: 'expiryDate', label: t('app.stock.expiryDateCol'), type: 'date', width: 'w-32' },
    { key: 'quantity', label: t('app.fields.quantity'), type: 'number', required: true },
    { key: 'unitAmount', label: t('app.purchase.unitCost'), type: 'number' },
    { key: 'amount', label: t('app.fields.lineTotal'), type: 'number', computed: true },
  ],
  }
})

const tabs = computed<DocumentTabSchema[]>(() => {
  if (returnMode.value) {
    return [
      {
        id: 'general',
        labelKey: 'app.stock.tabGeneral',
        label: t('app.stock.tabGeneral'),
        sections: [
          {
            id: 'purchase-return',
            titleKey: 'app.purchase.returnMode',
            fields: [
              { key: 'purchaseNo', labelKey: 'app.reports.purchaseNo', type: 'text', readOnly: true },
              { key: 'supplierName', labelKey: 'app.nav.suppliers', type: 'text', readOnly: true },
              { key: 'transactionDate', labelKey: 'app.fields.date', type: 'date', readOnly: true },
              { key: 'currency', labelKey: 'app.fields.currency', type: 'text', readOnly: true },
            ],
          },
          {
            id: 'return-reason',
            fields: [
              { key: 'returnReason', labelKey: 'app.reports.returnReason', type: 'textarea', required: true, colSpan: 2 },
            ],
          },
        ],
      },
      {
        id: 'products',
        labelKey: 'app.purchase.lines',
        sections: [
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
                  // Fixed original lines: no add / remove, no payment footer.
                  hideAdd: true,
                  hideRowActions: true,
                },
              },
            ],
          },
        ],
      },
    ]
  }
  if (viewMode.value) {
    return [{
      id: 'general',
      labelKey: 'app.stock.tabGeneral',
      label: t('app.stock.tabGeneral'),
      sections: [
        {
          id: 'purchase',
          titleKey: 'app.purchase.infoSection',
          fields: [
            { key: 'purchaseNo', labelKey: 'app.reports.purchaseNo', type: 'text', readOnly: true },
            { key: 'supplierName', labelKey: 'app.nav.suppliers', type: 'text', readOnly: true },
            { key: 'transactionDate', labelKey: 'app.fields.date', type: 'date', readOnly: true },
            { key: 'paymentMethod', labelKey: 'app.pos.paymentMethod', type: 'text', readOnly: true },
            { key: 'currency', labelKey: 'app.fields.currency', type: 'text', readOnly: true },
            { key: 'note', labelKey: 'app.fields.note', type: 'textarea', colSpan: 2, readOnly: true },
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
                hideAdd: true,
                hideRowActions: true,
                viewOnly: true,
              },
            },
          ],
        },
      ],
    }]
  }
  return [{
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
  }]
})

// ---------------------------------------------------------------- totals

type PurchaseRow = Record<string, unknown> & {
  productId: string
  uomId: string
  quantity: number
  unitAmount: number
  batchNo?: string
  expiryDate?: string
}

const lines = computed<PurchaseRow[]>(() =>
  (Array.isArray(model.lines) ? model.lines as PurchaseRow[] : []))

/** Lines ready to save: product + quantity + cost are all set, and the
 *  batch/expiry requirements of the row's product are satisfied. A row still
 *  on the "+ New Batch" sentinel (generation in flight) is not ready yet. */
const completedLines = computed(() => lines.value.filter((row) => {
  if (!row.productId) return false
  if (!(Number(row.quantity) > 0)) return false
  if (Number(row.unitAmount) < 0) return false
  const product = productFor(row.productId)
  // Spec: batch no required when the product tracks batches; expiry date
  // required when it tracks expiry (expiry implies batch).
  if (tracksBatch(product) && (!String(row.batchNo ?? '').trim() || String(row.batchNo) === NEW_BATCH)) return false
  if (tracksExpiry(product) && !String(row.expiryDate ?? '').trim()) return false
  return true
}))

/** Lines with a product, quantity and cost — the running purchase total. The
 *  stricter `completedLines` (below) additionally enforces batch/expiry, so an
 *  incomplete line still shows its amount in the summary instead of $0.00. */
const pricedLines = computed(() => lines.value.filter((row) => {
  if (!row.productId) return false
  if (!(Number(row.quantity) > 0)) return false
  return Number(row.unitAmount) >= 0
}))

const subtotal = computed(() =>
  round2(pricedLines.value.reduce(
    (sum, row) => sum + round2(multiplyDecimalSafe(Number(row.quantity || 0), Number(row.unitAmount || 0))),
    0,
  )))

const discount = computed(() => round2(Math.max(0, Number(model.discount ?? 0))))
const tax = computed(() => round2(Math.max(0, Number(model.tax ?? 0))))
const total = computed(() => round2(Math.max(0, subtotal.value - discount.value + tax.value)))
/** Untouched Paid now = pay in full (same as POS cash). Credit pays nothing. */
const paidNow = computed(() => checkoutPaidNow(
  model.paidNow as number | undefined,
  total.value,
  String(model.paymentMethod || '') === 'Credit',
))
const remaining = computed(() => round2(Math.max(0, total.value - paidNow.value)))

const canSave = computed(() =>
  returnMode.value
    ? (completedLines.value.length > 0 && Boolean(returnReason.value.trim()))
    : (completedLines.value.length > 0
      && (remaining.value <= 0 || Boolean(model.supplierId))
      && (model.currency !== 'KHR' || Number(model.exchangeRate || 0) > 0)))

/** Human reason Submit stays blocked — shown as a toast when the user clicks. */
function saveBlockedReason(): string | null {
  if (returnMode.value) {
    if (!completedLines.value.length) return t('app.purchase.needLines')
    if (!returnReason.value.trim()) return t('app.purchase.needReturnReason')
    return null
  }
  if (!pricedLines.value.length) return t('app.purchase.needLines')
  if (!completedLines.value.length) {
    const incomplete = lines.value.find((row) => {
      if (!row.productId || !(Number(row.quantity) > 0)) return false
      const product = productFor(row.productId)
      if (tracksBatch(product) && (!String(row.batchNo ?? '').trim() || String(row.batchNo) === NEW_BATCH)) return true
      if (tracksExpiry(product) && !String(row.expiryDate ?? '').trim()) return true
      return false
    })
    if (incomplete) {
      const product = productFor(incomplete.productId)
      if (tracksExpiry(product) && !String(incomplete.expiryDate ?? '').trim()) {
        return t('app.purchase.needExpiry')
      }
      return t('app.purchase.needBatch')
    }
    return t('app.purchase.needLines')
  }
  if (remaining.value > 0 && !model.supplierId) return t('app.purchase.needSupplier')
  if (model.currency === 'KHR' && !(Number(model.exchangeRate || 0) > 0)) {
    return t('app.purchase.needExchangeRate')
  }
  return null
}

/** Header CTA: Submit for new purchases, Save changes for edits, Confirm for returns. */
const purchaseSaveLabel = computed(() => {
  if (returnMode.value) return t('app.reports.confirmReturn')
  if (editMode.value) return t('core.common.save')
  return t('core.confirm.submit')
})

// ---------------------------------------------------------------- submit

const saving = ref(false)

/** Resolve any leftover "+ New Batch" sentinels before posting. */
async function resolvePendingBatches() {
  const rows = Array.isArray(model.lines) ? model.lines as Array<Record<string, unknown>> : []
  for (const row of rows) {
    const productId = String(row.productId || '')
    if (!productId) continue
    if (String(row.batchNo || '') === NEW_BATCH) {
      await applyNewBatch(row, productId)
    }
    else if (tracksBatch(productFor(productId)) && !String(row.batchNo || '').trim()) {
      await autofillLatestBatch(row, productId)
    }
  }
}

async function saveReturn() {
  if (!canSave.value || saving.value) return
  saving.value = true
  try {
    await posCommands.returnPurchase({
      stockInId: returnPurchaseId.value,
      reason: returnReason.value.trim(),
      lines: completedLines.value.map(row => ({
        lineId: String((row as { lineId?: string }).lineId || ''),
        quantity: Number(row.quantity),
      })),
    })
    toast.add({ title: t('app.reports.returnSaved'), color: 'success' })
    void store.fetchList('products')
    void store.fetchList('stockIns')
    await navigateTo('/reports/purchases')
  }
  catch (error: unknown) {
    if (!isApiErrorHandled(error)) {
      toast.add({
        title: t('app.reports.returnFailed'),
        description: apiErrorMessage(error, t('app.reports.returnFailed')),
        color: 'error',
      })
    }
  }
  finally {
    saving.value = false
  }
}

/** Save the edited purchase (reverse + reapply on the backend). */
async function saveEdit() {
  if (!canSave.value || saving.value) return
  saving.value = true
  try {
    await resolvePendingBatches()
    await posCommands.updatePurchase({
      stockInId: editPurchaseId.value,
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
          batchNo: String(row.batchNo || '').trim() || null,
          expiryDate: String(row.expiryDate || '').trim() || null,
        }
      }),
      discountAmount: discount.value,
      taxAmount: tax.value,
      currency: String(model.currency || 'USD') as 'USD' | 'KHR',
      exchangeRate: Number(model.exchangeRate || 1),
      note: String(model.note || '').trim() || null,
      transactionDate: String(model.transactionDate || '').trim() || null,
    })
    toast.add({ title: t('app.purchase.updated'), color: 'success' })
    void store.fetchList('products')
    void store.fetchList('stockIns')
    await navigateTo('/reports/purchases')
  }
  catch (error: unknown) {
    if (!isApiErrorHandled(error)) {
      toast.add({
        title: t('app.purchase.updateFailed'),
        description: apiErrorMessage(error, t('app.purchase.updateFailed')),
        color: 'error',
      })
    }
  }
  finally {
    saving.value = false
  }
}

async function save() {
  if (saving.value) return
  await resolvePendingBatches()
  const blocked = saveBlockedReason()
  if (blocked) {
    toast.add({ title: blocked, color: 'warning' })
    return
  }
  if (returnMode.value) {
    await saveReturn()
    return
  }
  if (editMode.value) {
    await saveEdit()
    return
  }
  if (!canSave.value) return
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
          batchNo: String(row.batchNo || '').trim() || null,
          expiryDate: String(row.expiryDate || '').trim() || null,
        }
      }),
      supplierId: String(model.supplierId || '') || null,
      paidAmount: paidNow.value,
      paymentMethod: String(model.paymentMethod || 'Cash'),
      discountAmount: discount.value,
      taxAmount: tax.value,
      currency: String(model.currency || 'USD') as 'USD' | 'KHR',
      exchangeRate: Number(model.exchangeRate || 1),
      transactionDate: String(model.transactionDate || '').trim() || null,
      note: String(model.note || '').trim() || null,
    })
    toast.add({ title: t('app.purchase.created'), color: 'success' })
    void store.fetchList('products')
    void store.fetchList('stockIns')
    await navigateTo('/reports/purchases')
  }
  catch (error: unknown) {
    if (!isApiErrorHandled(error)) {
      toast.add({
        title: t('app.purchase.saveFailed'),
        description: apiErrorMessage(error, t('app.purchase.saveFailed')),
        color: 'error',
      })
    }
  }
  finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="flex h-full min-h-0 flex-1 flex-col overflow-hidden">
    <div
      v-if="returnMode"
      class="flex items-center gap-2 border-b border-warning/40 bg-warning/10 px-3 py-1.5 text-sm font-medium text-warning"
    >
      <UIcon name="i-lucide-undo-2" class="size-4" />
      <span>{{ t('app.purchase.returnMode') }}</span>
      <span v-if="model.purchaseNo" class="text-muted">· {{ model.purchaseNo }}</span>
    </div>
    <div
      v-if="viewMode"
      class="flex items-center gap-2 border-b border-info/40 bg-info/10 px-3 py-1.5 text-sm font-medium text-info"
    >
      <UIcon name="i-lucide-eye" class="size-4" />
      <span>{{ t('app.purchase.viewMode') }}</span>
      <span v-if="model.purchaseNo" class="text-muted">· {{ model.purchaseNo }}</span>
    </div>
    <div
      v-if="editMode"
      class="flex items-center gap-2 border-b border-primary/40 bg-primary/10 px-3 py-1.5 text-sm font-medium text-primary"
    >
      <UIcon name="i-lucide-pencil" class="size-4" />
      <span>{{ t('app.purchase.editMode') }}</span>
      <span v-if="model.purchaseNo" class="text-muted">· {{ model.purchaseNo }}</span>
    </div>
    <DocumentAppDocumentPage
      :tabs="tabs"
      active-tab="general"
      :field-value="fieldValue"
      :set-field-value="setFieldValue"
      :pending="returnLoading"
      :saving="saving"
      :can-save="!viewMode"
      :confirm-save="canSave"
      :save-label="purchaseSaveLabel"
      :read-only="viewMode"
      :is-create="!editMode && !returnMode && !viewMode"
      :show-tabs="false"
      content-wide
      :show-cancel="true"
      list-to="/reports/purchases"
      :can-export="false"
      @save="save()"
    />
  </div>
</template>
