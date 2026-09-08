<script setup lang="ts">
import type { AppRecord } from '~/config/admin-seed'
import { PAYMENT_METHODS } from '~/config/pos-options'
import { formatMoney } from '~/composables/module/useModule'

export type DebtPaymentKind = 'customer' | 'supplier'

/**
 * Record a payment against one customer or supplier debt document.
 * Modal only — opened from Customer / Supplier Debt Report row actions.
 */
const props = defineProps<{
  kind: DebtPaymentKind
  debt: AppRecord | null
  currency?: string
}>()

const open = defineModel<boolean>('open', { default: false })
const emit = defineEmits<{
  submit: [payload: {
    kind: DebtPaymentKind
    debtId: string
    partyId: string
    amount: number
    paymentMethod: string
    reference: string | null
  }]
}>()

const { t } = useI18n()
const preferences = usePreferencesStore()

const amount = ref<number | undefined>()
const paymentMethod = ref('Cash')
const reference = ref('')
const busy = ref(false)

/** Debt payments settle cash/bank — not new credit. */
const methodOptions = PAYMENT_METHODS.filter(method => method !== 'Credit')

const currency = computed(() => props.currency || preferences.currency || 'USD')
const title = computed(() => props.kind === 'customer'
  ? t('app.reports.payCustomerDebtTitle')
  : t('app.reports.paySupplierDebtTitle'))
const docNo = computed(() => {
  if (!props.debt) return ''
  return String(props.debt.invoiceNo || props.debt.purchaseNo || '')
})
const party = computed(() => {
  if (!props.debt) return ''
  return String(props.debt.customer || props.debt.supplier || '')
})
const remaining = computed(() => Number(props.debt?.remainingAmount || 0))
const canSubmit = computed(() => {
  const pay = Number(amount.value || 0)
  return Boolean(
    props.debt?.id
    && remaining.value > 0
    && pay > 0
    && pay <= remaining.value + 1e-9
    && paymentMethod.value,
  )
})

watch(
  () => [open.value, props.debt?.id, props.kind] as const,
  ([isOpen]) => {
    if (!isOpen) return
    amount.value = remaining.value > 0 ? remaining.value : undefined
    paymentMethod.value = 'Cash'
    reference.value = ''
  },
)

function money(value: unknown) {
  return formatMoney(value, currency.value)
}

async function onSubmit() {
  if (!canSubmit.value || !props.debt || busy.value) return
  const partyId = props.kind === 'customer'
    ? String(props.debt.customerId || '')
    : String(props.debt.supplierId || '')
  if (!partyId) return
  busy.value = true
  try {
    emit('submit', {
      kind: props.kind,
      debtId: String(props.debt.id),
      partyId,
      amount: Number(amount.value),
      paymentMethod: paymentMethod.value,
      reference: reference.value.trim() || null,
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
    icon="i-lucide-hand-coins"
    color="success"
    size="sm"
    :loading="busy"
  >
    <div class="w-full space-y-3">
      <div class="grid gap-1 text-sm">
        <p>
          <span class="text-muted">{{ kind === 'customer' ? t('app.reports.customer') : t('app.reports.supplier') }}:</span>
          <span class="ms-1 font-medium">{{ party || '—' }}</span>
        </p>
        <p>
          <span class="text-muted">{{ kind === 'customer' ? t('app.fields.invoiceNo') : t('app.reports.purchaseNo') }}:</span>
          <span class="ms-1 font-medium">{{ docNo || '—' }}</span>
        </p>
        <p>
          <span class="text-muted">{{ t('app.reports.remainingAmount') }}:</span>
          <span class="ms-1 font-medium tabular-nums">{{ money(remaining) }}</span>
        </p>
      </div>

      <CommonAppMoneyField
        v-model="amount"
        :label="t('app.reports.paymentAmount')"
        :required="true"
        :min="0"
        :step="0.01"
        class="w-full"
        :help="Number(amount || 0) > remaining ? t('app.reports.paymentOverRemaining') : ''"
      />
      <CommonAppSelectMenuField
        v-model="paymentMethod"
        :items="methodOptions.map(method => ({ label: method, value: method }))"
        :label="t('app.fields.paymentMethod')"
        :required="true"
        class="w-full"
      />
      <CommonAppTextField
        v-model="reference"
        :label="t('app.fields.reference')"
        :placeholder="t('app.reports.paymentReferenceHint')"
        class="w-full"
      />
    </div>

    <template #footer>
      <div class="flex w-full justify-end gap-2">
        <UButton
          color="neutral"
          variant="ghost"
          :label="t('common.cancel')"
          @click="open = false"
        />
        <UButton
          color="success"
          icon="i-lucide-hand-coins"
          :loading="busy"
          :disabled="!canSubmit"
          :label="t('app.reports.confirmPayment')"
          @click="onSubmit"
        />
      </div>
    </template>
  </CommonAppDialog>
</template>
