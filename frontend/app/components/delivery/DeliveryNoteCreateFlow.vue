<script setup lang="ts">
import type { AppRecord } from '~/config/admin-seed'
import type { ModuleTable } from '~/config/modules'
import type { DocumentTabSchema } from '~/types/stock-pos/common'
import { useDeliveryCommands } from '~/repositories/index'
import { collectionOptionsEndpoint } from '~/utils/module/document-tabs'
import {
  invoiceDeliveryStatusLabelKey,
  normalizeDeliverableInvoice,
  noteSales,
  type DeliverableInvoice,
} from '~/utils/delivery/notes'
import { printDeliveryNoteDocument } from '~/utils/print/delivery-note'
import { apiErrorMessage, isApiErrorHandled } from '~/utils/api/errors'

/**
 * Reusable delivery-note create flow (spec §2.1.9 / §5.13) — built on the
 * same reusable document components as the purchase page:
 * DocumentAppDocumentPage + schema-driven AppDocumentForm sections +
 * the generic TableAppLineTable. Simplified invoice-level UI:
 *
 * - "Delivery Information" header section: customer (required), phone
 *   (required), address (required), delivery price, note. Driver / vehicle /
 *   date / status stay backend-managed (not part of the visible form).
 * - "Invoices to deliver" line table: each row adds ONE invoice — the
 *   picker offers only the selected customer's deliverable invoices
 *   (same-customer rule, searchable by invoice no), auto-fills the row's
 *   Date + Status, and blocks duplicate selection. Multiple invoices of the
 *   SAME customer can be added as rows. Every selected invoice expands to
 *   its deliverable item lines (full remaining qty) on submit — the item
 *   level delivery-note API contract (saleId / saleItemId / productId /
 *   qtyToDeliver) is unchanged.
 *
 * POS auto-entry passes `autoSelectSaleId` (invoice that just completed,
 * row prefilled) plus `initialPhone` / `initialLocation` from the checkout
 * snapshot. No stock mutation (stock-out already happened at POS).
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
  /** Allow saving edits (delivery.update permission); edit mode only. */
  canUpdate?: boolean
  /** Auto-print the bilingual note after creation. */
  printOnCreate?: boolean
  shopName?: string
  /** Existing draft note to edit — turns the flow into an edit form. */
  editNote?: AppRecord | null
}>(), {
  canConfirm: true,
  canUpdate: true,
  printOnCreate: true,
  shopName: 'Yoeun Sokhon Pharmacy',
  editNote: null,
})

const emit = defineEmits<{
  /** Created record (deliveryNo included) after a successful save. */
  created: [record: AppRecord]
}>()

const deliveryCommands = useDeliveryCommands()
const { t } = useI18n()
const toast = useToast()

const model = reactive<Record<string, unknown>>({
  customerId: '',
  deliveryPhone: '',
  deliveryLocation: '',
  deliveryFee: undefined,
  note: '',
  // Backend-managed fields (not part of the visible form): driver / vehicle
  // stay unset and the note is dated today until the workflow advances.
  driverName: '',
  vehicleNo: '',
  deliveryDate: new Date().toISOString().slice(0, 10),
  status: 'Draft',
  lines: [] as Array<Record<string, unknown>>,
})

function fieldValue(key: string): unknown {
  return model[key]
}

function setFieldValue(key: string, value: unknown): void {
  model[key] = value
}

/** Deliverable invoices offered by the picker (create mode + additions). */
const deliverable = ref<DeliverableInvoice[]>([])
const loading = ref(false)
const saving = ref(false)

const isEdit = computed(() => Boolean(props.editNote))
const canSave = computed(() => !isEdit.value || props.canUpdate)

/** Lines of the note being edited (edit mode) as normalized invoices. */
const noteInvoices = computed<DeliverableInvoice[]>(() => {
  const note = props.editNote
  if (!note) return []
  const links = noteSales(note)
  const items = Array.isArray(note.items) ? note.items as AppRecord[] : []
  return links.map((link) => {
    const mapped = items
      .filter(item => String(item.saleId || '') === link.saleId || links.length === 1)
      .map(item => ({
        saleItemId: String(item.saleItemId || ''),
        productId: String(item.productId || ''),
        product: String(item.product || ''),
        sku: '',
        uomSymbol: String(item.uomSymbol || ''),
        qtyOrdered: Number(item.qtyOrdered ?? 0),
        qtyRemaining: Number(item.qtyToDeliver ?? 0),
      }))
    return {
      saleId: link.saleId,
      invoiceNo: link.invoiceNo || '—',
      customerId: String(note.customerId || ''),
      customer: String(note.customer || ''),
      phone: String(note.deliveryPhone || ''),
      location: String(note.deliveryLocation || note.deliveryAddress || ''),
      saleStatus: '',
      date: '',
      deliveryStatus: 'PENDING',
      qtyRemaining: mapped.reduce((sum, item) => sum + item.qtyRemaining, 0),
      items: mapped,
    }
  })
})

/** Edit mode keeps the note's own invoices even when fully reserved. */
const invoices = computed<DeliverableInvoice[]>(() => {
  const map = new Map<string, DeliverableInvoice>()
  for (const invoice of noteInvoices.value) map.set(invoice.saleId, invoice)
  for (const invoice of deliverable.value) if (!map.has(invoice.saleId)) map.set(invoice.saleId, invoice)
  return [...map.values()]
})

/** Edit mode: prefill the header + invoice rows from the existing note. */
function applyEditNote(note: AppRecord) {
  model.customerId = String(note.customerId || '')
  model.deliveryPhone = String(note.deliveryPhone || '')
  model.deliveryLocation = String(note.deliveryLocation || note.deliveryAddress || '')
  model.deliveryFee = Number(note.deliveryFee ?? note.deliveryPrice ?? note.delivery_fee ?? 0) || undefined
  model.note = String(note.note || '')
  model.driverName = String(note.driverName || '')
  model.vehicleNo = String(note.vehicleNo || '')
  model.lines = noteSales(note).map(link => ({
    saleId: link.saleId,
    invoiceNo: link.invoiceNo,
    invoiceStatus: '',
  }))
}

onMounted(async () => {
  if (props.initialPhone) model.deliveryPhone = props.initialPhone
  if (props.initialLocation) model.deliveryLocation = props.initialLocation
  loading.value = true
  try {
    const rows = await deliveryCommands.deliverableInvoices(null)
    deliverable.value = rows
      .map(row => normalizeDeliverableInvoice(row as Record<string, unknown>))
      .filter(row => row.items.length > 0)
    if (props.editNote) {
      applyEditNote(props.editNote)
      return
    }
    const preselect = String(props.autoSelectSaleId || '')
    if (preselect) {
      const invoice = invoiceById.value.get(preselect)
      if (invoice) {
        model.customerId = invoice.customerId
        model.lines = [{ saleId: preselect, invoiceNo: invoice.invoiceNo, invoiceStatus: '' }]
      }
      else toast.add({ title: t('app.delivery.noDeliverableSales'), color: 'warning' })
    }
  }
  finally {
    loading.value = false
  }
})

const invoiceById = computed(() =>
  new Map(invoices.value.map(invoice => [invoice.saleId, invoice])))

/** Invoice picker of a row: only the selected customer's deliverable
 *  invoices (same-customer rule, spec §2.1.9), minus invoices already
 *  picked on other rows (no duplicates). Label = invoice no; searchable. */
function invoiceOptionsFor(row: Record<string, unknown>): Array<{ label: string, value: string }> {
  const customerId = String(model.customerId || '')
  const rows = Array.isArray(model.lines) ? model.lines as Array<Record<string, unknown>> : []
  const own = String(row.saleId || '')
  const taken = new Set(rows
    .filter(other => other !== row)
    .map(other => String(other.saleId || ''))
    .filter(Boolean))
  const items = invoices.value
    // The row's own invoice is always offered (so the picker shows its number,
    // never the raw UUID) even when it is no longer "deliverable" or the
    // customer filter would drop it.
    .filter(invoice => invoice.saleId === own
      || ((!customerId || invoice.customerId === customerId) && !taken.has(invoice.saleId)))
    .map(invoice => ({ label: invoice.invoiceNo, value: invoice.saleId }))
  if (own && !items.some(item => item.value === own)) {
    const stored = String(row.invoiceNo || '').trim()
    items.unshift({ label: stored || own, value: own })
  }
  return items
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
      // Searchable invoice-no picker; wide column carries the dropdown.
      searchable: true,
      width: 'w-80 min-w-64',
      optionItems: row => invoiceOptionsFor(row),
    },
    // Auto-filled snapshot of the selected invoice (display only).
    { key: 'invoiceStatus', label: t('app.fields.status'), type: 'text', computed: true, width: 'w-36 min-w-32' },
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
        // Customer first — only this customer's deliverable invoices are
        // offered in the line table (same-customer rule).
        {
          key: 'customerId',
          labelKey: 'app.pos.customer',
          type: 'select',
          required: true,
          // The customer is fixed once a note exists (backend update keeps it).
          readOnly: isEdit.value,
          optionsEndpoint: collectionOptionsEndpoint('customers'),
        },
        { key: 'deliveryPhone', labelKey: 'app.delivery.deliveryPhone', type: 'text', required: true },
        { key: 'deliveryLocation', labelKey: 'app.delivery.deliveryAddress', type: 'text', required: true },
        { key: 'deliveryFee', labelKey: 'app.delivery.deliveryPrice', type: 'number' },
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

// Customer changed → drop lines that belong to another customer.
watch(() => model.customerId, (customerId) => {
  const selected = String(customerId || '')
  if (!selected) return
  const rows = Array.isArray(model.lines) ? model.lines as Array<Record<string, unknown>> : []
  const kept = rows.filter((row) => {
    const invoice = invoiceById.value.get(String(row.saleId || ''))
    return !invoice || invoice.customerId === selected
  })
  if (kept.length !== rows.length) model.lines = kept
})

/**
 * Keep rows coherent: every selected invoice must belong to the form's
 * customer (same-customer rule), may appear on ONE row only (no duplicate
 * selection), and auto-fills the row's Date + Status from the invoice.
 */
watch(() => model.lines, (rows) => {
  if (!Array.isArray(rows)) return
  let changed = false
  const selectedCustomer = String(model.customerId || '')
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
    if (selectedCustomer && invoice.customerId !== selectedCustomer) {
      toast.add({
        title: t('app.delivery.mixedCustomer'),
        description: t('app.delivery.sameCustomerHint'),
        color: 'warning',
      })
      changed = true
      continue
    }
    if (seen.has(saleId)) {
      // Duplicate invoice selection — keep only the first row.
      changed = true
      continue
    }
    seen.add(saleId)
    const row = {
      saleId,
      invoiceNo: invoice.invoiceNo,
      invoiceStatus: t(invoiceDeliveryStatusLabelKey(invoice.deliveryStatus)),
    }
    if (JSON.stringify(row) !== JSON.stringify(raw)) changed = true
    next.push(row)
  }
  if (changed || next.length !== rows.length) model.lines = next
}, { deep: true })

/** Invoices picked on the rows (order preserved). */
const selectedInvoices = computed<DeliverableInvoice[]>(() =>
  (Array.isArray(model.lines) ? model.lines as Array<Record<string, unknown>> : [])
    .map(row => invoiceById.value.get(String(row.saleId || '')))
    .filter((invoice): invoice is DeliverableInvoice => Boolean(invoice)))

const canSubmit = computed(() => Boolean(
  selectedInvoices.value.length > 0
  && String(model.customerId || '').trim()
  && String(model.deliveryPhone || '').trim()
  && String(model.deliveryLocation || '').trim()))

async function save(confirm: boolean) {
  if (!canSubmit.value || saving.value) return
  if (isEdit.value && !props.canUpdate) return
  // A single Submit: confirm when the user has the permission, else just save.
  const doConfirm = confirm && props.canConfirm
  saving.value = true
  try {
    const first = selectedInvoices.value[0]
    // Each selected invoice expands to its deliverable item lines at their
    // full remaining qty (required saleItemId/productId intact). In edit mode
    // the note's own lines carry their reserved qty as "remaining".
    const lines = selectedInvoices.value.flatMap(invoice =>
      invoice.items.map(item => ({
        saleId: invoice.saleId,
        saleItemId: item.saleItemId,
        productId: item.productId,
        qtyToDeliver: item.qtyRemaining,
      })))

    if (isEdit.value && props.editNote) {
      let record = await deliveryCommands.updateDeliveryNote(String(props.editNote.id), {
        deliveryPhone: String(model.deliveryPhone || '').trim() || null,
        deliveryLocation: String(model.deliveryLocation || '').trim() || null,
        deliveryFee: Number(model.deliveryFee ?? 0) > 0 ? Number(model.deliveryFee) : null,
        note: String(model.note || '').trim() || null,
        lines,
      })
      if (doConfirm) record = await deliveryCommands.setDeliveryStatus(String(record.id), 'confirm')
      toast.add({ title: t('app.delivery.updated'), color: 'success' })
      emit('created', record)
      return
    }

    const record = await deliveryCommands.createDeliveryNote({
      customerId: String(model.customerId || '').trim() || first?.customerId || null,
      deliveryPhone: String(model.deliveryPhone || '').trim() || null,
      deliveryLocation: String(model.deliveryLocation || '').trim() || null,
      // Backend-managed header fields kept intact (not part of the form).
      driverName: String(model.driverName || '').trim() || null,
      vehicleNo: String(model.vehicleNo || '').trim() || null,
      deliveryDate: String(model.deliveryDate || '').trim() || null,
      deliveryFee: Number(model.deliveryFee ?? 0) > 0 ? Number(model.deliveryFee) : null,
      note: String(model.note || '').trim() || null,
      confirm: doConfirm,
      lines,
    })
    toast.add({
      title: `${t('app.delivery.created')} · ${record.deliveryNo}`,
      color: 'success',
    })
    if (props.printOnCreate) await printDeliveryNoteDocument(record, props.shopName)
    emit('created', record)
  }
  catch (error: unknown) {
    if (!isApiErrorHandled(error)) {
      toast.add({
        title: isEdit.value ? t('app.delivery.updateFailed') : t('app.delivery.createFailed'),
        description: apiErrorMessage(
          error,
          isEdit.value ? t('app.delivery.updateFailed') : t('app.delivery.createFailed'),
        ),
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
  <DocumentAppDocumentPage
    :tabs="tabs"
    active-tab="general"
    :field-value="fieldValue"
    :set-field-value="setFieldValue"
    :pending="loading"
    :saving="saving"
    :can-save="canSubmit && canSave"
    :confirm-save="canSave"
    :is-create="!isEdit"
    :show-tabs="false"
    content-wide
    :show-cancel="true"
    list-to="/delivery-notes"
    :can-export="false"
    @save="save(true)"
  />
</template>