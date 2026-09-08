<script setup lang="ts">
import { useAppHeader } from '~/composables/layout/useAppHeader'
import { useDeliveryCommands, useSettingsRepositories } from '~/repositories/index'
import {
  deliverableLines,
  saleHasDeliverableLines,
  type DeliveryLineAvailability,
} from '~/utils/delivery/notes'
import { printDeliveryNoteDocument } from '~/utils/print/delivery-note'

/**
 * Create a delivery note from a POS sale (spec §2.1.9 / §5.13). No contact /
 * driver / schedule form: receiver, phone and address auto-fill from the
 * linked sale / customer snapshot and the page goes straight to the lines
 * table. Quantities are validated against the remaining undelivered qty per
 * sale line across non-cancelled notes. No stock is moved here — the
 * stock-out already happened at POS.
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
const saleId = ref('')
const lineQty = ref<Record<string, number>>({})

setTitle(t('app.delivery.newTitle'))
setBreadcrumbs([
  { label: t('app.nav.deliveryNotes'), to: '/delivery-notes' },
  { label: t('app.delivery.newTitle') },
])

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([
      store.fetchList('sales'),
      store.fetchList('deliveryNotes'),
      store.fetchList('customers'),
    ])
    const preselect = String(route.query.saleId || '')
    if (preselect && store.list('sales').some(row => String(row.id) === preselect)) {
      saleId.value = preselect
    }
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

/** Sales that still have at least one line with remaining deliverable qty. */
const salesWithDeliverableLines = computed(() => store.list('sales')
  .filter(sale => saleHasDeliverableLines(sale, store.list('deliveryNotes')))
  .slice(0, 100))

const saleOptions = computed(() => salesWithDeliverableLines.value.map(sale => ({
  label: `${sale.invoiceNo || sale.saleNo} · ${sale.customer || t('app.pos.walkIn')} · ${String(sale.date || '').slice(0, 10)}`,
  value: String(sale.id),
})))

const selectedSale = computed(() => store.list('sales')
  .find(sale => String(sale.id) === saleId.value) || null)

const selectedSaleLines = computed<DeliveryLineAvailability[]>(() =>
  selectedSale.value ? deliverableLines(selectedSale.value, store.list('deliveryNotes')) : [])

const deliverableLineCount = computed(() => selectedSaleLines.value.filter(line => line.qtyRemaining > 0).length)

function selectSale(id: string) {
  saleId.value = id
  lineQty.value = {}
}

function remainingFor(line: DeliveryLineAvailability): number {
  return line.qtyRemaining
}

function qtyFor(line: DeliveryLineAvailability): number {
  return Number(lineQty.value[line.saleItemId] ?? 0)
}

function setQty(line: DeliveryLineAvailability, value: number | undefined) {
  const max = remainingFor(line)
  const qty = Math.max(0, Math.min(max, Number(value ?? 0)))
  lineQty.value = { ...lineQty.value, [line.saleItemId]: qty }
}

function fillRemaining() {
  const next: Record<string, number> = {}
  for (const line of selectedSaleLines.value) {
    if (line.qtyRemaining > 0) next[line.saleItemId] = line.qtyRemaining
  }
  lineQty.value = next
}

const selectedLines = computed(() => selectedSaleLines.value
  .map(line => ({ line, qty: qtyFor(line) }))
  .filter(entry => entry.qty > 0))

const canSubmit = computed(() => Boolean(saleId.value) && selectedLines.value.length > 0)

async function submit(confirm: boolean) {
  if (!canSubmit.value || saving.value) return
  if (confirm && !auth.canAccessPage('delivery.confirm')) return
  saving.value = true
  try {
    // Receiver fields come from the sale / customer snapshot — the user
    // never re-types contact data on a Delivery Notes form.
    const sale = selectedSale.value
    const customer = sale?.customerId
      ? store.list('customers').find(row => String(row.id) === String(sale.customerId))
      : null
    const record = await deliveryCommands.createDeliveryNote({
      saleId: saleId.value,
      deliveryName: customer?.name
        ? String(customer.name)
        : String(sale?.customer || '') || null,
      deliveryPhone: customer?.phone ? String(customer.phone) : null,
      deliveryAddress: customer
        ? String(customer.location || customer.address || '') || null
        : null,
      scheduledDate: new Date().toISOString().slice(0, 10),
      driverName: null,
      vehicleNote: null,
      note: null,
      confirm,
      lines: selectedLines.value.map(({ line, qty }) => ({
        saleItemId: line.saleItemId,
        productId: line.productId,
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
          <CommonAppSelectMenuField
            :model-value="saleId"
            :items="saleOptions"
            :label="t('app.delivery.selectSale')"
            :label-key="'app.delivery.selectSale'"
            :placeholder="t('app.delivery.selectSalePlaceholder')"
            :required="true"
            :search-input="true"
            :disabled="saleOptions.length === 0"
            @update:model-value="selectSale(String($event || ''))"
          />
          <div class="flex items-end">
            <p v-if="saleId" class="text-xs text-muted">
              {{ t('app.delivery.deliverableLines', { n: deliverableLineCount }) }}
            </p>
            <p v-else-if="saleOptions.length === 0" class="text-xs text-warning">
              {{ t('app.delivery.noDeliverableSales') }}
            </p>
          </div>
        </div>
      </UCard>

      <UCard v-if="selectedSale" :ui="{ body: 'p-0 sm:p-0' }">
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
                <th class="px-3 py-2 font-medium">{{ t('app.fields.product') }}</th>
                <th class="px-3 py-2 font-medium">{{ t('app.fields.uom') }}</th>
                <th class="px-3 py-2 text-right font-medium">{{ t('app.delivery.qtyOrdered') }}</th>
                <th class="px-3 py-2 text-right font-medium">{{ t('app.delivery.qtyReserved') }}</th>
                <th class="px-3 py-2 text-right font-medium">{{ t('app.delivery.qtyRemaining') }}</th>
                <th class="px-3 py-2 text-right font-medium">{{ t('app.delivery.qtyToDeliver') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="line in selectedSaleLines" :key="line.saleItemId" class="border-t border-default">
                <td class="px-3 py-2 font-medium">{{ line.product }}</td>
                <td class="px-3 py-2 text-muted">{{ line.uomSymbol || '—' }}</td>
                <td class="px-3 py-2 text-right tabular-nums">{{ line.qtyOrdered }}</td>
                <td class="px-3 py-2 text-right tabular-nums">{{ line.qtyReserved }}</td>
                <td class="px-3 py-2 text-right tabular-nums" :class="line.qtyRemaining > 0 ? 'text-default' : 'text-muted'">
                  {{ line.qtyRemaining }}
                </td>
                <td class="px-3 py-2 text-right">
                  <CommonAppNumberField
                    :model-value="qtyFor(line) || undefined"
                    :min="0"
                    :max="remainingFor(line)"
                    :step="1"
                    :disabled="line.qtyRemaining <= 0"
                    class="w-24 align-middle"
                    @update:model-value="setQty(line, $event)"
                  />
                </td>
              </tr>
              <tr v-if="!selectedSaleLines.length">
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
