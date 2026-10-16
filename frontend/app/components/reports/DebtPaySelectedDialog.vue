<script setup lang="ts">
import type { AppRecord } from '~/config/admin-seed'
import { PAYMENT_METHODS } from '~/config/pos-options'
import { formatMoney } from '~/composables/module/useModule'
import { formatNumber } from '~/utils/format/format-service'
import { convertAmount, roundMoney } from '~/utils/pos/cart'
import { debtCurrency, selectedDebtsTotal } from '~/utils/reports/debts'

export type DebtPaymentKind = 'customer' | 'supplier'

/**
 * Settle several open debt documents of ONE customer/supplier in a single
 * action. The backend settles open debts **oldest-first** (existing rule) and
 * rejects overpayment; all selected rows share the same party + currency.
 *
 * The payment currency option ($/៛) picks the currency the customer is
 * COLLECTING IN: the amount is typed in that currency, converted at the
 * exchange rate and settles the debts (which keep their own currency). The
 * receipt prints the collected amount next to the settled one.
 */
const props = defineProps<{
  kind: DebtPaymentKind
  debts: AppRecord[]
  currency?: string
}>()

const open = defineModel<boolean>('open', { default: false })
const emit = defineEmits<{
  submit: [payload: {
    /** Settled amount in the debts' own currency. */
    amount: number
    paymentMethod: string
    /** Currency the cashier actually collected (USD | KHR). */
    collectedCurrency: string
    /** Collected amount, in `collectedCurrency`. */
    collectedAmount: number
    /** KHR per 1 USD used when the collected currency differs, else null. */
    exchangeRate: number | null
  }]
}>()

const { t } = useI18n()
const preferences = usePreferencesStore()

/** Collected amount, in the selected payment (`collectCurrency`) currency. */
const amount = ref<number | undefined>()
const paymentMethod = ref('Cash')
const methodOptions = PAYMENT_METHODS.filter(method => method !== 'Credit')

/** Debt document currency — payments always settle THIS currency. */
const debtCurrencyCode = computed(() => debtCurrency(props.debts[0], props.currency || preferences.currency || 'USD'))
/** Currency the cashier collects in (may differ from the debt currency). */
const collectCurrency = ref<'USD' | 'KHR'>('USD')
/** KHR per 1 USD used for the conversion (0 = not known yet). */
const collectRate = ref(0)
const rateDialogOpen = ref(false)
const pendingCollect = ref<'USD' | 'KHR' | null>(null)

const party = computed(() => String(props.debts[0]?.customer || props.debts[0]?.supplier || ''))
const total = computed(() => selectedDebtsTotal(props.debts))
/** Collected in another currency than the debts' → convert at the rate. */
const converting = computed(() => collectCurrency.value !== debtCurrencyCode.value)
/** Amount this payment settles in the debts' own currency. */
const settledAmount = computed(() => {
  const entered = Number(amount.value || 0)
  if (!Number.isFinite(entered) || entered <= 0) return 0
  if (!converting.value) return roundMoney(entered)
  return convertAmount(entered, collectCurrency.value, debtCurrencyCode.value as 'USD' | 'KHR', collectRate.value)
})
const canSubmit = computed(() => Boolean(
  props.debts.length
  && settledAmount.value > 0
  && settledAmount.value <= total.value + 1e-9
  && paymentMethod.value,
))

/** Prefill the collected amount with the full selected balance. */
function prefillAmount() {
  if (total.value <= 0) {
    amount.value = undefined
    return
  }
  amount.value = converting.value
    ? convertAmount(total.value, debtCurrencyCode.value as 'USD' | 'KHR', collectCurrency.value, collectRate.value)
    : roundMoney(total.value)
}

watch(() => [open.value, props.debts.length] as const, ([isOpen]) => {
  if (!isOpen) return
  collectCurrency.value = debtCurrencyCode.value === 'KHR' ? 'KHR' : 'USD'
  collectRate.value = debtCurrencyCode.value === 'KHR' ? Number(props.debts[0]?.exchangeRate || 0) : 0
  pendingCollect.value = null
  paymentMethod.value = 'Cash'
  prefillAmount()
})

function money(value: unknown) {
  return formatMoney(value, debtCurrencyCode.value)
}

/** $/៛ pressed: collect in this currency (asking for the rate when needed). */
function selectCollectCurrency(value: 'USD' | 'KHR') {
  if (value === collectCurrency.value) return
  if (value !== debtCurrencyCode.value && collectRate.value <= 0) {
    pendingCollect.value = value
    rateDialogOpen.value = true
    return
  }
  collectCurrency.value = value
  prefillAmount()
}

/** Shared rate dialog confirmed: use it for this collection. */
function onRateConfirm(rate: number) {
  const parsed = Number(rate)
  if (!Number.isFinite(parsed) || parsed <= 0) return
  collectRate.value = parsed
  const target = pendingCollect.value
  pendingCollect.value = null
  if (target) {
    collectCurrency.value = target
    prefillAmount()
  }
}

function onSubmit() {
  if (!canSubmit.value) return
  emit('submit', {
    amount: settledAmount.value,
    paymentMethod: paymentMethod.value,
    collectedCurrency: collectCurrency.value,
    collectedAmount: roundMoney(Number(amount.value || 0)),
    exchangeRate: converting.value ? collectRate.value : null,
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
          <span class="ms-1 font-medium tabular-nums">{{ money(total) }} ({{ debtCurrencyCode }})</span>
        </p>
      </div>

      <p class="text-xs text-muted">{{ t('app.reports.paySelectedHint') }}</p>

      <!-- Payment currency: collect in $ or ៛; the debts keep their currency. -->
      <div class="flex items-center justify-between">
        <span class="text-sm text-muted">{{ t('app.reports.paymentCurrency') }}</span>
        <div class="inline-flex overflow-hidden rounded-sm border border-default">
          <UButton
            size="xs"
            :color="collectCurrency === 'USD' ? 'primary' : 'neutral'"
            :variant="collectCurrency === 'USD' ? 'solid' : 'ghost'"
            label="$"
            :title="t('app.pos.currencyUsd')"
            :aria-label="t('app.pos.currencyUsd')"
            :aria-pressed="collectCurrency === 'USD'"
            @click="selectCollectCurrency('USD')"
          />
          <UButton
            size="xs"
            :color="collectCurrency === 'KHR' ? 'primary' : 'neutral'"
            :variant="collectCurrency === 'KHR' ? 'solid' : 'ghost'"
            label="៛"
            :title="t('app.pos.currencyKhr')"
            :aria-label="t('app.pos.currencyKhr')"
            :aria-pressed="collectCurrency === 'KHR'"
            @click="selectCollectCurrency('KHR')"
          />
        </div>
      </div>

      <CommonAppMoneyField
        v-model="amount"
        name="amount"
        :label="t('app.reports.paymentAmount')"
        :required="true"
        :currency="collectCurrency"
        :min="0"
        :step="0.0001"
        class="w-full"
        :help="settledAmount > total ? t('app.reports.paymentOverRemaining') : ''"
      />
      <p v-if="converting && collectRate > 0" class="text-xs text-muted">
        = {{ money(settledAmount) }} ({{ debtCurrencyCode }}) · 1 USD = {{ formatNumber(Math.round(collectRate)) }} KHR
      </p>

      <CommonAppSelectMenuField
        v-model="paymentMethod"
        name="paymentMethod"
        :items="methodOptions.map(method => ({ label: method, value: method }))"
        :label="t('app.fields.paymentMethod')"
        :required="true"
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

  <CommonAppExchangeRateDialog
    v-model:open="rateDialogOpen"
    @confirm="onRateConfirm"
  />
</template>
