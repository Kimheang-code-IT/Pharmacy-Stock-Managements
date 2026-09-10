<script setup lang="ts">
import type { AppRecord } from '~/config/admin-seed'
import type { ModuleTable } from '~/config/modules'
import type { DocumentTabSchema } from '~/types/stock-pos/common'
import { useDeliveryCommands } from '~/repositories/index'
import {
  normalizeDeliverableInvoice,
  type DeliverableInvoice,
  type DeliverableInvoiceItem,
} from '~/utils/delivery/notes'
import { printDeliveryNoteDocument } from '~/utils/print/delivery-note'

/**
 * Reusable delivery-note create flow (spec §2.1.9 / §5.13) — built on the
 * same reusable document components as the purchase page:
 * DocumentAppDocumentPage + schema-driven AppDocumentForm sections +
 * the generic TableAppLineTable. Layout mirrors Purchase:
 *
 * - "Delivery Information" header section: phone (required), location
 *   (required), note.
 * - "Lines to deliver" line table: each row adds one invoice line —
 *   pick the Invoice (deliverable confirmed invoices, live options), then
 *   the Product line of that invoice; UOM / Ordered / Remaining are
 *   snapshots and Qty to deliver is editable (bounded by Remaining).
 *   Multiple invoices of the SAME customer can be added as rows.
 *
 * POS auto-entry passes `autoSelectSaleId` (invoice that just completed,
 * all its lines prefilled) plus `initialPhone` / `initialLocation` from the
 * checkout snapshot. No driver/vehicle/schedule form; no stock mutation
 * (stock-out already happened at POS).
 */
const props = withDefaults(defineProps<{
  /** POS auto-entry: sale id whose lines are prefilled after invoices load. */
  autoSelectSaleId?: string
  /** Prefilled destination phone (POS checkout snapshot). */
  initialPhone?: string
  /** Prefilled destination location (POS checkout snapshot). */
  initialLocation?: string
  /** Show Save & Confirm (delivery.confirm permission). */
  canConfirm?: boolean
  /** Auto-print the bilingual note after creation. */
  printOnCreate?: boolean
  shopName?: string
}>(), {
  canConfirm: true,
  printOnCreate: true,
  shopName: 'Yoeun Sokhon Pharmacy',
})

const emit = defineEmits<{
  /** Created record (deliveryNo included) after a successful save. */
  created: [record: AppRecord]
}>()

const deliveryCommands = useDeliveryCommands()
const { t } = useI18n()
const toast = useToast()

type DeliveryRow = Record<string, unknown> & {
  saleId: string
  saleItemId: string
  product: string
  uomSymbol: string
  qtyOrdered: number
  qtyRemaining: number
  qtyToDeliver: number
}

const model = reactive<Record<string, unknown>>({
  deliveryPhone: '',
  deliveryLocation: '',
  note: '',
  lines: [] as Array<Record<string, unknown>>,
})

function fieldValue(key: string): unknown {
  return model[key]
}

function setFieldValue(key: string, value: unknown): void {
  model[key] = value
}

const invoices = ref<DeliverableInvoice[]>([])
const loading = ref(false)
const saving = ref(false)

onMounted(async () => {
  if (props.initialPhone) model.deliveryPhone = props.initialPhone
  if (props.initialLocation) model.deliveryLocation = props.initialLocation
  loading.value = true
  try {
    const rows = await deliveryCommands.deliverableInvoices(null)
    invoices.value = rows
      .map(row => normalizeDeliverableInvoice(row as Record<string, unknown>))
      .filter(row => row.items.length > 0)
    const preselect = String(props.autoSelectSaleId || '')
    if (preselect) {
      const invoice = invoiceById.value.get(preselect)
      if (invoice) model.lines = invoice.items.map(item => rowOf(preselect, item))
      else toast.add({ title: t('app.delivery.noDeliverableSales'), color: 'warning' })
    }
  }
  finally {
    loading.value = false
  }
})

const invoiceById = computed(() =>
  new Map(invoices.value.map(invoice => [invoice.saleId, invoice])))

function invoiceOptionsFor(): Array<{ label: string, value: string }> {
  return invoices.value.map(invoice => ({
    label: `${invoice.invoiceNo} · ${invoice.customer || t('app.pos.walkIn')}`,
    value: invoice.saleId,
  }))
}

/** Product lines of the row's invoice (deliverable remainder only). */
function itemOptionsFor(row: Record<string, unknown>): Array<{ label: string, value: string }> {
  const invoice = invoiceById.value.get(String(row.saleId || ''))
  if (!invoice) return []
  return invoice.items.map(item => ({
    label: `${item.product} · ${t('app.delivery.qtyRemaining')} ${item.qtyRemaining}`,
    value: item.saleItemId,
  }))
}

function rowOf(saleId: string, item: DeliverableInvoiceItem): DeliveryRow {
  return {
    saleId,
    saleItemId: item.saleItemId,
    product: item.product,
    uomSymbol: item.uomSymbol,
    qtyOrdered: item.qtyOrdered,
    qtyRemaining: item.qtyRemaining,
    qtyToDeliver: item.qtyRemaining,
  }
}

const linesTable = computed<ModuleTable>(() => ({
  key: 'deliveryLines',
  title: t('app.delivery.lines'),
  addLabelKey: 'app.ui.addRow',
  columns: [
    {
      key: 'saleId',
      label: t('app.delivery.selectInvoices'),
      type: 'select',
      required: true,
      optionItems: () => invoiceOptionsFor(),
    },
    {
      key: 'saleItemId',
      label: t('app.pos.product'),
      type: 'select',
      required: true,
      optionItems: row => itemOptionsFor(row),
    },
    { key: 'uomSymbol', label: t('app.pos.uom'), type: 'text', computed: true },
    { key: 'qtyOrdered', label: t('app.delivery.qtyOrdered'), type: 'number', computed: true },
    { key: 'qtyRemaining', label: t('app.delivery.qtyRemaining'), type: 'number', computed: true },
    { key: 'qtyToDeliver', label: t('app.delivery.qtyToDeliver'), type: 'number', required: true },
  ],
}))

const tabs = computed<DocumentTabSchema[]>(() => [{
  id: 'general',
  labelKey: 'app.stock.tabGeneral',
  label: t('app.stock.tabGeneral'),
  sections: [
    {
      id: 'delivery-info',
      titleKey: 'app.delivery.infoSection',
      fields: [
        { key: 'deliveryPhone', labelKey: 'app.delivery.deliveryPhone', type: 'text', required: true },
        { key: 'deliveryLocation', labelKey: 'app.delivery.deliveryAddress', type: 'text', required: true },
        { key: 'note', labelKey: 'app.fields.note', type: 'textarea', colSpan: 2 },
      ],
    },
    {
      id: 'delivery-lines',
      titleKey: 'app.delivery.lines',
      fields: [
        {
          key: 'lines',
          labelKey: 'app.delivery.lines',
          type: 'line-table',
          colSpan: 2,
          meta: { table: linesTable.value },
        },
      ],
    },
  ],
}])

/**
 * Keep rows coherent: resolve the invoice's customer (same-customer rule),
 * snapshot product/UOM/quantities from the selected sale line, drop
 * duplicate lines, and default Qty to deliver to the remaining qty.
 */
const lastFilled = ref(new Set<string>())

watch(() => model.lines, (rows) => {
  if (!Array.isArray(rows)) return
  let changed = false
  let customerId = ''
  const seen = new Set<string>()
  const next: Array<Record<string, unknown>> = []
  for (const raw of rows as Array<Record<string, unknown>>) {
    const saleId = String(raw.saleId || '')
    if (!saleId) {
      // Blank row from Add row — keep it for editing.
      next.push(raw)
      continue
    }
    const invoice = invoiceById.value.get(saleId)
    if (!invoice) {
      changed = true
      continue
    }
    if (!customerId) customerId = invoice.customerId
    if (invoice.customerId !== customerId) {
      toast.add({
        title: t('app.delivery.mixedCustomer'),
        description: t('app.delivery.sameCustomerHint'),
        color: 'warning',
      })
      changed = true
      continue
    }
    const item = invoice.items.find(row => row.saleItemId === String(raw.saleItemId || ''))
      || invoice.items[0]
    if (!item) {
      changed = true
      continue
    }
    if (seen.has(item.saleItemId)) {
      changed = true
      continue
    }
    seen.add(item.saleItemId)
    const filledKey = `${item.saleItemId}`
    const typed = Number(raw.qtyToDeliver ?? 0)
    const qty = !lastFilled.value.has(filledKey) && typed <= 0
      ? item.qtyRemaining
      : Math.min(Math.max(0, typed), item.qtyRemaining)
    lastFilled.value.add(filledKey)
    const row = rowOf(saleId, item)
    row.qtyToDeliver = qty
    if (JSON.stringify(row) !== JSON.stringify(raw)) changed = true
    next.push(row)
  }
  if (changed || next.length !== rows.length) model.lines = next
}, { deep: true })

const deliveryRows = computed<DeliveryRow[]>(() =>
  (Array.isArray(model.lines) ? model.lines as DeliveryRow[] : []))

const submitRows = computed(() => deliveryRows.value.filter(row =>
  row.saleId && row.saleItemId && Number(row.qtyToDeliver) > 0))

const canSubmit = computed(() => Boolean(
  submitRows.value.length > 0
  && String(model.deliveryPhone || '').trim()
  && String(model.deliveryLocation || '').trim()))

async function save(confirm: boolean) {
  if (!canSubmit.value || saving.value) return
  if (confirm && !props.canConfirm) return
  saving.value = true
  try {
    const first = invoiceById.value.get(submitRows.value[0]!.saleId)
    const record = await deliveryCommands.createDeliveryNote({
      customerId: first?.customerId || null,
      deliveryPhone: String(model.deliveryPhone || '').trim() || null,
      deliveryLocation: String(model.deliveryLocation || '').trim() || null,
      note: String(model.note || '').trim() || null,
      confirm,
      lines: submitRows.value.map(row => ({
        saleId: row.saleId,
        saleItemId: row.saleItemId,
        productId: String(invoiceById.value.get(row.saleId)?.items
          .find(item => item.saleItemId === row.saleItemId)?.productId || ''),
        qtyToDeliver: Number(row.qtyToDeliver),
      })),
    })
    toast.add({
      title: `${t('app.delivery.created')} · ${record.deliveryNo}`,
      color: 'success',
    })
    if (props.printOnCreate) await printDeliveryNoteDocument(record, props.shopName)
    emit('created', record)
  }
  catch (error: unknown) {
    toast.add({
      title: t('app.delivery.createFailed'),
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
    :pending="loading"
    :saving="saving"
    :can-save="canSubmit"
    :is-create="true"
    :show-tabs="false"
    :show-save="false"
    content-wide
    :show-cancel="true"
    list-to="/delivery-notes"
    :can-export="false"
    @save="save(true)"
  >
    <template #actions>
      <UButton
        color="neutral"
        variant="soft"
        icon="i-lucide-save"
        size="sm"
        :label="t('app.delivery.saveDraft')"
        :loading="saving"
        :disabled="!canSubmit"
        @click="save(false)"
      />
      <UButton
        v-if="canConfirm"
        color="primary"
        icon="i-lucide-check-circle-2"
        size="sm"
        :label="t('app.delivery.saveConfirm')"
        :loading="saving"
        :disabled="!canSubmit"
        @click="save(true)"
      />
    </template>
  </DocumentAppDocumentPage>
</template>