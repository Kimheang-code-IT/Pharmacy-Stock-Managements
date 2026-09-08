<script setup lang="ts">
import type { AppRecord } from '~/config/admin-seed'
import { formatMoney } from '~/composables/module/useModule'
import {
  buildReturnLines,
  returnRefundTotal,
  validateReturnLines,
  type ReturnDocumentKind,
  type ReturnLineDraft,
} from '~/utils/reports/returns'

/**
 * Customer return (Sales Report) or supplier return (Purchase Report).
 * Modal only — no /returns page. Confirms via PosCommandRepository.
 */
const props = defineProps<{
  kind: ReturnDocumentKind
  document: AppRecord | null
  currency?: string
}>()

const open = defineModel<boolean>('open', { default: false })
const emit = defineEmits<{
  submit: [payload: {
    kind: ReturnDocumentKind
    documentId: string
    reason: string
    lines: Array<{ lineId: string, quantity: number, restock: boolean }>
  }]
}>()

const { t } = useI18n()
const preferences = usePreferencesStore()

const reason = ref('')
const lines = ref<ReturnLineDraft[]>([])
const busy = ref(false)

const currency = computed(() => props.currency || preferences.currency || 'USD')
const title = computed(() => props.kind === 'sale'
  ? t('app.reports.customerReturnTitle')
  : t('app.reports.supplierReturnTitle'))
const docNo = computed(() => {
  if (!props.document) return ''
  return String(props.document.saleNo || props.document.invoiceNo || props.document.purchaseNo || '')
})
const party = computed(() => {
  if (!props.document) return ''
  return String(props.document.customer || props.document.supplier || '')
})
const refundTotal = computed(() => returnRefundTotal(lines.value))
const validation = computed(() => validateReturnLines(lines.value))
const canSubmit = computed(() => Boolean(
  props.document?.id
  && reason.value.trim()
  && validation.value == null,
))

watch(
  () => [open.value, props.document?.id, props.kind] as const,
  ([isOpen]) => {
    if (!isOpen) return
    reason.value = ''
    lines.value = buildReturnLines(props.document, props.kind)
  },
)

function money(value: unknown) {
  return formatMoney(value, currency.value)
}

function clampQty(line: ReturnLineDraft, raw: number | null | undefined) {
  const n = Number(raw ?? 0)
  if (!Number.isFinite(n) || n <= 0) {
    line.qty = 0
    return
  }
  line.qty = Math.min(line.returnableQty, Math.round(n * 10000) / 10000)
}

async function submit() {
  if (!canSubmit.value || !props.document?.id || busy.value) return
  busy.value = true
  try {
    emit('submit', {
      kind: props.kind,
      documentId: String(props.document.id),
      reason: reason.value.trim(),
      lines: lines.value
        .filter(line => Number(line.qty) > 0)
        .map(line => ({
          lineId: line.lineId,
          quantity: Number(line.qty),
          restock: props.kind === 'sale' ? Boolean(line.restock) : false,
        })),
    })
  }
  finally {
    busy.value = false
  }
}
</script>

<template>
  <CommonAppDialog
    v-model:open="open"
    :title="title"
    icon="i-lucide-undo-2"
    color="warning"
    wide
    :loading="busy"
  >
    <div class="flex min-h-0 flex-col gap-3">
      <div class="grid gap-1 text-sm sm:grid-cols-2">
        <p>
          <span class="text-muted">{{ kind === 'sale' ? t('app.reports.saleNo') : t('app.reports.purchaseNo') }}:</span>
          <span class="ms-1 font-medium text-highlighted">{{ docNo || '—' }}</span>
        </p>
        <p>
          <span class="text-muted">{{ kind === 'sale' ? t('app.reports.customer') : t('app.reports.supplier') }}:</span>
          <span class="ms-1 font-medium text-highlighted">{{ party || '—' }}</span>
        </p>
      </div>

      <CommonAppTextareaField
        v-model="reason"
        :label="t('app.reports.returnReason')"
        :rows="2"
        required
        class="w-full"
      />

      <div
v-if="!lines.length"
class="rounded-sm border border-dashed border-default p-6 text-center text-sm text-muted">
        {{ t('app.reports.nothingToReturn') }}
      </div>

      <div
v-else
class="max-h-[45vh] overflow-auto rounded-sm border border-default">
        <table class="w-full min-w-[40rem] border-collapse text-sm">
          <thead class="sticky top-0 bg-elevated text-left text-xs text-muted">
            <tr>
              <th class="px-2 py-1.5 font-medium">{{ t('app.pos.product') }}</th>
              <th class="px-2 py-1.5 font-medium text-end">{{ t('app.reports.soldQty') }}</th>
              <th class="px-2 py-1.5 font-medium text-end">{{ t('app.reports.returnedQty') }}</th>
              <th class="px-2 py-1.5 font-medium text-end">{{ t('app.reports.returnableQty') }}</th>
              <th class="px-2 py-1.5 font-medium text-end">{{ t('app.reports.returnQty') }}</th>
              <th class="px-2 py-1.5 font-medium text-end">{{ t('app.pos.price') }}</th>
              <th
v-if="kind === 'sale'"
class="px-2 py-1.5 font-medium text-center">{{ t('app.reports.restock') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="line in lines"
              :key="line.lineId"
              class="border-t border-default"
            >
              <td class="px-2 py-1.5">
                <p class="font-medium text-highlighted">{{ line.name }}</p>
                <p
v-if="line.uom"
class="text-xs text-muted">{{ line.uom }}</p>
              </td>
              <td class="px-2 py-1.5 text-end tabular-nums">{{ line.soldQty }}</td>
              <td class="px-2 py-1.5 text-end tabular-nums">{{ line.returnedQty }}</td>
              <td class="px-2 py-1.5 text-end tabular-nums">{{ line.returnableQty }}</td>
              <td class="px-2 py-1.5 text-end">
                <UInput
                  :model-value="line.qty || undefined"
                  type="number"
                  size="sm"
                  :min="0"
                  :max="line.returnableQty"
                  :step="0.0001"
                  class="ms-auto w-24"
                  @update:model-value="clampQty(line, Number($event))"
                />
              </td>
              <td class="px-2 py-1.5 text-end tabular-nums">{{ money(line.unitAmount) }}</td>
              <td
v-if="kind === 'sale'"
class="px-2 py-1.5 text-center">
                <UCheckbox v-model="line.restock" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="flex items-center justify-between gap-2 text-sm">
        <p
v-if="validation === 'empty' && reason.trim()"
class="text-warning">
          {{ t('app.reports.returnQtyRequired') }}
        </p>
        <p
v-else-if="validation === 'over'"
class="text-error">
          {{ t('app.reports.returnOverQty') }}
        </p>
        <span v-else />
        <p class="font-semibold tabular-nums text-highlighted">
          {{ t('app.reports.returnTotal') }}: {{ money(refundTotal) }}
        </p>
      </div>
    </div>

    <template #footer>
      <div class="flex w-full justify-end gap-2">
        <UButton
          color="neutral"
          variant="ghost"
          :label="t('common.cancel')"
          :disabled="busy"
          @click="open = false"
        />
        <UButton
          color="warning"
          icon="i-lucide-undo-2"
          :label="t('app.reports.confirmReturn')"
          :loading="busy"
          :disabled="!canSubmit"
          @click="submit"
        />
      </div>
    </template>
  </CommonAppDialog>
</template>
