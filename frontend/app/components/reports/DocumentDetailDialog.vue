<script setup lang="ts">
import type { AppRecord } from '~/config/admin-seed'
import { formatMoney } from '~/composables/module/useModule'

/**
 * Read-only detail dialog for a completed document — Sale (Sales Report) or
 * Purchase (Purchase Report). Opened by clicking the document number on the
 * owning report; shows the full document: meta, line items and totals.
 */
const props = defineProps<{
  kind: 'sale' | 'purchase'
  document: AppRecord | null
  currency?: string
}>()

const open = defineModel<boolean>('open', { default: false })

const { t } = useI18n()
const preferences = usePreferencesStore()

const currency = computed(() => props.currency || preferences.currency || 'USD')
const title = computed(() => props.kind === 'sale'
  ? t('app.reports.saleDetail')
  : t('app.reports.purchaseDetail'))

const docNo = computed(() => {
  if (!props.document) return ''
  return String(props.document.saleNo || props.document.purchaseNo || '')
})
const party = computed(() => {
  if (!props.document) return ''
  return String(props.document.customer || props.document.supplier || '')
})
const lines = computed<AppRecord[]>(() => {
  const items = props.document?.items
  return Array.isArray(items) ? items as AppRecord[] : []
})
const subtotal = computed(() => {
  if (props.document && props.document.subtotal != null) return Number(props.document.subtotal)
  return roundMoney(lines.value.reduce((sum, line) => sum + Number(line.total || 0), 0))
})
const discount = computed(() => Number(props.document?.discount || 0))
const total = computed(() => Number(props.document?.total || 0))
const paidAmount = computed(() => Number(props.document?.paidAmount || 0))
const remaining = computed(() => Number(props.document?.remaining ?? props.document?.remainingAmount ?? 0))

function roundMoney(value: number) {
  return Math.round(value * 100) / 100
}

function money(value: unknown) {
  return formatMoney(value, currency.value)
}
</script>

<template>
  <CommonAppDialog
    v-model:open="open"
    :title="`${title} ${docNo ? `· ${docNo}` : ''}`"
    :icon="kind === 'sale' ? 'i-lucide-receipt-text' : 'i-lucide-package-plus'"
    :color="kind === 'sale' ? 'primary' : 'success'"
    size="md"
  >
    <div v-if="document" class="flex min-h-0 flex-col gap-3">
      <div class="grid gap-1 text-sm sm:grid-cols-2">
        <p>
          <span class="text-muted">{{ kind === 'sale' ? t('app.reports.saleNo') : t('app.reports.purchaseNo') }}:</span>
          <span class="ms-1 font-medium text-highlighted">{{ docNo || '—' }}</span>
        </p>
        <p>
          <span class="text-muted">{{ t('app.fields.date') }}:</span>
          <span class="ms-1 font-medium text-highlighted">{{ document.date || '—' }}</span>
        </p>
        <p>
          <span class="text-muted">{{ kind === 'sale' ? t('app.reports.customer') : t('app.reports.supplier') }}:</span>
          <span class="ms-1 font-medium text-highlighted">{{ party || '—' }}</span>
        </p>
        <p>
          <span class="text-muted">{{ t('app.fields.status') }}:</span>
          <span class="ms-1 font-medium text-highlighted">{{ document.status || '—' }}</span>
        </p>
        <p>
          <span class="text-muted">{{ t('app.fields.paymentMethod') }}:</span>
          <span class="ms-1 font-medium text-highlighted">{{ document.paymentMethod || '—' }}</span>
        </p>
        <p>
          <span class="text-muted">{{ t('app.fields.user') }}:</span>
          <span class="ms-1 font-medium text-highlighted">{{ document.cashier || document.user || '—' }}</span>
        </p>
      </div>

      <div class="overflow-hidden rounded-sm border border-default">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-default bg-elevated/50 text-start">
              <th class="px-2 py-1.5 text-start font-medium text-muted">{{ t('app.pos.product') }}</th>
              <th class="px-2 py-1.5 text-end font-medium text-muted">{{ t('app.fields.quantity') }}</th>
              <th class="px-2 py-1.5 text-end font-medium text-muted">{{ t('app.fields.unitPrice') }}</th>
              <th class="px-2 py-1.5 text-end font-medium text-muted">{{ t('app.fields.lineTotal') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="line in lines"
              :key="String(line.id || line.name)"
              class="border-b border-default last:border-b-0"
            >
              <td class="px-2 py-1.5 text-default">{{ line.name || '—' }}</td>
              <td class="px-2 py-1.5 text-end tabular-nums text-default">{{ line.quantity }}</td>
              <td class="px-2 py-1.5 text-end tabular-nums text-default">{{ money(line.price) }}</td>
              <td class="px-2 py-1.5 text-end tabular-nums text-default">{{ money(line.total) }}</td>
            </tr>
            <tr v-if="!lines.length">
              <td colspan="4" class="px-2 py-3 text-center text-muted">{{ t('app.ui.noRecords') }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="rounded-lg bg-elevated p-3 text-sm">
        <div class="flex items-center justify-between">
          <span class="text-muted">{{ t('app.fields.subtotal') }}</span>
          <span>{{ money(subtotal) }}</span>
        </div>
        <div v-if="discount > 0" class="flex items-center justify-between">
          <span class="text-muted">{{ t('app.fields.discount') }}</span>
          <span>−{{ money(discount) }}</span>
        </div>
        <div class="flex items-center justify-between">
          <span class="text-muted">{{ t('app.fields.total') }}</span>
          <span class="font-semibold">{{ money(total) }}</span>
        </div>
        <div class="flex items-center justify-between">
          <span class="text-muted">{{ t('app.fields.paid') }}</span>
          <span>{{ money(paidAmount) }}</span>
        </div>
        <div
          class="flex items-center justify-between"
          :class="remaining > 0 ? 'text-warning' : ''"
        >
          <span class="text-muted">{{ t('app.fields.remaining') }}</span>
          <span class="font-semibold">{{ money(remaining) }}</span>
        </div>
      </div>
    </div>
  </CommonAppDialog>
</template>
