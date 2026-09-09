<script setup lang="ts">
import { useAppHeader } from '~/composables/layout/useAppHeader'
import { useConfirm } from '~/composables/common/useConfirm'
import { useDeliveryCommands, useSettingsRepositories } from '~/repositories/index'
import {
  canTransitionAction,
  deliveryLines,
  deliveryStatusOf,
  noteInvoiceNos,
  type DeliveryStatusAction,
} from '~/utils/delivery/notes'
import { printDeliveryNoteDocument } from '~/utils/print/delivery-note'
import type { AppRecord } from '~/config/admin-seed'

/**
 * Delivery note detail (spec §2.1.9 / §5.13): header chrome only (status
 * badge + **Delivery OK** + optional Cancel + Print) above a single lines
 * table from the linked POS sale. No contact/driver/schedule form — those
 * live only in the sale/customer snapshot used for printing. Delivery never
 * mutates stock.
 */
definePageMeta({
  titleKey: 'app.pages.deliveryNotes',
  permission: 'delivery.view',
})

const route = useRoute()
const store = useAppDataStore()
const auth = useAuthStore()
const { t } = useI18n()
const { setTitle, setBreadcrumbs, clear } = useAppHeader()
const deliveryCommands = useDeliveryCommands()
const { appInfo } = useSettingsRepositories()
const toast = useToast()
const { confirm } = useConfirm()

onBeforeUnmount(clear)

const noteId = computed(() => String(route.params.id || ''))
const loading = ref(false)
const busy = ref(false)
const cancelOpen = ref(false)
const cancelReason = ref('')

const note = computed(() => store.get('deliveryNotes', noteId.value) as AppRecord | null)
const status = computed(() => deliveryStatusOf(note.value))
const lines = computed(() => deliveryLines(note.value))
const shopName = ref('Yoeun Sokhon Pharmacy')

watch(note, (value) => {
  if (!value) return
  setTitle(String(value.deliveryNo || ''))
  setBreadcrumbs([
    { label: t('app.nav.deliveryNotes'), to: '/delivery-notes' },
    { label: String(value.deliveryNo || '') },
  ])
}, { immediate: true })

onMounted(async () => {
  loading.value = true
  try {
    if (!store.get('deliveryNotes', noteId.value)) await store.fetchOne('deliveryNotes', noteId.value)
    await Promise.all([
      store.fetchList('sales'),
      store.fetchList('customers'),
    ])
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

/** Multi-invoice notes (spec §2.1.9): the joined invoice list is shown in
 *  the lines card; the first linked sale (if any) stays available for lookups. */
const linkedInvoiceNos = computed(() => noteInvoiceNos(note.value))

/* ------------------------------ permissions ------------------------------ */

const canDeliver = computed(() => auth.canAccessPage('delivery.deliver'))
const canCancel = computed(() => auth.canAccessPage('delivery.cancel'))

function allowed(action: DeliveryStatusAction): boolean {
  return Boolean(note.value) && canTransitionAction(note.value as AppRecord, action)
}

/** Simplified actions (spec §5.13): Delivery OK when possible, else Cancel. */
const statusActions = computed(() => ([
  { action: 'deliver' as const, label: t('app.delivery.actionDeliveryOk'), icon: 'i-lucide-package-check', color: 'success' as const, solid: true, enabled: allowed('deliver') && canDeliver.value },
  { action: 'cancel' as const, label: t('app.delivery.actionCancel'), icon: 'i-lucide-circle-off', color: 'error' as const, solid: false, enabled: allowed('cancel') && canCancel.value },
]).filter(item => item.enabled))

/* ------------------------------ transitions ------------------------------ */

async function runAction(action: DeliveryStatusAction, reason?: string | null) {
  if (busy.value || !note.value) return
  busy.value = true
  try {
    await deliveryCommands.setDeliveryStatus(String(note.value.id), action, reason ?? null)
    await store.fetchOne('deliveryNotes', String(note.value.id))
    toast.add({ title: t('app.delivery.statusUpdated'), color: 'success' })
  }
  catch (error: unknown) {
    toast.add({
      title: t('app.delivery.statusUpdateFailed'),
      description: error instanceof Error ? error.message : String(error),
      color: 'error',
    })
  }
  finally {
    busy.value = false
  }
}

async function cancelNote() {
  const reason = cancelReason.value.trim()
  if (!reason) return
  const ok = await confirm({
    kind: 'generic',
    title: t('app.delivery.actionCancel'),
    description: t('app.delivery.cancelHint'),
    confirmColor: 'error',
  })
  if (!ok) return
  cancelOpen.value = false
  await runAction('cancel', reason)
  cancelReason.value = ''
}

function printNote() {
  if (!note.value) return
  void printDeliveryNoteDocument(note.value, shopName.value)
}
</script>

<template>
  <div class="flex h-full min-h-0 flex-1 flex-col gap-3 overflow-y-auto bg-muted/20 p-3">
    <p v-if="loading && !note" class="text-sm text-muted">{{ t('common.loading') }}</p>
    <UEmpty
      v-else-if="!note"
      variant="naked"
      icon="i-lucide-package-x"
      :title="t('app.ui.recordNotFound')"
    />

    <template v-else>
      <!-- Header chrome: status badge + Delivery OK / Cancel + Print -->
      <div class="flex flex-wrap items-center justify-between gap-2 print:hidden">
        <div class="flex items-center gap-2">
          <UBadge
            size="lg"
            variant="subtle"
            :color="status === 'Delivered' ? 'success' : status === 'Cancelled' ? 'error' : status === 'Out for Delivery' ? 'warning' : status === 'Confirmed' ? 'primary' : 'neutral'"
          >
            {{ status }}
          </UBadge>
          <p v-if="note.cancelReason" class="text-xs text-muted">{{ note.cancelReason }}</p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <UButton
            v-for="item in statusActions"
            :key="item.action"
            :color="item.color"
            :variant="item.solid ? 'solid' : 'soft'"
            size="sm"
            :icon="item.icon"
            :label="item.label"
            :loading="busy"
            @click="item.action === 'cancel' ? (cancelOpen = true) : runAction(item.action)"
          />
          <UButton
            color="neutral"
            variant="outline"
            size="sm"
            icon="i-lucide-printer"
            :label="t('app.delivery.print')"
            @click="printNote"
          />
        </div>
      </div>

      <!-- Lines to deliver (from the linked POS sale) -->
      <UCard :ui="{ body: 'p-0 sm:p-0' }" class="print:hidden">
        <template #header>
          <p class="text-sm font-medium">{{ t('app.delivery.lines') }}</p>
        </template>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-elevated text-left text-xs text-muted">
              <tr>
                <th class="px-3 py-2 font-medium">{{ t('app.fields.product') }}</th>
                <th class="px-3 py-2 font-medium">{{ t('app.fields.uom') }}</th>
                <th class="px-3 py-2 text-right font-medium">{{ t('app.delivery.qtyOrdered') }}</th>
                <th class="px-3 py-2 text-right font-medium">{{ t('app.delivery.qtyToDeliver') }}</th>
                <th class="px-3 py-2 text-right font-medium">{{ t('app.delivery.qtyDelivered') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(line, index) in lines" :key="line.id ?? index" class="border-t border-default">
                <td class="px-3 py-2 font-medium">{{ line.product }}</td>
                <td class="px-3 py-2 text-muted">{{ line.uomSymbol || '—' }}</td>
                <td class="px-3 py-2 text-right tabular-nums">{{ line.qtyOrdered }}</td>
                <td class="px-3 py-2 text-right tabular-nums">{{ line.qtyToDeliver }}</td>
                <td class="px-3 py-2 text-right tabular-nums">{{ line.qtyDelivered }}</td>
              </tr>
              <tr v-if="!lines.length">
                <td colspan="5" class="px-3 py-4 text-center text-sm text-muted">{{ t('app.ui.noRecords') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </UCard>

      <p v-if="linkedInvoiceNos.length" class="text-xs text-muted">
        {{ t('app.delivery.linkedSale') }}: {{ linkedInvoiceNos.join(', ') }}
      </p>
    </template>

    <!-- Cancel reason dialog -->
    <CommonAppDialog
      v-model:open="cancelOpen"
      :title="t('app.delivery.actionCancel')"
      icon="i-lucide-circle-off"
      color="error"
      size="sm"
      :loading="busy"
    >
      <div class="space-y-3">
        <p class="text-sm text-muted">{{ t('app.delivery.cancelHint') }}</p>
        <CommonAppTextareaField
          v-model="cancelReason"
          :label="t('app.delivery.cancelReason')"
          :required="true"
          :rows="3"
          class="w-full"
        />
      </div>
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton
            color="neutral"
            variant="ghost"
            :label="t('common.cancel')"
            @click="cancelOpen = false"
          />
          <UButton
            color="error"
            icon="i-lucide-circle-off"
            :loading="busy"
            :disabled="!cancelReason.trim()"
            :label="t('app.delivery.actionCancel')"
            @click="cancelNote"
          />
        </div>
      </template>
    </CommonAppDialog>
  </div>
</template>
