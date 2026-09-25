<script setup lang="ts">
import type { AppRecord } from '~/config/admin-seed'
import { PAYMENT_METHODS } from '~/config/pos-options'
import { formatMoney } from '~/composables/module/useModule'
import { debtCurrency, selectedDebtsTotal } from '~/utils/reports/debts'

export type DebtPaymentKind = 'customer' | 'supplier'

/**
 * Settle several open debt documents of ONE customer/supplier in a single
 * action. The backend settles open debts **oldest-first** (existing rule) and
 * rejects overpayment; all selected rows share the same party + currency.
 */
const props = defineProps<{
  kind: DebtPaymentKind
  debts: AppRecord[]
  currency?: string
}>()

const open = defineModel<boolean>('open', { default: false })
const emit = defineEmits<{
  submit: [payload: { amount: number, paymentMethod: string, reference: string | null }]
}>()

const { t } = useI18n()
const preferences = usePreferencesStore()

const amount = ref<number | undefined>()
const paymentMethod = ref('Cash')
const reference = ref('')
const methodOptions = PAYMENT_METHODS.filter(method => method !== 'Credit')

const currency = computed(() => debtCurrency(props.debts[0], props.currency || preferences.currency || 'USD'))
const party = computed(() => String(props.debts[0]?.customer || props.debts[0]?.supplier || ''))
const total = computed(() => selectedDebtsTotal(props.debts))
const canSubmit = computed(() => {
  const pay = Number(amount.value || 0)
  return Boolean(props.debts.length && pay > 0 && pay <= total.value + 1e-9 && paymentMethod.value)
})

watch(() => [open.value, props.debts.length] as const, ([isOpen]) => {
  if (!isOpen) return
  amount.value = total.value > 0 ? total.value : undefined
  paymentMethod.value = 'Cash'
  reference.value = ''
})

function money(value: unknown) {
  return formatMoney(value, currency.value)
}

function onSubmit() {
  if (!canSubmit.value) return
  emit('submit', {
    amount: Number(amount.value),
    paymentMethod: paymentMethod.value,
    reference: reference.value.trim() || null,
  })
}
</script>

<template>
  <CommonAppDialog
    v-model:open="open"
    :title="t('app.reports.paySelected')"
    icon="i-lucide-hand-coins"
    color="success"
    size="sm"
  >
    <div class="w-full space-y-3">
      <div class="grid gap-1 text-sm">
        <p>
          <span class="text-muted">{{ kind === 'customer' ? t('app.reports.customer') : t('app.reports.supplier') }}:</span>
          <span class="ms-1 font-medium">{{ party || '—' }}</span>
        </p>
        <p>
          <span class="text-muted">{{ t('app.reports.selectedDebts') }}:</span>
          <span class="ms-1 font-medium tabular-nums">{{ debts.length }}</span>
        </p>
        <p>
          <span class="text-muted">{{ t('app.reports.selectedTotal') }}:</span>
          <span class="ms-1 font-medium tabular-nums">{{ money(total) }} ({{ currency }})</span>
        </p>
      </div>

      <p class="text-xs text-muted">{{ t('app.reports.paySelectedHint') }}</p>

      <CommonAppMoneyField
        v-model="amount"
        name="amount"
        :label="t('app.reports.paymentAmount')"
        :required="true"
        :min="0"
        :step="0.01"
        class="w-full"
        :help="Number(amount || 0) > total ? t('app.reports.paymentOverRemaining') : ''"
      />
      <CommonAppSelectMenuField
        v-model="paymentMethod"
        name="paymentMethod"
        :items="methodOptions.map(method => ({ label: method, value: method }))"
        :label="t('app.fields.paymentMethod')"
        :required="true"
        class="w-full"
      />
      <CommonAppTextField
        v-model="reference"
        name="reference"
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
          :disabled="!canSubmit"
          :label="t('app.reports.confirmPayment')"
          @click="onSubmit"
        />
      </div>
    </template>
  </CommonAppDialog>
</template>
