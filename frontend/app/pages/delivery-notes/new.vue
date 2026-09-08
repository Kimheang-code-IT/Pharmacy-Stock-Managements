<script setup lang="ts">
import { useAppHeader } from '~/composables/layout/useAppHeader'
import { useDeliveryCommands, useSettingsRepositories } from '~/repositories/index'
import {
  normalizeDeliverableInvoice,
  type DeliverableInvoice,
  type DeliverableInvoiceItem,
} from '~/utils/delivery/notes'
import { printDeliveryNoteDocument } from '~/utils/print/delivery-note'

/**
 * Create a delivery note (spec §2.1.9 / §5.13). Multi-invoice: pick any
 * confirmed invoices (of the SAME customer — enforced here and server-side)
 * from GET /delivery-notes/deliverable-invoices, enter phone + location, then
 * set per-line quantities within the remaining undelivered qty. No
 * driver/vehicle/schedule form; no stock is moved here — the stock-out
 * already happened at POS.
 */
definePageMeta({
  titleKey: 'app.pages.deliveryNotes',
  permission: 'delivery.create',
})

const route = useRoute()
const store = useAppDataStore()
const auth = useAuthStore()
const { t } = useI18n()
const { setTitle, setBreadcrumbs, clear } = useAppHeader()
const deliveryCommands = useDeliveryCommands()
const { appInfo } = useSettingsRepositories()
const toast = useToast()

onBeforeUnmount(clear)

const loading = ref(false)
const saving = ref(false)
const shopName = ref('Yoeun Sokhon Pharmacy')
const invoiceSearch = ref('')
const selectedSaleIds = ref<string[]>([])
const deliveryPhone = ref('')
const deliveryLocation = ref('')
const note = ref('')
const lineQty = ref<Record<string, number>>({})
const invoices = ref<DeliverableInvoice[]>([])

setTitle(t('app.delivery.newTitle'))
setBreadcrumbs([
  { label: t('app.nav.deliveryNotes'), to: '/delivery-notes' },
  { label: t('app.delivery.newTitle') },
])

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([
      loadDeliverableInvoices(),
      store.fetchList('customers'),
    ])
    // POS auto-entry: preselect the sale that just completed.
    const preselect = String(route.query.saleId || '')
    if (preselect) selectedSaleIds.value = [preselect]
    try {
      const info = await appInfo.get()
      const name = String(info.businessName || info.applicationName || '').trim()
      if (name) shopName.value = name
    }
    catch {
      // Keep default shop name when settings are unavailable.
    }
  }
  finally {
    loading.value = false
  }
})

async function loadDeliverableInvoices() {
  const rows = await deliveryCommands.deliverableInvoices(invoiceSearch.value || null)
  invoices.value = rows
    .map(row => normalizeDeliverableInvoice(row as Record<string, unknown>))
    .filter(row => row.items.length > 0)
}

const invoiceOptions = computed(() => invoices.value.map(invoice => ({
  label: `${invoice.invoiceNo} · ${invoice.customer || t('app.pos.walkIn')} · ${invoice.items.length} item(s)`,
  value: invoice.saleId,
})))

const invoiceById = computed(() =>
  new Map(invoices.value.map(invoice => [invoice.saleId, invoice])))

/** Selected invoices; same-customer is enforced on selection. */
const selectedInvoices = computed<DeliverableInvoice[]>(() =>
  selectedSaleIds.value
    .map(id => invoiceById.value.get(id))
    .filter((invoice): invoice is DeliverableInvoice => Boolean(invoice)))

const selectedCustomerId = computed(() => selectedInvoices.value[0]?.customerId || '')

/** Reject adding an invoice of a DIFFERENT customer (spec: one note = one customer). */
function onInvoicesChange(values: string[]) {
  const added = values.find(id => !selectedSaleIds.value.includes(id))
  if (added) {
    const addedInvoice = invoiceById.value.get(added)
    if (selectedCustomerId.value && addedInvoice && addedInvoice.customerId !== selectedCustomerId.value) {
      toast.add({
        title: t('app.delivery.mixedCustomer'),
        description: t('app.delivery.sameCustomerHint'),
        color: 'warning',
      })
      return
    }
  }
  selectedSaleIds.value = values
}

/** All selected lines with a quantity to deliver. */
const selectedLines = computed(() => selectedInvoices.value.flatMap(invoice =>
  invoice.items
    .map((item: DeliverableInvoiceItem) => ({
      invoice,
      item,
      qty: Math.min(Math.max(0, Number(lineQty.value[item.saleItemId] ?? 0)), item.qtyRemaining),
    }))
    .filter(entry => entry.qty > 0)))

const deliverableLineCount = computed(() => selectedInvoices.value
  .reduce((sum, invoice) => sum + invoice.items.length, 0))

const canSubmit = computed(() => Boolean(
  selectedLines.value.length > 0
  && String(deliveryPhone.value || '').trim()
  && String(deliveryLocation.value || '').trim()))

function fillRemaining() {
  const next: Record<string, number> = {}
  for (const invoice of selectedInvoices.value) {
    for (const item of invoice.items) {
      if (item.qtyRemaining > 0) next[item.saleItemId] = item.qtyRemaining
    }
  }
  lineQty.value = next
}

function setQty(saleItemId: string, value: number | undefined, max: number) {
  const qty = Math.max(0, Math.min(max, Number(value ?? 0)))
  lineQty.value = { ...lineQty.value, [saleItemId]: qty }
}

async function submit(confirm: boolean) {
  if (!canSubmit.value || saving.value) return
  if (confirm && !auth.canAccessPage('delivery.confirm')) return
  saving.value = true
  try {
    const record = await deliveryCommands.createDeliveryNote({
      customerId: selectedCustomerId.value || null,
      deliveryPhone: String(deliveryPhone.value || '').trim() || null,
      deliveryLocation: String(deliveryLocation.value || '').trim() || null,
      note: note.value?.trim() || null,
      confirm,
      lines: selectedLines.value.map(({ invoice, item, qty }) => ({
        saleId: invoice.saleId,
        saleItemId: item.saleItemId,
        productId: item.productId,
        qtyToDeliver: qty,
      })),
    })
    toast.add({
      title: `${t('app.delivery.created')} · ${record.deliveryNo}`,
      color: 'success',
    })
    await printDeliveryNoteDocument(record, shopName.value)
    await navigateTo(`/delivery-notes/${String(record.id)}`)
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
  <div class="flex h-full min-h-0 flex-1 flex-col gap-3 overflow-y-auto bg-muted/20 p-3">
    <p v-if="loading" class="text-sm text-muted">{{ t('common.loading') }}</p>

    <template v-else>
      <UCard :ui="{ body: 'p-3 sm:p-3' }">
        <div class="grid grid-cols-1 gap-3 lg:grid-cols-2">
          <CommonAppField
            :label="t('app.delivery.selectInvoices')"
            :required="true"
            :help="t('app.delivery.sameCustomerHint')"
          >
            <USelectMenu
              :model-value="selectedSaleIds"
              :items="invoiceOptions"
              multiple
              value-key="value"
              :search-input="true"
              :disabled="invoiceOptions.length === 0"
              :placeholder="invoiceOptions.length === 0 ? t('app.delivery.noDeliverableSales') : t('app.delivery.selectInvoicesPlaceholder')"
              class="w-full"
              @update:model-value="onInvoicesChange(($event || []) as string[])"
            />
          </CommonAppField>
          <div class="flex items-end justify-between gap-2">
            <p v-if="selectedSaleIds.length" class="text-xs text-muted">
              {{ t('app.delivery.invoicesSelected', { n: selectedSaleIds.length }) }}
              · {{ t('app.delivery.deliverableLines', { n: deliverableLineCount }) }}
            </p>
            <p v-else-if="invoiceOptions.length === 0" class="text-xs text-warning">
              {{ t('app.delivery.noDeliverableSales') }}
            </p>
          </div>
        </div>
        <div class="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
          <CommonAppTextField
            v-model="deliveryPhone"
            :label="t('app.delivery.deliveryPhone')"
            :required="true"
            class="w-full"
          />
          <CommonAppTextField
            v-model="deliveryLocation"
            :label="t('app.delivery.deliveryAddress')"
            :required="true"
            class="w-full"
          />
          <CommonAppTextareaField
            v-model="note"
            :label="t('app.fields.note')"
            :rows="2"
            class="w-full lg:col-span-2"
          />
        </div>
      </UCard>

      <UCard v-if="selectedInvoices.length" :ui="{ body: 'p-0 sm:p-0' }">
        <template #header>
          <div class="flex items-center justify-between gap-2">
            <p class="text-sm font-medium">{{ t('app.delivery.lines') }}</p>
            <UButton
              size="xs"
              variant="soft"
              color="primary"
              icon="i-lucide-list-check"
              :label="t('app.delivery.fillRemaining')"
              :disabled="deliverableLineCount === 0"
              @click="fillRemaining"
            />
          </div>
        </template>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-elevated text-left text-xs text-muted">
              <tr>
                <th class="px-3 py-2 font-medium">{{ t('app.fields.invoice') }}</th>
                <th class="px-3 py-2 font-medium">{{ t('app.fields.product') }}</th>
                <th class="px-3 py-2 font-medium">{{ t('app.fields.uom') }}</th>
                <th class="px-3 py-2 text-right font-medium">{{ t('app.delivery.qtyOrdered') }}</th>
                <th class="px-3 py-2 text-right font-medium">{{ t('app.delivery.qtyRemaining') }}</th>
                <th class="px-3 py-2 text-right font-medium">{{ t('app.delivery.qtyToDeliver') }}</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="invoice in selectedInvoices" :key="invoice.saleId">
                <tr
                  v-for="item in invoice.items"
                  :key="item.saleItemId"
                  class="border-t border-default"
                >
                  <td class="px-3 py-2 text-muted">{{ invoice.invoiceNo }}</td>
                  <td class="px-3 py-2 font-medium">{{ item.product }}</td>
                  <td class="px-3 py-2 text-muted">{{ item.uomSymbol || '—' }}</td>
                  <td class="px-3 py-2 text-right tabular-nums">{{ item.qtyOrdered }}</td>
                  <td class="px-3 py-2 text-right tabular-nums text-default">{{ item.qtyRemaining }}</td>
                  <td class="px-3 py-2 text-right">
                    <CommonAppNumberField
                      :model-value="Number(lineQty[item.saleItemId] ?? 0) || undefined"
                      :min="0"
                      :max="item.qtyRemaining"
                      :step="1"
                      :disabled="item.qtyRemaining <= 0"
                      class="w-24 align-middle"
                      @update:model-value="setQty(item.saleItemId, $event, item.qtyRemaining)"
                    />
                  </td>
                </tr>
              </template>
              <tr v-if="!selectedLines.length && !deliverableLineCount">
                <td colspan="6" class="px-3 py-4 text-center text-sm text-muted">{{ t('app.ui.noRecords') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </UCard>

      <div class="flex items-center justify-end gap-2">
        <UButton
          color="neutral"
          variant="ghost"
          :label="t('common.cancel')"
          :disabled="saving"
          @click="navigateTo('/delivery-notes')"
        />
        <UButton
          color="neutral"
          variant="soft"
          icon="i-lucide-save"
          :label="t('app.delivery.saveDraft')"
          :loading="saving"
          :disabled="!canSubmit"
          @click="submit(false)"
        />
        <UButton
          v-if="auth.canAccessPage('delivery.confirm')"
          color="primary"
          icon="i-lucide-check-circle-2"
          :label="t('app.delivery.saveConfirm')"
          :loading="saving"
          :disabled="!canSubmit"
          @click="submit(true)"
        />
      </div>
    </template>
  </div>
</template>
